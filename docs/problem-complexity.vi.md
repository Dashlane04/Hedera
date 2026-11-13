# Hedera: phát biểu bài toán và phân tích độ phức tạp

Tài liệu bổ sung cho slide 4–8 và phần vấn đáp. Phân tích dựa trên bản mã trong `sim/hedera-core.cc`, dữ liệu `results/scheduler-v2.csv` và paper Hedera (NSDI 2010). Các công thức tối ưu và cận của bản C++ dưới đây là diễn giải của đồ án, không phải công thức được chép nguyên từ paper.

## 1. Bài toán cần giải quyết

Mạng fat-tree có nhiều đường cùng độ dài giữa hai host. ECMP dùng hash để chọn đường cho flow nhưng không kiểm tra các flow khác đang tranh những link nào. Vì vậy, hai flow có thể cùng đi qua một link đã đầy trong khi đường khác còn dung lượng. Hedera thu thập thông tin toàn mạng, suy nhu cầu của các flow lớn và chọn lại đường để giảm tranh chấp đó.

Quyết định cần tìm là **đường đi của flow**. Controller không trực tiếp đặt tốc độ truyền TCP, cửa sổ tắc nghẽn hay lịch phát từng packet. TCP phản ứng với đường mà controller cài, rồi simulator mới đo kết quả truyền thực tế.

### 1.1. Đầu vào của một kỳ placement

| Ký hiệu | Ý nghĩa và đơn vị |
|---|---|
| G = (V, A) | Đồ thị mạng, A là tập link có hướng |
| E = \|A\| | Số link có hướng, dùng trong công thức độ phức tạp |
| C_ℓ | Dung lượng link ℓ, đơn vị tốc độ |
| N | Số host |
| 𝓕, F = \|𝓕\| | Tập và số flow lớn được detector chọn ở kỳ hiện tại |
| s_f, t_f | Host nguồn và đích của flow f |
| d_f | Natural demand đã ước lượng cho flow f, đơn vị tốc độ |
| P_f | Tập đường ngắn nhất hợp lệ giữa s_f và t_f |
| A_old, π_old | Reservation GFF hoặc mapping SA từ kỳ trước |

Trong core hiện tại, mọi capacity được chuẩn hóa theo NIC: capacity link bằng 1. Với cấu hình link/NIC 20 Mbit/s, demand 0,5 tương ứng 10 Mbit/s trong mô hình. Demand 0,5 không khẳng định PacketSink sẽ nhận đúng 10 Mbit/s.

Đây là snapshot tại một kỳ điều khiển. Bộ lập lịch không được biết trước thời điểm hoàn thành hay toàn bộ tương lai của traffic. Estimator hiện dùng endpoint của các flow đã được phát hiện; nó không đọc kích thước file để biết nhu cầu ứng dụng chính xác.

### 1.2. Đầu ra

Với mỗi flow đang xét, trả về một đường `p_f ∈ P_f`. Trong mỗi phiên bản định tuyến, flow dùng một đường, không đồng thời chia tỷ lệ packet của cùng flow qua nhiều đường. Kỳ sau có thể thay đổi đường. Packet của phiên bản cũ và mới vẫn có thể cùng tồn tại trên mạng.

Flow chưa thuộc tập Hedera tiếp tục dùng ECMP. Trong GFF, flow không đặt được reservation cũng dùng ECMP và có thể được thử lại ở kỳ sau. Vì vậy, “không đặt được” không có nghĩa là bỏ flow hoặc ngừng truyền dữ liệu.

## 2. Mô hình tối ưu lý tưởng và ràng buộc

Một cách phát biểu bài toán tốc độ để giải thích mục tiêu là chọn đường `p_f` và tốc độ lý tưởng `r_f` nhằm:

```text
maximize    Σ_f r_f
subject to  p_f ∈ P_f                    với mọi flow f
            0 ≤ r_f ≤ d_f                với mọi flow f
            Σ_{f: ℓ∈p_f} r_f ≤ C_ℓ      với mọi link có hướng ℓ
            Σ_{f: s_f=u} r_f ≤ C_u^tx    với mọi sender u
            Σ_{f: t_f=v} r_f ≤ C_v^rx    với mọi receiver v
```

