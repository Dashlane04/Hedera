# Trạng thái triển khai và kiểm chứng

Ngày kiểm chứng: **25/10/2026**, WSL2 Ubuntu 24.04.4 LTS, ns-3 **3.47**, GCC 13.3.0, CMake 3.28.3.

## Những thành phần đã build và chạy

| Mốc | Source | Bằng chứng |
|---|---|---|
| Fat-tree và đường hợp lệ | `sim/hedera-core.*` | Kiểm tra mọi cặp host k=4, số node/link, số đường cùng chi phí |
| TCP packet-level và ECMP theo flow | `sim/hedera-network.*` | Single flow nhận đủ 8 MiB; ECMP không reroute |
| Detector và Demand Estimation | `sim/hedera-core.cc`, `Experiment::Tick` | Figure 4; 100 ma trận flow ngẫu nhiên không vượt NIC gửi/nhận |
| Global First Fit | `GlobalFirstFit` | Đặt/giữ/giải phóng đường, fallback, trường hợp vừa khít capacity |
| Simulated Annealing | `Anneal` | Kiểm tra delta energy với phép tính lại, ánh xạ một-một, best và warm start |
| Điều khiển có delay | `Experiment::ApplyPaths` | GFF thay đường tại các mốc snapshot + 20 ms |
| Metrics và runner | `scripts/*.py` | 27 ca matched-input; CSV, XML và biểu đồ đã sinh |

Core executable báo **83.559 kiểm tra điều kiện vượt qua** trong một test suite; đây không phải 83.559 test case độc lập. `ctest` có một test executable tổng hợp.

## Bộ so sánh prototype

Output: `results/prototype-study/`.

- 3 workload: collision, permutation, mixed.
- 3 seed: 1, 2, 3.
- 3 thuật toán: ECMP, GFF, SA.
- Tổng **27 lần chạy**, k=4, 16 host, 20 router/switch mô hình.
- Link 100 Mbit/s, propagation delay 10 us/link, TCP NewReno.
- Nguồn dừng ở giây 3, sink còn chạy thêm 1 giây.
- Detector/scheduler mỗi 100 ms, threshold 10% NIC, SA 1.000 bước/kỳ.
- Workload CSV giữa ba thuật toán khớp byte-for-byte theo từng seed.
- Đã kiểm tra không có drop do thiếu route, TTL, checksum, interface hoặc fragment; queue drop được phép và giữ trong dữ liệu.
- Đã kiểm tra số byte nhận không vượt số byte gửi theo application, FCT nhất quán, ECMP không đổi đường và SA best không xấu hơn trạng thái đầu trong cùng snapshot.

**Chế độ `--check-energy` được bật để kiểm chứng trong study này.** Runtime CPU của SA bao gồm kiểm tra bằng full recomputation, không dùng làm kết quả performance benchmark cho phiên bản delta-only. Thông tin này nằm trong manifest của study. Study được tạo trước khi bổ sung các trường metadata và logging energy cho GFF; không sử dụng hai cột energy GFF (giá trị 0 trong study ban đầu) để kết luận chất lượng placement. Bản hiện tại ghi energy GFF thực tế và `energy_verification` trong summary.

## Kết quả ban đầu, trung bình theo seed

| Workload | Thuật toán | Goodput trong cửa sổ (Mbit/s) | Mean FCT của flow hoàn thành (s) | Tỷ lệ flow hoàn thành |
|---|---|---:|---:|---:|
| Collision | ECMP | 191,74 | 2,3812 | 100% |
| Collision | GFF | 191,74 | 0,8056 | 100% |
| Collision | SA | 191,74 | 0,8043 | 100% |
| Permutation | ECMP | 347,00 | 1,0855 | 89,58% |
| Permutation | GFF | 333,34 | 0,9235 | 85,42% |
| Permutation | SA | 340,03 | 0,8230 | 87,50% |
| Mixed | ECMP | 340,99 | 0,6389 | 91,67% |
| Mixed | GFF | 349,95 | 0,5853 | 89,58% |
| Mixed | SA | 330,23 | 0,5429 | 87,50% |

Các giới hạn diễn giải:

1. Collision là fixture chọn port có chủ đích để băm về cùng core. Nó kiểm tra cơ chế, không phải bằng chứng đại diện mọi traffic. Các seed tạo port khác nhưng cùng cấu trúc collision, vì vậy độ biến thiên nhỏ là bình thường.
2. Ở collision, cả ba phương pháp gửi xong cùng lượng dữ liệu trước cuối cửa sổ. Goodput trung bình trong toàn cửa sổ do đó bằng nhau, dù FCT khác rõ. Không gọi metric này là throughput bão hòa.
3. Ở permutation/mixed, tập flow hoàn thành khác nhau giữa thuật toán. Không được kết luận SA/GFF tốt hơn chỉ dựa trên mean FCT thấp hơn; phải xem completion fraction, goodput, drop và flow bị cắt.
4. Có một flow mixed-seed3-ECMP không nhận payload: SYN-ACK bị FIFO queue disc drop, trong khi flow hết thời gian trước khi handshake hồi phục. FlowMonitor xác nhận queue-disc drop, không phải lỗi thiếu route. Flow được giữ là chưa hoàn thành.
5. Error bar trong `comparison.png` là sample standard deviation giữa ba seed, chưa phải khoảng tin cậy.
6. Đây là baseline prototype, chưa tái tạo đầy đủ workload và cấu hình của paper 2010.

## Integration checks

