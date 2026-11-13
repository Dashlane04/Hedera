# Hedera: ghi chú nghiên cứu và đặc tả thuật toán

Ngày đọc và đối chiếu: 22/10/2026.

**Paper:** Mohammad Al-Fares, Sivasankar Radhakrishnan, Barath Raghavan, Nelson Huang, Amin Vahdat. *Hedera: Dynamic Flow Scheduling for Data Center Networks*, NSDI 2010.

**Nguồn chính:** [trang USENIX](https://www.usenix.org/conference/nsdi10-0/hedera-dynamic-flow-scheduling-data-center-networks), [PDF USENIX](https://www.usenix.org/legacy/event/nsdi10/tech/full_papers/al-fares.pdf). Bản PDF lưu tại `research/sources/hedera-nsdi2010.pdf`.

Tài liệu này diễn giải lại bằng tiếng Việt. Giả mã được viết lại để làm rõ dữ liệu và điều kiện biên, không phải bản chép nguyên văn hay code gốc. Ký hiệu “diễn giải triển khai” dùng cho các suy luận và đề xuất bổ sung. Số trang dưới đây tính từ trang đầu của PDF, từ 1 đến 15.

## 1. Luận điểm trung tâm

Mạng fat-tree có nhiều đường cùng chi phí nhưng ECMP có thể băm nhiều flow lớn vào cùng một link, khiến link đó nghẽn trong khi đường khác còn dư. Hedera bổ sung một bộ điều phối có thông tin toàn mạng: phát hiện flow lớn, ước lượng nhu cầu khi bỏ các nút thắt bên trong mạng, rồi bố trí đường bằng Global First Fit hoặc Simulated Annealing.

Ba thành phần có vai trò khác nhau:

| Thành phần | Câu hỏi cần trả lời | Đầu ra |
|---|---|---|
| Demand Estimation | Flow có thể dùng bao nhiêu băng thông nếu chỉ bị giới hạn ở NIC hai đầu? | Demand cho từng flow |
| Global First Fit (GFF) | Đường đầu tiên nào còn đủ chỗ trên mọi link? | Một đường cho flow lớn mới |
| Simulated Annealing (SA) | Có thể đổi cách ánh xạ đích tới core để giảm tổng quá tải không? | Ánh xạ đích-core tốt nhất tìm được |

Demand Estimation được dùng trước GFF hoặc SA. GFF và SA là hai lựa chọn đặt đường được so sánh; không phải chuỗi bắt buộc GFF rồi SA. ECMP vẫn phục vụ các flow chưa được Hedera quản lý.

**Định vị:** Hedera giải quyết flow placement/routing, không thay TCP, không lập lịch từng packet, không huấn luyện mô hình ML và không phải một topology mới. SA là phương pháp tối ưu ngẫu nhiên cổ điển.

Nguồn đối chiếu: §2-4, trang 2-8.

## 2. Tại sao ECMP chưa đủ?

ECMP ánh xạ flow vào một trong các đường cùng chi phí bằng hàm băm. Cách này giữ các packet của flow trên cùng đường ở trạng thái ổn định, nhưng không lựa chọn theo nhu cầu băng thông hiện tại của các flow khác.

Ví dụ tự dựng: hai đường ứng viên có dung lượng 1 Gbit/s. Hai flow độc lập, mỗi flow có thể gửi 1 Gbit/s và không bị nghẽn tại NIC, cùng bị băm lên đường thứ nhất. Chúng chỉ đạt tổng khoảng 1 Gbit/s tại nút thắt, trong khi đường thứ hai bỏ trống. Nếu bố trí mỗi flow trên một đường, tổng khả dụng có thể là 2 Gbit/s. Ví dụ chỉ minh họa nút thắt, không phải dự báo TCP cho mọi topology.

Paper phân biệt:

- **Local collision:** các flow cùng tranh một uplink ngay tại một switch.
- **Downstream collision:** quyết định riêng ở các switch đầu nguồn tạo nút thắt tại một link phía sau.

Đây là lý do phải kiểm tra toàn bộ đường, thay vì chỉ chọn cổng đầu tiên ít tải. Cũng không nên suy ra ECMP luôn kém: với nhiều flow nhỏ, tải phân tán đều hoặc các flow kết thúc nhanh, Hedera có thể đem lại ít lợi ích.

Nguồn đối chiếu: §2.2, Figure 2-3; §6.3.

## 3. Mô hình fat-tree và ký hiệu

Xét fat-tree chuẩn dùng switch k cổng, k chẵn, link đồng tốc:

- k pod.
- Mỗi pod có k/2 edge switch và k/2 aggregation switch.
- Mỗi edge switch nối k/2 host.
- Số host mỗi pod và số core đều bằng q = (k/2)^2.
- Tổng số host N = k^3/4.
- Tổng số switch = 5k^2/4.
- Giữa hai host khác pod có q đường ngắn nhất, mỗi đường được xác định bởi core được chọn.

Hai host cùng edge hoặc cùng pod có đường ngắn nhất không cần đi qua core. Khi triển khai SA, chỉ áp dụng lựa chọn core vào lưu lượng thực sự cần core; không ép traffic nội bộ đi vòng qua core.

| Ký hiệu | Ý nghĩa |
|---|---|
| F | Tập flow lớn đang hoạt động |
| d_f | Demand ước lượng của flow f |
| C_l | Dung lượng link có hướng l |
| p_f | Đường của flow f |
| U_l | Tổng demand hoặc reservation đang quy cho link l |
| pi(h) | Core được gán cho host đích h trong trạng thái SA |
| I | Ngân sách số vòng SA |
| f_avg | Số flow lớn trung bình đi đến một host |

Host NIC full-duplex cần được biểu diễn thành hai tài nguyên: giới hạn gửi và giới hạn nhận. Không cộng lưu lượng gửi và nhận rồi áp chung một giới hạn.

Nguồn topology: §5.1. Các công thức đếm và lưu ý đường nội bộ là diễn giải từ cấu trúc fat-tree.

## 4. Core ideas cần giữ nguyên

**4.1. Tập trung vào flow lớn để hạn chế overhead.** Flow mới đi bằng ECMP. Bản triển khai của paper phát hiện flow lớn ở ngưỡng tốc độ 100 Mbit/s trên NIC 1 Gbit/s, tức 10%. Đây là ngưỡng tốc độ, không phải mặc định “đã truyền 10 MB”.

**4.2. Nhu cầu không đồng nhất với throughput đang đo.** Flow đang đạt 500 Mbit/s có thể chỉ đạt mức đó vì nghẽn trên đường; nếu chuyển đường, nó có thể dùng nhiều hơn. Nếu dành trước đúng 500 Mbit/s rồi flow tăng tốc sau chuyển đường, scheduler đã đánh giá thiếu nhu cầu.

**4.3. Dùng thông tin toàn mạng.** Scheduler theo dõi flow, topology và dung lượng được quy cho các link; đường được chọn phải tính cả nút thắt ở phía sau.

**4.4. Giảm không gian tìm kiếm bằng cấu trúc mạng.** Đặc trưng nổi bật của SA là gán core cho host đích, không gán core độc lập cho từng flow. Các phép đổi chỗ giữ sự phân bố core trong pod.

**4.5. Tận dụng tính cục bộ theo cả không gian lẫn thời gian.** Một phép đổi chỗ chỉ ảnh hưởng flow đi tới hai host; chu kỳ tiếp theo bắt đầu từ nghiệm tốt nhất trước đó.

Nguồn đối chiếu: §2.3, §3.1-3.2, §4.4.

## 5. Thuật toán 1: Demand Estimation

### 5.1. Bài toán mà estimator giải

Đầu vào là nguồn và đích của các flow lớn, không phải giả định đã biết “nhu cầu thật” từ trước. Trong mô hình đồng tốc, chuẩn hóa NIC thành 1. Estimator tìm cách phân chia theo tinh thần max-min fairness khi chỉ giữ giới hạn gửi/nhận:

    sum(d_f với src(f) = i) <= 1, cho mọi host i
    sum(d_f với dst(f) = j) <= 1, cho mọi host j

Các link bên trong fat-tree không xuất hiện trong estimator này. Vì vậy kết quả là demand để scheduler cố bố trí, chưa phải throughput có thể đạt trên đường hiện tại.

Paper tập trung vào flow network-limited. Nếu ứng dụng, đĩa hoặc CPU tự giới hạn tốc độ, không thể mặc nhiên dùng mô hình này như một phép đo chính xác nhu cầu ứng dụng.

### 5.2. Biểu diễn dữ liệu

Paper dùng ma trận M[i,j], mỗi ô có số flow n_ij, demand mỗi flow d_ij và cờ hội tụ. Flow cùng cặp nguồn-đích có cùng demand trong mô hình. Nên lưu thưa khi triển khai.

Nếu một ô chứa 3 flow, đóng góp vào băng thông là 3*d_ij và đóng góp vào số flow là 3. Không được coi mỗi ô khác 0 như chỉ có một flow.

### 5.3. Bước phía gửi

Với nguồn i, giữ nguyên demand của các flow đã bị chốt. Chia đều phần NIC gửi còn lại cho các flow chưa chốt:

    fixed_i = sum(d_f với src(f)=i và converged(f))
    share_i = (1 - fixed_i) / số flow chưa chốt từ i

Gán share_i cho từng flow chưa chốt. Nếu không còn flow chưa chốt thì bỏ qua phép chia.

### 5.4. Bước phía nhận: water filling có trần từ nguồn

Nếu tổng đề xuất đi vào đích j không vượt 1, giữ nguyên. Nếu vượt 1, tìm mức chia a sao cho:

    sum(min(proposal_f, a), với dst(f)=j) = 1

Flow có proposal thấp hơn a không bị tăng lên. Phần còn lại nhận a và được đánh dấu hội tụ. Có thể tìm a bằng cách lặp: loại các flow đã có proposal nhỏ hơn mức chia đều, giữ nguyên demand của chúng, rồi chia dung lượng còn lại cho nhóm chưa loại.

Ví dụ tự dựng: một receiver dung lượng 1 nhận các đề xuất 0.2, 0.8, 0.8. Phân chia đúng là 0.2, 0.4, 0.4. Chia đều 1/3 cho cả ba sẽ tăng sai flow chỉ có thể đề xuất 0.2 ở bước nguồn.

Sau khi receiver giới hạn một số flow, nguồn tương ứng có thể phân lại băng thông cho những flow chưa chốt ở vòng sau.

### 5.5. Giả mã diễn giải

~~~text
ESTIMATE_DEMANDS(F):
    d[f] = 0; converged[f] = false, với mọi f

    repeat:
        old_d = copy(d)

        for mỗi nguồn i có flow:
            A = các flow chưa converged gửi từ i
            fixed = tổng d của các flow đã converged gửi từ i
            if A không rỗng:
                đặt d[f] = (1 - fixed) / |A|, với f thuộc A

        for mỗi đích j có flow:
            incoming = tất cả flow nhận tại j
            if tổng d[incoming] <= 1:
                continue

            R = incoming
            fixed = 0
            repeat:
                share = (1 - fixed) / |R|
                small = các f trong R có d[f] < share
                if small rỗng:
                    break
                fixed += tổng d[small]
                R -= small

            for f trong R:
                d[f] = share
                converged[f] = true

    until d không thay đổi trong sai số epsilon
    return d
~~~

Giả mã theo từng flow để dễ hiểu; phiên bản gộp cặp phải dùng trọng số n_ij. Cờ receiver-limited tạm thời trong Figure 7 khác với cờ converged được giữ qua các vòng. Khi cài đặt cần bảo vệ danh sách rỗng, phép chia cho 0 và sai số số thực.

### 5.6. Ví dụ đã đối chiếu với Figure 4

Ví dụ bốn host, NIC chuẩn hóa thành 1. Các kết quả dưới đây là demand **mỗi flow**, không phải tổng cả cặp:

| Nguồn -> đích | Số flow | Demand mỗi flow sau hội tụ |
|---|---:|---:|
| H0 -> H1 | 1 | 1/3 |
| H0 -> H2 | 1 | 1/3 |
| H0 -> H3 | 1 | 1/3 |
| H1 -> H0 | 2 | 1/3 |
| H1 -> H2 | 1 | 1/3 |
| H2 -> H0 | 1 | 1/3 |
| H2 -> H3 | 1 | 2/3 |
| H3 -> H1 | 2 | 1/3 |

H2 có thể tăng flow tới H3 lên 2/3 sau khi flow tới H0 bị giới hạn ở 1/3. H3 chỉ gửi tổng 2/3 vì receiver H1 đã hết chỗ. Không phải nguồn nào cũng dùng hết NIC.

Đã kiểm tra ví dụ bằng tính toán phân số chính xác và thu được đúng ma trận cuối Figure 4. Đây là kiểm tra nhỏ về cách hiểu estimator, chưa phải tái hiện toàn bộ hệ thống hay thực nghiệm của paper.

Nguồn đối chiếu: §4.1-4.2, Figure 4 và Figure 7, trang 5 và 7.

## 6. Thuật toán 2: Global First Fit

### 6.1. Điều kiện đặt đường

GFF duyệt lần lượt các đường cùng chi phí. Một đường khả thi khi **mọi link có hướng** trên đường còn đủ dung lượng cho demand của flow:

    U_l + d_f < C_l, với mọi l thuộc p

Figure 5 dùng dấu <. Nếu bản triển khai dùng <= kèm epsilon để cho phép vừa khít dung lượng, cần ghi rõ đó là lựa chọn số học, tránh khác nhau âm thầm ở trường hợp biên.

### 6.2. Giả mã diễn giải

~~~text
PLACE_GFF(f):
    if f đã có đường được gán:
        return đường hiện tại

    for p trong danh sách đường cùng chi phí theo thứ tự cố định:
        if mọi link l thuộc p thỏa U[l] + demand[f] < capacity[l]:
            cập nhật reservation trên từng link của p
            lưu đường và trạng thái đã gán cho f
            cài quy tắc forwarding
            return p

    return đường chọn bằng ECMP/hash
~~~

Fallback bằng hash chỉ diễn ra sau khi không tìm được đường phù hợp; khi đó không có bảo đảm mọi demand được đáp ứng. Giả mã ở Figure 5 rất gọn, phải đọc cùng mô tả §4.3 để hiểu việc kiểm tra toàn đường.

### 6.3. Ý nghĩa và giới hạn

- First fit chọn **đường đầu tiên đủ chỗ**, không chọn đường ít tải nhất hay đường có điểm số tốt nhất.
- Flow đã đặt được giữ đường, tránh tính lại toàn bộ và tránh liên tục đổi đường.
- Khi flow hết hạn phải giải phóng reservation.
- Reservation là trạng thái kế toán của scheduler; tự nó không phải bảo đảm băng thông cứng ở phần cứng.
- Thứ tự flow và thứ tự duyệt đường có thể ảnh hưởng nghiệm.
- Nếu thêm việc định kỳ đặt lại mọi flow hoặc chọn least-loaded path, đó là biến thể cần được đặt tên và đánh giá riêng.

Diễn giải triển khai: cần xác định rõ cách làm mới reservation khi demand thay đổi giữa các kỳ; không cộng thêm cùng một demand nhiều lần vào link mà không trừ giá trị cũ.

Nguồn đối chiếu: §4.3, Figure 5 và §4.5, trang 6 và 8.

## 7. Thuật toán 3: Simulated Annealing của Hedera

### 7.1. Biểu diễn trạng thái mới là phần quan trọng

Đặt pi(h) là core dành cho host đích h. Các flow liên pod tới h đi qua core đó. Trong mỗi pod, khởi tạo ánh xạ một-một giữa q host và q core. Phép đổi chỗ hai host trong cùng pod bảo toàn tính một-một.

Nếu tối ưu từng flow độc lập, không gian thô có khoảng q^m cách gán cho m flow liên pod. Nếu xét các hoán vị đích-core trong k pod, không gian bị hạn chế còn (q!)^k cách, kể cả các host chưa có flow. Đây là phép đếm minh họa từ biểu diễn, không phải một bảo đảm rằng biểu diễn mới luôn nhỏ hơn cho mọi m.

Hạn chế không gian giúp tìm kiếm hiệu quả, nhưng có thể loại nghiệm mà một host cần nhận flow qua nhiều core. Không có bảo đảm tìm tối ưu toàn cục cho mọi traffic. Paper nêu các điều kiện đủ trong fat-tree liên quan số flow lớn mỗi host không quá k/2, hoặc ngưỡng flow lớn ít nhất 2/k dung lượng link; phần chứng minh chi tiết được lược bỏ trong paper. Không nên gọi nhận định này là một định lý đã được chứng minh đầy đủ ngay trong bài.

### 7.2. Hàm energy

Với một trạng thái pi:

    U_l(pi) = sum(d_f với l thuộc path(f, pi))
    E(pi) = sum_l max(0, U_l(pi) - C_l)

Energy là tổng demand vượt quá capacity trên các link. Nó không phải max-link-utilization, phương sai tải hay flow completion time.

Ví dụ tự dựng với capacity chuẩn hóa bằng 1:

- Trạng thái A có tải ba link 1.4, 0.9, 1.1: E(A) = 0.4 + 0 + 0.1 = 0.5.
- Trạng thái B có tải 1.1, 1.0, 1.1: E(B) = 0.1 + 0 + 0.1 = 0.2.

E=0 nghĩa các demand đang xét không làm vượt capacity trong mô hình. Điều đó chưa chứng minh TCP thực tế đạt một giá trị goodput cụ thể, cũng chưa bảo đảm chất lượng cho traffic không được đưa vào phép tính.

### 7.3. Sinh hàng xóm

Paper dùng hỗn hợp ba phép đổi chỗ, mỗi loại được chọn với xác suất 1/3:

1. Chọn một pod, đổi core của hai host ngẫu nhiên trong pod.
2. Chọn một edge switch, đổi core của hai host nối vào edge đó.
3. Chọn edge hoặc aggregation switch với xác suất bằng nhau, rồi đổi core của hai host có đường lên core hiện tại đi qua switch được chọn.

Phép thứ ba phải chọn host theo ánh xạ/đường hiện tại. Với trường hợp không đủ hai host hợp lệ, bản triển khai phải có chính sách chọn lại hoặc bỏ bước; paper không đặc tả toàn bộ điều kiện biên này.

### 7.4. Chấp nhận bước tốt và bước xấu

Gọi E là energy hiện tại, E_new là energy của hàng xóm:

    p = 1, nếu E_new < E
    p = exp(c * (E - E_new) / T), nếu E_new >= E và T > 0

T là số vòng còn lại. Đầu quá trình có thể chấp nhận một bước xấu để thoát cực tiểu cục bộ; khi T giảm, bước xấu khó được chấp nhận hơn. Bước có energy bằng nhau có p=1 khi T>0.

Paper báo cáo c=0.5*T0 cho cụm 16 host và c=1000*T0 cho mạng lớn hơn. Đây là tham số thực nghiệm của tác giả, không phải hằng số dùng đúng cho mọi đơn vị energy. Nếu đổi chuẩn hóa demand từ phần NIC sang bit/s, phải hiệu chỉnh tham số tương ứng.

### 7.5. Giả mã diễn giải có xử lý T=0

~~~text
ANNEAL(F, demands, I, previous_best):
    current = previous_best nếu có, nếu không thì khởi tạo ánh xạ
    xây tải link và E(current) theo tập flow/demand hiện tại
    best = bản sao của current

    for T = I, I-1, ..., 1:
        tạo neighbor bằng một trong ba phép đổi chỗ
        tính E_new bằng cập nhật cục bộ

        if E_new < E(best):
            best = bản sao của neighbor

        if E_new < E(current)
           hoặc uniform(0,1) < exp(c*(E(current)-E_new)/T):
            chấp nhận neighbor và cập nhật tải link
        else:
            hoàn tác mọi thay đổi tạm

    return best
~~~

Figure 6 ghi vòng lặp tới 0 nhưng công thức xác suất chia cho T. Ở đây viết lại tới 1 để tránh phép chia cho 0; nếu muốn xử lý bước cuối ở T=0, phải dùng nhánh chấp nhận riêng. Đây là làm rõ điều kiện biên, không phải thay đổi ý tưởng tìm kiếm.

Phải lưu best tách khỏi current, vì SA có thể rời trạng thái tốt để khám phá. Không trả về current cuối cùng một cách mặc định. Nếu thêm dừng sớm tại E=0 hoặc dừng do không cải thiện, đánh dấu đó là biến thể của đồ án.

### 7.6. Cập nhật energy cục bộ

Đổi core của h_a và h_b chỉ đổi đường các flow đi tới hai host đó. Cần:

1. Tập hợp các link trên đường cũ và đường mới của nhóm flow bị ảnh hưởng.
2. Gộp delta tải theo link; trừ demand khỏi đường cũ và cộng vào đường mới.
3. Cập nhật chênh lệch energy trên tập link liên quan:

    delta_E = sum_l [max(0,U_l+delta_l-C_l) - max(0,U_l-C_l)]

4. Giữ thay đổi nếu chấp nhận; nếu không thì hoàn tác.

Các link dùng chung phải được gộp delta trước khi chốt energy. Tính lại mọi flow ở mỗi bước vẫn tạo được một bản tham chiếu đúng nếu làm cẩn thận, nhưng đánh mất lợi thế hiệu năng của paper.

### 7.7. Giữ nghiệm qua các kỳ

Chu kỳ tiếp theo dùng best của kỳ trước làm trạng thái đầu. Tuy nhiên tải link và energy phải được cập nhật theo flow vừa đến, vừa kết thúc và demand mới. Không được tái sử dụng energy cũ nguyên vẹn khi đầu vào đã thay đổi.

Nguồn đối chiếu: §4.4, Figure 6, trang 6-8. Công thức tổng, phép đếm không gian và quy trình delta là diễn giải toán học để triển khai từ mô tả tác giả.

## 8. Độ phức tạp: tách từng đơn vị công việc

| Thành phần | Thông tin trong paper | Cách hiểu khi triển khai |
|---|---|---|
| Demand Estimation | §4.2 ghi O(|F|) | Paper không trình bày chứng minh chặt cho mọi cách cài đặt vòng lặp; không tự động gán con số này cho bản quét lại toàn bộ dữ liệu nhiều lần |
| GFF | Table 1: O((k/2)^2) | Chi phí tìm đường cho một flow mới, với chiều dài đường bị chặn bởi số tầng cố định |
| SA | Table 1: O(f_avg) | Chi phí trung bình của một bước cập nhật cục bộ, không phải toàn bộ I bước |
| Bộ nhớ placement | Table 1: O(k^3 + |F|) | Trạng thái link trong fat-tree và trạng thái các flow; không bao gồm một ma trận host dense N*N do người triển khai tự chọn |

Diễn giải triển khai:

- GFF xử lý m_new flow mới có cận O(m_new*k^2) trong topology số tầng cố định, chưa cộng estimator và cập nhật rule.
- Một swap SA ảnh hưởng a và b flow đến hai host, đường dài tối đa L: cập nhật có chi phí O((a+b)*L). Trung bình suy ra O(f_avg) khi L cố định và chọn host theo cách phù hợp; trường hợp hotspot có thể lớn hơn nhiều.
- Tổng I bước SA gần O(I*f_avg) trung bình, cộng khởi tạo hoặc làm mới tải link và lưu nghiệm tốt nhất.
- Nếu mỗi lần lưu best sao chép toàn bộ ánh xạ N host, bản triển khai còn thêm chi phí O(N) cho mỗi lần cải thiện; cần tính cả chi phí này khi đo hoặc tối ưu cấu trúc lưu.
- Lưu ma trận demand dense tốn O(N^2). Bản sparse có số ô không rỗng không quá số flow.
- Bản estimator cài bằng nhiều vòng quét phải báo số vòng ngoài và vòng water filling; không chứng minh được O(|F|) chỉ bằng việc mỗi vòng có duyệt F.

Khi vấn đáp, luôn ghi “mỗi flow”, “mỗi swap” hay “mỗi scheduling period” bên cạnh Big-O. Table 1 không thay thế phân tích cả hệ thống.

## 9. Vòng điều khiển end-to-end

~~~mermaid
flowchart LR
    A[Flow mới đi bằng ECMP] --> B[Thu thập thống kê ở edge]
    B --> C[Phát hiện flow lớn]
    C --> D[Ước lượng natural demand]
    D --> E{Thuật toán placement}
    E --> F[Global First Fit]
    E --> G[Simulated Annealing]
    F --> H[Cập nhật forwarding]
    G --> H
    H --> B
~~~

Flow hết hạn được gỡ khỏi trạng thái scheduler và reservation. Scheduler dùng OpenFlow để sửa forwarding tại các switch cần thiết; host không phải thay TCP stack.

Thời gian phản ứng không chỉ là thời gian chạy thuật toán:

    độ trễ phản ứng ≈ chờ đo + thu thập thống kê + estimate
                    + placement + cài rule

Công thức trên là mô hình phân rã của người đọc. Bản testbed của paper poll/lập lịch mỗi 5 giây do hạn chế đọc thanh ghi OpenFlow NetFPGA. Không được biến 5 giây thành yêu cầu bản chất của Hedera; cũng không nhầm dự đoán khả thi sub-100ms của tác giả với phép đo end-to-end đã đạt trong testbed đó.

Nguồn đối chiếu: §3, §5.3-5.4, §6.4.5.

## 10. Tác giả đã đánh giá gì?

### 10.1. Môi trường và baseline

- Testbed 16 host, 20 switch 4 cổng dựa trên NetFPGA, link 1 Gbit/s.
- Mô phỏng flow-level tới 8.192 host, k=32.
- So sánh ECMP/static hash, GFF, SA và mạng/switch non-blocking làm mốc tham chiếu.
- Traffic gồm stride, staggered theo xác suất cục bộ, random, random bijection và hotspot.
- Simulator dùng flow đến theo Poisson, kích thước theo phân phối mũ, cập nhật theo tick; có xấp xỉ slow start và AIMD.
- Mỗi thí nghiệm chạy 60 giây, đo băng thông trung bình trong 40 giây giữa.

Chi tiết quan trọng khi tái hiện: §6.2 mô tả baseline static hash theo IP đích trong thực nghiệm testbed. Nó không tự động đại diện cho mọi cấu hình ECMP hiện đại dùng 5-tuple. Nếu đồ án dùng baseline khác, cần công bố rõ.

### 10.2. Những số liệu có thể trích có điều kiện

| Kết quả paper | Điều kiện/giới hạn cần ghi kèm |
|---|---|
| Tới 96% mốc tối ưu và cải thiện tới 113% so với phương pháp tĩnh | Kết quả được báo cáo cho các thí nghiệm mô phỏng 8.192 host; không phải mọi workload |
| Tới 4 lần băng thông ECMP | Kết quả tốt nhất trong testbed; không phải mức cải thiện trung bình chung |
| Demand estimator: 250.000 flow trên 27.648 host khoảng 199,43 ms | Table 4; máy, cài đặt và bốn luồng thực thi của tác giả |
| SA với 50.000 flow và 10.000 vòng khoảng 55,741 ms | Table 5, trường hợp 8.192 host; chỉ runtime SA, không phải cả vòng điều khiển |

Không dùng “96% tối ưu” như một approximation guarantee. Mốc so sánh non-blocking không phải nghiệm tối ưu chính xác được chứng minh cho từng instance của mạng ban đầu.

### 10.3. Data shuffle 120 GB: Table 2

| Chỉ tiêu | ECMP | GFF | SA | Control/non-blocking |
|---|---:|---:|---:|---:|
| Tổng thời gian shuffle (s) | 438,44 | 335,50 | 335,96 | 306,37 |
| Băng thông bisection trung bình (Gbit/s) | 2,811 | 3,891 | 3,843 | 4,443 |

Từ các số đã làm tròn trong bảng, GFF tăng băng thông khoảng 38,42% và giảm thời gian khoảng 23,48% so với ECMP. Paper diễn đạt mức tăng băng thông khoảng 39%. Đây là tính lại từ Table 2, không phải kết quả mới của dự án.

SA không thắng GFF trong mọi chỉ số: ngay Table 2, GFF nhỉnh hơn một chút ở thời gian shuffle. Nên khảo sát nhiều workload thay vì mặc định SA luôn thắng.

Nguồn đối chiếu: §5.5, §6.1-6.4, Figure 9-11, Table 2-5.

## 11. Giới hạn và điều không được suy diễn

1. **Không phải tối ưu toàn cục có bảo đảm.** GFF và SA là heuristic. Trạng thái SA có thể loại một số cách bố trí flow.
2. **Không giải quyết nút thắt không thể tránh.** Nếu tổng demand tới một receiver vượt NIC của nó, đổi đường không làm NIC nhanh hơn.
3. **Phản ứng có độ trễ.** Flow ngắn có thể kết thúc trước khi scheduler can thiệp.
4. **Demand dựa trên mô hình.** Network-limited, chia sẻ công bằng ở đầu gửi/nhận và thông tin flow đủ chính xác là các giả định có tác động.
5. **Simulator không phải TCP đầy đủ.** Paper không mô phỏng từng packet, buffer, packet loss và RTO đầy đủ; ACK chiều ngược cũng được lược bỏ. Không suy ra kết quả packet latency, loss hay p99 queueing delay từ mô hình này.
6. **Ngưỡng phát hiện có thể bỏ sót flow đang bị bóp tốc độ.** Đây là suy luận triển khai cần khảo sát: một flow có tiềm năng lớn nhưng tốc độ đo dưới ngưỡng có thể chưa được đưa vào scheduler.
7. **Đổi đường cần cẩn thận.** Packet reordering và cập nhật rule là vấn đề của bản triển khai; không tự suy ra cơ chế chống reordering từ việc paper giữ đường theo flow.
8. **Số liệu cũ không phải mục tiêu phải khớp.** Mô hình traffic, baseline, đơn vị, số flow, cơ chế TCP và thời gian đo thay đổi đều có thể đổi kết quả.

Nguồn đối chiếu: §4.1, §4.4, §5.4-5.5, §6.3. Những câu được ghi là suy luận không phải tuyên bố thực nghiệm của tác giả.

## 12. Những điểm dễ làm sai khi triển khai đồ án

| Cách làm sai | Cách phân biệt/khắc phục |
|---|---|
| Dùng throughput đo được trực tiếp như natural demand | Có estimator riêng; dữ liệu đo dùng cho phát hiện và trạng thái vận hành |
| Mặc định elephant là flow vượt một số MB | Ghi rõ paper dùng ngưỡng tốc độ; size threshold là một biến thể |
| GFF chọn đường ít tải nhất | Bản gốc là đường đầu tiên thỏa mọi link |
| Định kỳ đưa mọi flow qua GFF để đổi lại đường | Bản gốc giữ đường flow đã đặt; biến thể phải tách riêng |
| SA đổi core độc lập của một flow | Bản Hedera đổi ánh xạ core của hai host đích |
| SA chỉ có swap ngẫu nhiên trong pod | Muốn tái hiện đầy đủ cần hỗn hợp ba neighbor như §4.4 |
| Energy là max utilization | Bản gốc dùng tổng phần vượt capacity |
| Tính lại mọi link, mọi flow trong mỗi swap nhưng vẫn ghi O(f_avg) | Phân tích đúng chi phí bản cài đặt, hoặc dùng delta update |
| Lưu best bằng tham chiếu mutable đến current | Sao chép hoặc lưu snapshot đủ để best không bị đổi theo |
| Warm start cả energy cũ sau khi flow đổi | Giữ ánh xạ, làm mới tải/energy theo đầu vào mới |
| Dùng đúng c của paper sau khi đổi đơn vị | Giữ chuẩn hóa hoặc hiệu chỉnh tham số |
| Gọi max-min allocation theo link là mô phỏng TCP Reno của paper | Đây là mô hình khác; cần công bố giới hạn |
| Dùng kết quả throughput của flow simulator để khẳng định p99 latency | Cần mô hình packet/queue phù hợp để có loại kết luận đó |

## 13. Đặc tả tối thiểu để chuyển sang lập trình

Đây là đề xuất thiết kế cho dự án, không phải cấu trúc code gốc của tác giả.

| Module | Trách nhiệm |
|---|---|
| topology | Tạo fat-tree, phân biệt đường nội bộ và liên pod, link có hướng |
| workload | Sinh danh sách flow với seed, thời gian bắt đầu, kích thước, nguồn-đích |
| flow_model | Cập nhật rate, số byte gửi, flow kết thúc theo mô hình công bố |
| detector | Phân loại flow lớn bằng số đo và ngưỡng khai báo |
| demand_estimator | Tạo demand từ tập flow lớn, có kiểm tra giới hạn NIC |
| ecmp | Hash ổn định, công bố trường header và cách ánh xạ đường |
| global_first_fit | Placement, reservation, giữ đường, xử lý expiry và fallback |
| annealing | State đích-core, ba neighbor, acceptance, best snapshot, warm start |
| metrics | Tách throughput, demand, energy, runtime và số lần đổi đường |
| experiments | Cùng workload/seed cho các phương pháp, cấu hình và xuất dữ liệu |

Các kiểm tra có ý nghĩa trước khi chạy thí nghiệm:

1. Đếm đúng host/switch/path của fat-tree; xác nhận đường đi hợp lệ.
2. Ví dụ Figure 4 và ví dụ receiver 0.2, 0.8, 0.8.
3. Tổng demand gửi/nhận không vượt NIC trong estimator.
4. Mỗi pod giữ ánh xạ một-một sau một chuỗi swap.
5. Delta energy bằng energy tính lại từ đầu trên mạng nhỏ.
6. Reject swap phục hồi đầy đủ state và tải link.
7. Best trả về không xấu hơn trạng thái khởi tạo trong cùng một input cố định.
8. Flow hết hạn giải phóng reservation đúng một lần.

## 14. Câu hỏi thực nghiệm và vấn đáp

Các câu hỏi thực nghiệm đề xuất:

- Khi traffic liên pod và có ít flow lớn, Hedera cải thiện so với ECMP bao nhiêu?
- Khi nhiều flow nhỏ hoặc tải cục bộ tăng, lợi ích giảm thế nào?
- Tăng I cải thiện energy và throughput ra sao, đổi lại runtime và số lần đổi đường bao nhiêu?
- Chu kỳ lập lịch dài, thống kê trễ và sai số demand ảnh hưởng thế nào?
- Thay state đích-core bằng per-flow SA có đánh đổi ra sao? Chỉ thử như một ablation riêng, không thay bản gốc âm thầm.
- Full recomputation và delta update có cho cùng energy nhưng khác runtime không?

Các điểm phải giải thích được khi vấn đáp:

- Vì sao có nhiều đường mà ECMP vẫn có thể nghẽn?
- Natural demand khác measured throughput ở đâu?
- Vì sao receiver phải giữ nguyên flow đã sender-limited trong water filling?
- Vì sao state SA là đích-core, và khi nào cách hạn chế này có thể bỏ nghiệm tốt?
- Vì sao cần nhận bước xấu và lưu best riêng?
- Vì sao E=0 không đồng nghĩa với “đã chứng minh throughput TCP tối ưu”?
- Big-O đang tính một flow, một swap hay cả kỳ lập lịch?
- Mô hình mô phỏng cho phép và không cho phép kết luận về những metric nào?

## 15. Bản đồ đọc lại paper

| Nội dung | Vị trí |
|---|---|
| ECMP collision và measured rate khác natural demand | §2.2-2.3, Figure 2-3, trang 3-4 |
| Kiến trúc và ngưỡng tốc độ | §3.1-3.2, trang 4 |
| Demand Estimation | §4.2, Figure 4 và Figure 7, trang 5 và 7 |
| Global First Fit | §4.3, Figure 5, trang 6 |
| SA, energy, acceptance | §4.4, Figure 6, trang 6-8 |
| Ba neighbor, delta update, warm start, giới hạn state | §4.4, trang 7-8 |
| Big-O và bộ nhớ placement | Table 1, §4.5, trang 8 |
| OpenFlow và chu kỳ 5 giây | §5.3-5.4, trang 9-10 |
| Mô hình simulator và giới hạn | §5.5, trang 10 |
| Workload và testbed | §6.1-6.3, Figure 9, Table 2, trang 10-12 |
| Quy mô lớn, runtime, overhead | §6.4, Figure 10-11, Table 3-5, trang 12-14 |

**Thông điệp dùng để bảo vệ:** đóng góp của Hedera là kết hợp đo đạc, suy ra demand và lựa chọn đường có thông tin toàn mạng; với SA, biểu diễn trạng thái có cấu trúc cùng cập nhật cục bộ làm cho việc tối ưu đủ nhanh để có ích. Giá trị đồ án nằm ở tái hiện đúng cơ chế và chỉ ra điều kiện mà lợi ích vượt chi phí điều khiển.