Đây là mô hình giải thích do đồ án phát biểu. Bản triển khai **không gọi solver** để giải tối ưu toàn cục mô hình này và không trực tiếp cài các `r_f` vào TCP. Nó suy `d_f`, rồi dùng GFF hoặc SA để chọn `p_f`.

Các giới hạn gửi và nhận là hai tài nguyên riêng của NIC full-duplex. Một host có thể vừa gửi vừa nhận ở tốc độ NIC. Không cộng tốc độ hai chiều rồi áp cùng một giới hạn.

Nếu chỉ lập lịch các flow lớn, mô hình trên chưa tính đủ flow nhỏ, ACK và overhead giao thức. Có thể xây dựng mô hình rộng hơn với tải nền và dung lượng còn lại, nhưng code hiện tại không trừ một vector tải nền đầy đủ khỏi capacity của mọi link. Vì vậy, tính khả thi của mô hình demand không phải cam kết hiệu năng cho toàn bộ packet traffic.

### 2.1. Nếu cần trình bày dưới dạng biến nhị phân

Đặt `x_fp ∈ {0,1}` là chọn đường p cho f và `y_fp ≥ 0` là tốc độ f đặt trên đường p:

```text
Σ_{p∈P_f} x_fp = 1
0 ≤ y_fp ≤ d_f x_fp
r_f = Σ_{p∈P_f} y_fp
Σ_f Σ_{p∈P_f: ℓ∈p} y_fp ≤ C_ℓ
```

Kết hợp với giới hạn NIC ở trên, đây là một phát biểu tuyến tính hỗn hợp nguyên cho bài toán lý tưởng trên tập đường ứng viên. Điều kiện nhị phân buộc mỗi flow có tối đa một đường mang tốc độ dương. Mô hình chỉ dùng để xác định rõ biến quyết định và ràng buộc; đồ án chưa dùng nó làm oracle để tính khoảng cách đến nghiệm tối ưu.

### 2.2. Aggregate goodput và bisection bandwidth

`Σ r_f` mô tả tổng tốc độ của tập flow. Khi đánh giá bisection, phải chỉ rõ phép chia host và chỉ đếm traffic đi qua phép chia đó, kèm quy ước một hay hai chiều. Hai đại lượng này có thể khác nhau khi workload có traffic nội edge hoặc nội pod.

Bản ns-3 thu application payload goodput và chỉ tiêu payload qua host half-cut riêng. Slide kết quả chính hiện dùng **application goodput**. Không đổi tên chỉ tiêu này thành bisection bandwidth chỉ vì paper nhấn mạnh bisection.

## 3. GFF và SA thực sự tối ưu điều gì?

### 3.1. Estimator cung cấp demand, không chọn đường

Estimator chia sẻ capacity ở NIC gửi và nhận, lặp đến khi vector demand ổn định. Nó bỏ qua nút thắt fabric ở bước suy natural demand. Nhờ đó, một flow đang bị ECMP kìm ở 0,3 NIC vẫn có thể có demand cao hơn 0,3.

Mô hình này phù hợp nhất với các flow còn dữ liệu để gửi. Với flow bị ứng dụng giới hạn, việc chỉ nhìn endpoint không đủ để biết chính xác offered load. Đây là một lý do cần thí nghiệm ablation, thay vì mặc định natural demand luôn tốt hơn measured rate.

### 3.2. GFF: kiểm tra khả năng đặt thêm reservation

Gọi `U_ℓ^res` là tổng demand trên các đường đã được GFF giữ. Với flow chưa có reservation, GFF duyệt đường theo thứ tự và chọn đường đầu tiên thỏa:

```text
U_ℓ^res + d_f ≤ C_ℓ + 10^(-12)    trên mọi link ℓ của đường đó.
```

GFF không so sánh toàn bộ nghiệm theo một hàm mục tiêu rồi chọn nghiệm tốt nhất. Nó giải quyết từng quyết định đặt thêm bằng một quy tắc tham lam. Reservation cũ còn hoạt động giữ nguyên đường, ngay cả khi demand mới tăng.

Ba giới hạn cần nói rõ:

- Thứ tự flow và thứ tự đường ứng viên ảnh hưởng kết quả.
- Nhu cầu tăng có thể làm các reservation cũ quá tải mà GFF không tự sắp xếp lại chúng.
- Flow fallback dùng ECMP nhưng không được cộng vào reservation. `U^res` vì thế không đại diện toàn bộ tải mà mạng sẽ chuyển tiếp.