Các ca acceptance của bản source cuối được lưu tại `results/acceptance/`; bản integration trước đó tại `results/integration-final/`. Script tái chạy bằng output mới là `scripts/smoke-tests.py`. Build cuối không có compiler diagnostic warning; cả 8 ca acceptance vượt qua.

| Ca | Kết quả quan sát |
|---|---|
| Locality CSV với ECMP | 4/4 flow hoàn thành, gồm cùng edge/cùng pod/liên pod |
| Locality CSV với GFF | 4/4 flow hoàn thành |
| Locality CSV với SA | 4/4 flow hoàn thành, kiểm tra delta bật |
| k=8 single | 128 host, 1/1 flow hoàn thành |
| GFF control delay 20 ms | 8/8 flow hoàn thành, 6 thay đường, thời điểm apply đúng delay |
| Hotspot không hoàn thành | 0/4 flow hoàn thành; mean/p95 FCT trong JSON là null, không giả thành 0 |
| Staggered localProbability=1 | 8/8 hoàn thành; toàn bộ đích cùng pod với nguồn |
| Staggered localProbability=0 | 8/8 hoàn thành; toàn bộ đích khác pod |

Validator tự kiểm tra matched inputs khi có study manifest. Thư mục smoke chứa nhiều cấu hình khác nhau, nên không yêu cầu tất cả các workload trong đó giống nhau. Riêng ba locality case phải dùng cùng CSV và được smoke script đối chiếu trực tiếp.

## Những việc còn lại ở mốc prototype cũ

- Chốt workload, cửa sổ đo, stop/drain, seed và cách xử lý censored flows.
- Tách chạy kiểm chứng `checkEnergy=1` khỏi đo runtime tối ưu `checkEnergy=0`.
- Bổ sung Poisson/exponential hoặc trace phù hợp nếu mục tiêu là tái hiện phần simulator của paper.
- Khảo sát scheduling interval, threshold và số bước SA; dùng output/manifest riêng cho mỗi cấu hình.
- Thêm nhiều seed và khoảng tin cậy phù hợp sau khi chốt thiết kế thí nghiệm.
- Giữ rõ giả định router IPv4, controller đọc memory, cập nhật đường nguyên tử có version tag và biến thể biên GFF `<=` trong README.

## Cập nhật benchmark ngày 26/10/2026

Mốc này thay thế danh sách việc còn lại của prototype đối với workload, cửa sổ đo, Poisson, sensitivity và thống kê. [Báo cáo benchmark](benchmark-report.vi.md) ghi kết quả và các giới hạn; [giao thức](benchmark-protocol.md) ghi cấu hình tái chạy.

- Core suite bản mở rộng vượt qua **83.560 kiểm tra điều kiện trong một executable**, gồm hash mixing và các kiểm tra thuật toán trước đó. Scheduler microbenchmark được build Release.
- Bảy ca tại `results/benchmark-acceptance-v2` vượt qua: reference/fat-tree không tải khớp FCT khoảng 22,599 ms, Poisson và tải persistent của cả bốn thuật toán. Persistent có FCT/completion null.
- Validator vượt qua **100 run Main16**, **16 run Scale**, **42 run Sensitivity** và **4 run Late-window**. Tổng cộng 162 run, ngoài các ca acceptance. Workload giữa các thuật toán được đối chiếu byte-for-byte; mỗi study giữ source snapshot và manifest.
- Scheduler riêng có 120 mẫu tại `results/scheduler-v2.csv`, chạy tuần tự trước các study packet-level.
- Biểu đồ mới và bảng CSV giữ cả flow chưa hoàn thành, CI bootstrap qua seed và tỷ lệ theo cặp seed. Main16 dùng 5 seed; Scale/Sensitivity dùng 2 seed nên chỉ có giá trị thăm dò.
- Profile `paper60` chưa chạy. Bản mở rộng dùng 20 Mbit/s và cửa sổ ngắn theo tài nguyên WSL, không khẳng định tái hiện định lượng paper. Reference không bảo đảm là upper bound throughput TCP; tỷ lệ lớn hơn 1 được giữ và phân tích trong báo cáo.

Log validator tương ứng nằm tại `tmp/main16-validation.log`, `tmp/scale128-validation.log`, `tmp/sensitivity-validation.log` và `tmp/warmup-validation.log`. Source mô phỏng tại thời điểm benchmark được lưu trong `source/` của từng study.

## Follow-up: TCP, ablation và demo

[Báo cáo bổ sung](followup-report.vi.md) ghi **68 run mới** đã qua validator: 12 diagnosis, 8 ACK-check, 20 demand ablation, 3 demo và 25 transport-check. Log lần lượt là `tmp/diagnosis-validation.log`, `tmp/ack-check-validation.log`, `tmp/ablation-validation.log`, `tmp/demo-validation.log`, `tmp/transport-check-validation.log`.

Build cuối và core tests vượt qua (`tmp/followup-build.log`). Chín acceptance tại `results/followup-acceptance` vượt qua; script kiểm tra cả hai mode demand và đối chiếu byte-for-byte flows cùng goodput giữa GFF có/không diagnostics. Hai baseline reference của ACK-check cũng tái tạo đúng `flows.csv` và window goodput của Main16 seed 1. Năm finite reference MinRTO 300 ms đều hoàn thành 16/16.

Validator kiểm tra `selected_demand == measured_fraction` trong mode measured, giá trị diagnostics hợp lệ và không có FCT giả cho persistent traffic. Phân tích ablation/transport đối chiếu workload giữa mode và giữa study theo từng seed. Các kiểm tra này không thay cho chứng minh optimality hoặc tương đương hoàn toàn với testbed paper.