Code dùng điều kiện bao gồm dấu bằng và tolerance. Đây là biến thể biên so với dấu `<` ở Figure 5 của paper.

Ví dụ cho tính tham lam: xét hai đường có bottleneck độc lập, capacity mỗi đường bằng 1, bốn flow có demand lần lượt 0,4; 0,4; 0,6; 0,6 và NIC hai đầu không tranh chấp. GFF có thể đặt hai flow đầu lên đường 0 thành 0,8, flow thứ ba lên đường 1 thành 0,6, rồi flow cuối không còn chỗ reservation. Trong khi đó, ghép 0,4 + 0,6 trên mỗi đường sẽ đặt được cả bốn. Ví dụ chỉ chứng minh giới hạn của quy tắc first fit, không phải một kết quả đo TCP.

### 3.3. SA: giảm tổng phần demand vượt capacity

SA dùng state `π(h)` gán một core cho host đích h. Trong từng pod, mapping là hoán vị của q core. Flow liên pod tới cùng một đích dùng cùng core đó; flow nội pod giữ baseline.

Với toàn bộ tập flow lớn đang xét:

```text
U_ℓ(π) = Σ_{f: ℓ∈p_f(π)} d_f
H(π)   = Σ_ℓ max(0, U_ℓ(π) − C_ℓ)
```

Ở đây dùng H để phân biệt **energy** với E là **số link** trong công thức độ phức tạp. Slide SA dùng ký hiệu E cho energy theo cách viết thông dụng của paper.

SA tìm mapping có H nhỏ trong số các state đã khảo sát. Hàm H là tổng phần quá tải, không phải tổng goodput, không phải maximum link utilization, và không trực tiếp tối ưu FCT. Một flow góp demand trên nhiều link nên phần overload có thể được cộng ở nhiều vị trí.

Một swap chỉ đổi core của hai host đích. Mọi flow tới hai đích đó có thể đổi đường. Code tính delta trên các link bị ảnh hưởng, chấp nhận bước tốt hơn và đôi khi nhận bước xấu hơn theo nhiệt độ. Nó lưu best riêng, rồi trả best sau I bước. Với ngân sách I hữu hạn, không có chứng nhận nghiệm tối ưu toàn cục.

**H = 0 chỉ khẳng định**: demand của tập flow đang xét vừa các capacity trong mô hình đường đó. H không thể phản ánh đầy đủ ACK, retransmission, slow start, RTO, hàng đợi, reordering và flow chưa được detector chọn. Vì vậy, hai mapping có H = 0 vẫn có thể cho goodput TCP khác nhau.

### 3.4. Phép đo cuối cùng trong ns-3

```text
goodput = 8 × số byte payload ứng dụng nhận trong [t0,t1] / (t1−t0).
```

Nếu tính Mbit/s thì chia thêm 10^6. Byte ứng dụng nhận không bao gồm TCP/IP header hoặc bản sao retransmission bị TCP loại. Đây là kết quả thực nghiệm sau khi ứng dụng, TCP và mạng tương tác, không phải giá trị suy ra từ energy.

Mục tiêu của Hedera là cải thiện sử dụng băng thông với overhead nhỏ. Quy trình đánh giá của đồ án phải kiểm tra cả chất lượng truyền dữ liệu và chi phí lập lịch. Chỉ chứng minh H giảm là chưa đủ để chứng minh ứng dụng truyền nhanh hơn.

## 4. Ký hiệu cho độ phức tạp

| Ký hiệu | Ý nghĩa |
|---|---|
| k | Radix của fat-tree |
| N = k³/4 | Tổng số host |
| q = (k/2)² | Số core, số host mỗi pod, số đường ngắn nhất liên pod |
| E = 6N | Số link có hướng trong fat-tree đầy đủ hiện tại, kể cả host links |
| L ≤ 6 | Số link trên một đường: 2, 4 hoặc 6 |
| F | Số flow lớn của kỳ hiện tại |
| S | Số reservation còn lưu khi bắt đầu kỳ GFF, trước khi loại flow hết hoạt động |
| Fᵤ | Số flow hiện tại chưa có reservation, kể cả flow fallback được thử lại |
| I | Số bước/nhiệt độ SA |
| a_i | Số flow liên pod tới hai đích được chọn ở bước SA thứ i |
| D_i | Số link xuất hiện trong delta của bước i, không quá min(E, 2a_iL) |
| B ≤ I | Số lần phát hiện best tốt hơn và sao chép mapping |
| R | Số vòng estimator thực sự thực hiện |

Các logarithm trong cận dưới hiểu là `log(2+n)` để tránh trường hợp tập rỗng hoặc một phần tử. k, N, q, E không độc lập với nhau. Cần giữ L khi giải thích số lần truy cập link; sau đó mới có thể dùng L ≤ 6 để rút gọn.

## 5. Demand estimator: các vòng lặp không biến mất

`EstimateDemands` tạo danh sách flow outgoing/incoming cho từng host, vector demand và frozen. Khởi tạo tốn O(N + F) thời gian và bộ nhớ.

Ở mỗi vòng ngoài:

1. Sao chép demand cũ: O(F).
2. Quét các sender và flow đi ra để chia proposal: O(N + F).
3. Quét các receiver và flow đi vào: ít nhất O(N + F).
4. Receiver quá tải chạy water filling bằng nhiều lượt lọc danh sách.
5. So vector demand mới/cũ để kiểm tra hội tụ: O(F).

Gọi d_v là số flow vào receiver v và w_{v,r} là số lượt lọc ở receiver đó trong vòng r. Một cận theo số lần thực thi là:

```text
T_est = O(N + F + Σ_{r=1..R} [N + F + Σ_v w_{v,r} d_v]).
```

Mỗi lượt lọc không kết thúc phải loại ít nhất một phần tử, nên `w_{v,r} ≤ d_v` khi d_v > 0. Từ đó có cận bảo thủ:

```text
T_est = O(R [N + F + Σ_v d_v²]) ⊆ O(R [N + F + F²]).
```

Đây là upper bound của cách quét lặp hiện tại, không khẳng định mọi input đều đạt cận đó. Outer loop có guard `2F+10`, rồi báo lỗi nếu chưa hội tụ. Guard là giới hạn vận hành, không tự nó chứng minh một định lý hội tụ cho mọi traffic. Paper trình bày estimator O(F), nhưng không dùng nhận định ấy thay cho việc đếm các vòng lặp của bản C++ này.

## 6. GFF: chi phí một flow và cả kỳ

### 6.1. Phần tìm đường, bỏ chi phí container

Flow khác pod có q đường ứng viên, mỗi đường dài không quá L. Một phép thử đọc các tải link rồi có thể cộng reservation. Vì vậy phần tìm kiếm cho một flow chưa giữ đường có cận O(qL). Fᵤ flow có cận O(FᵤqL).

`Candidates` tạo sẵn toàn bộ vector đường ứng viên trước khi vòng first fit bắt đầu. Ngay cả khi đường đầu tiên hợp lệ, vẫn có chi phí tạo O(qL) trong code hiện tại. Không khẳng định best case O(L) cho toàn bộ đoạn này.

Ngoài tìm đường, một kỳ còn phải loại reservation hết hoạt động, khởi tạo tải E link, dựng lại tải các reservation đang giữ và trả kết quả cho F flow. Nếu tạm coi phép tra tập/map là O(1), với S = O(F), phần tổng thể là:

```text
T_GFF,abstract = O(E + FL + FᵤqL).
```

Với L là hằng số, thành O(E + F + Fᵤk²). Chỉ được nói O(k²) khi đang nói **phần đặt một flow**, không phải toàn bộ kỳ xử lý F flow.

### 6.2. Thêm cấu trúc dữ liệu của bản C++

Code dùng `std::set` cho active flow, `std::map` cho reservation/result và `std::map<pair<node,node>,linkId>` cho tra link. Một cận bảo thủ của cả kỳ là:

```text
T_GFF = O((F + S) log(2+F+S)
          + E
          + FL log(2+E)
          + FᵤqL log(2+E)).
```

S được giữ riêng vì ở kỳ mới có thể rất nhiều flow cũ vừa hết hoạt động, trong khi F hiện tại nhỏ. Khi giả định S = O(F), công thức rút gọn không còn cần S. Cận này bao gồm copy đường ở kết quả và sinh candidate vì L ≥ 1, log được quy ước ít nhất hằng số.

GFF giữ các đường cũ nên một kỳ có ít flow cần thử có thể rẻ hơn một lần cold start. Microbenchmark hiện tại tạo GFF mới ở mỗi mẫu, vì vậy đo **cold placement** với Fᵤ = F, không đại diện chi phí mọi kỳ ổn định.

## 7. SA: vì sao delta nhanh và vì sao vẫn tốn I bước?

### 7.1. Khởi tạo và kết thúc

Mỗi lần gọi `Anneal` vẫn phải kiểm tra mapping, dựng đường theo demand hiện tại, tính tải và energy, rồi tạo chỉ mục incoming theo host. Có thể warm start mapping nhưng không tái sử dụng một mảng tải cũ với demand đã thay đổi.

Với container của code hiện tại, một cận cho khởi tạo và các phép tính đầy đủ ở cuối là:

```text
T_0 = O(N log(2+q) + E + F log(2+F) + FL log(2+E)).
```

Term N log q đến từ việc kiểm tra các hoán vị bằng set. Đầu ra paths được tạo trong map theo flow id, nên có term F log F.

### 7.2. Chi phí một bước i

Một swap chỉ ảnh hưởng flow liên pod tới hai destination được chọn. Chỉ mục incoming tìm nhóm này mà không quét toàn bộ F flow. Nếu nhóm có a_i flow, code đọc đường cũ và đường mới của chúng, gộp delta, rồi tính thay đổi overload trên D_i link.

Tuy vậy, bước i còn tạo vector eligible. Tùy kiểu neighbor, code quét các host trong edge hoặc tối đa q host của pod. Một cận bảo thủ là O(q), không phải luôn O(1).

Với map tra link và map delta:

```text
T_i = O(q + a_iL [log(2+E) + log(2+D_i)] + D_i).
```

Nếu tìm được best mới, sao chép thêm N phần tử mapping, tốn O(N). Khi mọi destination có số flow liên pod tương đối đều, chi phí cập nhật đường trung bình liên quan đến `f_avg = F_inter/N`; một swap tác động xấp xỉ hai nhóm destination. Nếu traffic dồn vào một đích, a_i có thể lớn tới F. Không thay a_i bằng một hằng số cho mọi workload.

### 7.3. Chi phí cả lần gọi

```text
T_SA = O(T_0
         + Iq
         + Σ_i {a_iL [log(2+E) + log(2+D_i)] + D_i}
         + BN).
```

Bỏ chi phí container, phần chính được dùng trên slide là:

```text
O(E + FL + Iq + LΣ_i a_i + BN).
```

E = Θ(N) trong topology này nên term khởi tạo N đã nằm trong E. Một cận bảo thủ hơn dùng a_i ≤ F là `O(T_0 + I[q + FL log(2+E)] + BN)` vì D_i ≤ E và L ≥ 1. Đây là cận trên, không phải mô tả một workload bình thường.

Vì vậy, độ phức tạp O(f_avg) ở mức cập nhật cục bộ trong paper không có nghĩa toàn bộ scheduler trả kết quả trong O(f_avg) độc lập với I, cũng không chứng minh code C++ hiện tại độc lập với k.

### 7.4. Chi phí kiểm chứng khác chi phí vận hành

Khi `checkEnergy=1`, mỗi bước có swap hợp lệ tính lại đường, load và full energy để đối chiếu delta. Phần thêm có cận O(E + F log(2+F) + FL log(2+E)) mỗi bước kiểm tra. Chế độ này hữu ích để kiểm chứng tính đúng, nhưng tắt khi đo hiệu suất cập nhật delta. Benchmark dùng `false`.

## 8. Không gian tìm kiếm và bộ nhớ

Nếu mỗi flow liên pod tự chọn một trong q core thì có q^F_inter tổ hợp đường, trước khi xét ràng buộc. SA dùng mapping đích–core là hoán vị theo pod, có tối đa `(q!)^k` mapping đầy đủ. Những mapping không có traffic có thể tạo nhiều state tương đương về đường thực tế.

Ví dụ với k = 4, F_inter = 16, mỗi destination có đúng một flow liên pod: chọn core độc lập có 4^16 = 4.294.967.296 tổ hợp, còn mapping hoán vị có (4!)^4 = 331.776 state. So sánh này dùng đúng điều kiện một flow tới mỗi destination. Khi F nhỏ, không thể lấy hai công thức để kết luận mapping lúc nào cũng có số state ít hơn.

Mapping có cấu trúc cũng hạn chế nghiệm: mọi flow liên pod cùng destination dùng chung core, và các destination trong một pod nhận core khác nhau. SA không khảo sát mọi cách đặt từng flow độc lập. Đây là đánh đổi thuật toán, không phải bảo đảm giữ lại mọi nghiệm tối ưu.

Với L bị chặn bởi 6, bộ nhớ core ở trạng thái ổn định thường tóm tắt là O(E + N + F). Chi tiết hơn:

- GFF dùng topology, tải, reservation cũ, result và candidate tạm: O(E + N + S + F + qL).
- SA dùng mapping current/best, incoming, đường và tải, affected/delta tạm: O(E + N + F) khi L hằng số.
- Estimator dùng danh sách thưa và các vector flow: O(N + F).

Không cộng bộ nhớ packet/event/queue/TCP buffers/log của ns-3 vào công thức rồi gọi đó là memory của GFF hoặc SA. Cũng không lấy bộ nhớ core để dự đoán RAM của toàn bộ mô phỏng packet-level.

## 9. Đánh đổi GFF–SA có số đo hỗ trợ

| Tiêu chí | GFF | SA |
|---|---|---|
| Quyết định | First fit cho flow chưa có reservation | Đổi mapping của các đích qua I bước |
| Trạng thái cũ | Giữ đường của reservation còn hoạt động | Warm start nhưng có thể đổi mapping |
| Hạn chế chính | Phụ thuộc thứ tự, có thể giữ bố trí kém | State bị giới hạn, ngân sách hữu hạn, phụ thuộc random seed |
| Điều khiển chi phí | Số flow cần thử và số candidate | I, số flow bị ảnh hưởng, số lần lưu best |
| Kết quả cần kiểm tra | Goodput/FCT và route churn | Goodput/FCT và route churn, cùng runtime |
| Bảo đảm tối ưu goodput | Chưa có | Chưa có |

Microbenchmark hiện có 120 dòng: 3 quy mô × 4 số flow × 5 seed × 2 phương pháp. Đây là benchmark thuật toán cô lập, không phải 120 lần chạy traffic ns-3. Chỉ lấy nhóm F = 1.024 để minh họa:

| Số host | GFF median placement (ms) | SA median placement (ms), I = 1.000 |
|---:|---:|---:|
| 16 | 0,793716 | 44,8918 |
| 54 | 1,564120 | 23,3604 |
| 128 | 2,490240 | 14,9894 |

Đo bằng `steady_clock`, trong build Release chạy cô lập. Mỗi nhóm có 5 seed, lấy median của `placement_us` rồi đổi sang ms. Estimator được đo riêng trước đó nên các số trên không bao gồm estimator. Topology và traffic đã tạo trước vùng đo. Việc tạo GFF/khởi tạo SA nằm trong vùng placement được đo; kiểm chứng energy sau placement nằm ngoài vùng đo.

Số flow trong microbenchmark là input tổng hợp được đưa trực tiếp vào core, không đi qua detector ngưỡng 10%. Ở mật độ cao, nhiều flow có natural demand thấp hơn ngưỡng detector của mô phỏng mạng. Vì vậy bảng này kiểm tra chi phí xử lý của thuật toán dưới tải đầu vào tổng hợp, không khẳng định có đúng 1.024 flow cùng đủ điều kiện elephant trong một run ns-3 của cấu hình tương ứng.

Không kết luận “SA nhanh hơn khi mạng lớn hơn”. Ở F cố định, số flow trung bình tới một host giảm từ 64 xuống 8 khi tăng N từ 16 lên 128, làm chi phí delta có thể giảm. Đây là thay đổi mật độ traffic đồng thời với thay đổi quy mô. Thêm vào đó, code chọn hệ số chấp nhận khác giữa 16 host và các quy mô khác, nên không quy toàn bộ chênh lệch runtime cho một nguyên nhân duy nhất.

Ở nhóm 128 host, SA tốn khoảng 6,02 lần thời gian placement của GFF. Tỷ lệ runtime này không có nghĩa goodput tăng hay giảm 6,02 lần. Hai phép đo trả lời hai câu hỏi khác nhau.

Thời gian CPU thực không tự làm đồng hồ sự kiện ns-3 tiến. `controlDelay` là độ trễ mô phỏng được đặt riêng. Không tuyên bố đo CPU 15 ms đồng nghĩa controller trong mô hình luôn phản ứng sau đúng 15 ms. Một mô hình controller gắn trực tiếp latency với thời gian xử lý là phần mở rộng chưa triển khai.

## 10. Các câu trả lời nên chuẩn bị

**Thầy hỏi: “Em tối ưu cái gì?”**

Em giải quyết chọn đường cho các flow lớn để cải thiện sử dụng băng thông. GFF dùng quy tắc đặt reservation đầu tiên còn đủ capacity. SA giảm tổng demand vượt capacity trong mô hình. Em đánh giá hiệu quả cuối bằng goodput/FCT đo trong ns-3, không coi energy là goodput.

**“Vì sao không dùng đúng tốc độ đang đo làm demand?”**

Vì tốc độ đó có thể đã bị nút thắt đường hiện tại kìm lại. Estimator suy mức chia sẻ theo NIC hai đầu để tránh dành trước quá ít capacity sau khi chuyển đường. Tuy nhiên demand vẫn là mô hình, nên em có ablation natural/measured thay vì giả định nó luôn chính xác.

**“GFF O(k²) sao em lại có F trong công thức?”**

O(k²) mô tả phần đặt một flow khi số hop và truy cập link coi là hằng số. Một kỳ phải xử lý nhiều flow, dựng lại reservation và tạo kết quả. Bản C++ còn có map/set lookup nên em phân biệt chi phí một flow, cả kỳ và chi phí container.

**“SA O(f_avg) sao runtime lớn hơn GFF?”**

Đó là phần cập nhật cục bộ của một swap dưới giả định lưu lượng phân bố phù hợp. SA chạy I bước, còn khởi tạo, chọn neighbor và lưu best. Microbenchmark của em dùng I = 1.000 và cho thấy placement tốn thêm thời gian, nhưng chất lượng đường phải đánh giá riêng.

**“H = 0 đã là nghiệm tối ưu chưa?”**

Nó là nghiệm không quá tải đối với demand và flow đang xét. Nó chưa chứng minh goodput tối ưu vì mô hình energy không mô tả toàn bộ TCP, ACK, queue và các flow chưa được quản lý. Em chưa có oracle tối ưu để công bố optimality gap.

**“Tại sao phải giữ best riêng với current?”**

Current có thể nhận một bước làm energy xấu hơn để tiếp tục tìm kiếm. Nếu trả current ở cuối, có thể trả một state kém hơn state đã gặp. Best giữ chất lượng tốt nhất đã quan sát, trong khi warm start dùng mapping đó cho kỳ kế tiếp.

**“GFF và SA cái nào tốt hơn?”**

GFF có ưu thế chi phí thấp và giữ đường. SA bỏ thêm công tìm kiếm, có cơ hội thoát bố trí kém nhưng không có bảo đảm luôn thắng GFF về goodput. Lựa chọn phụ thuộc workload, tốc độ traffic thay đổi và ngân sách điều khiển.

## 11. Vị trí nguồn để đối chiếu

- [Paper Hedera, USENIX NSDI 2010](https://www.usenix.org/legacy/event/nsdi10/tech/full_papers/al-fares.pdf): §2–4, đặc biệt §4.3–4.5 và Table 1. Nhận định của paper và phân tích bản C++ được phân biệt trong tài liệu này.
- [Core thuật toán](../sim/hedera-core.cc): `EstimateDemands` dòng 65, `GlobalFirstFit::Place` dòng 118, `Anneal` dòng 160 tại thời điểm viết.
- [Microbenchmark](../tests/scheduler-benchmark.cc): vùng đo estimator/placement, cold start và SA 1.000 bước.
- [120 mẫu scheduler](../results/scheduler-v2.csv): nguồn trực tiếp của bảng median.
- [Ghi chú vấn đáp chung](defense-notes.vi.md) và [phân tích thực nghiệm](followup-report.vi.md).

Các cận được suy từ cấu trúc vòng lặp và container hiện tại. Chúng không phải một kết quả chứng minh mới về thuật toán Hedera tổng quát, và vài điểm runtime không thể xác nhận Big-O.
