# Đối chiếu project hiện tại với Hedera NSDI 2010

Mốc cập nhật: **29/10/2026**. Nguồn gốc: [paper USENIX](https://www.usenix.org/legacy/event/nsdi10/tech/full_papers/al-fares.pdf). Đối chiếu dưới đây dựa trên trách nhiệm và thuật toán; không tính một tỷ lệ “hoàn thành paper” từ số chức năng.

## Các thành phần đã triển khai

| Mốc paper | Trạng thái trong project | Phân loại |
|---|---|---|
| §3.1 — switch/default forwarding | `hedera-data-plane.cc`: fat-tree, ECMP giữ đường, đường theo core; có flow hash và destination hash. Khởi tạo bằng mô hình đường IPv4, không cài bảng prefix/flow-entry phần cứng nguyên bản. | Tái hiện hành vi, đơn giản hóa switch |
| §3.1 — large-flow detection | `hedera-monitoring.cc`: threshold tốc độ theo NIC, source-edge counter gồm retransmission, FIN/RST/idle soft state. | Tái hiện cơ chế |
| §3.2 — centralized scheduler | `hedera-control-plane.cc`: snapshot, demand, lựa chọn scheduler, kế hoạch và installer. Chạy trong cùng simulator với fabric. | Tái hiện trách nhiệm, đơn giản hóa triển khai |
| §4.2 / Figures 4, 7 — estimator | `EstimateDemands`: incoming/outgoing theo host, sender sharing, receiver water filling; kiểm tra ví dụ và capacity. | Tái hiện cơ chế |
| §4.3 / Figure 5 — GFF | Reservation, giữ đường flow cũ, thử candidate, fallback ECMP, xóa reservation hết active. Dùng điều kiện `<=` với tolerance ở biên capacity. | Tái hiện với biến thể biên công bố |
| §4.4 / Figure 6 — SA | Hoán vị destination–core, ba neighbor, delta energy, chấp nhận xác suất, best riêng, warm start. Vòng T dừng ở 1. | Tái hiện với bảo vệ số học |
| §5 — hệ thống thực | ns-3 PointToPoint/IPv4/TCP NewReno; packet-version tag và cập nhật nguyên tử. | Thay nền tảng thực thi |
| §5–6 — đánh giá | Có workload khớp giữa thuật toán, source snapshot, manifest, số đo ứng dụng/link, runtime riêng và các đối chứng TCP. | Đánh giá độc lập |

Không gian mapping SA, ngưỡng tốc độ và GFF reservation được giữ theo cách diễn giải đã kiểm chứng. Các chi tiết backend, hash và TCP khác môi trường gốc. Paper mô tả flow bằng 10 trường trong hệ thống; baseline project thường dùng 5-tuple. Không khẳng định hash của đồ án tương đương hash phần cứng của tác giả.

## Những phần được mở rộng trong lần nâng cấp này

| Phần bổ sung | Đã làm trong code | Giá trị kiểm chứng |
|---|---|---|
| Tách architecture | Façade, data plane, monitoring, control plane, workload và telemetry thành file riêng; monitoring/queue có API thuần C++. | Có thể kiểm thử chính sách tách khỏi packet simulation; ranh giới thông tin rõ hơn. |
| Workload theo pha | Start/stop từng flow, cohort, pha baseline/burst/recovery và log thời điểm nguồn. CSV cũ vẫn đọc được. | Kiểm tra phát hiện/thích nghi khi tập traffic thay đổi. |
| Vòng đời kế hoạch | FIFO/coalesce, một kế hoạch in-service, snapshot ID/time, kiểm tra tuổi và soft state trước cài. | Đánh giá backlog, kế hoạch bị thay/quá hạn, flow kết thúc trước cài. |
| Metric thống nhất | Per-flow goodput, conditional p95 FCT, fairness population, retransmission/drop, route churn, install age và các phase metric. | Giữ trường thiếu dữ liệu là null, không loại zero-goodput flow để làm đẹp fairness. |
| Exact oracle | Duyệt đủ các phép gán hợp lệ cho snapshot nhỏ trong cùng state space SA; từ chối nếu vượt giới hạn. | Đối chiếu absolute energy gap và tỷ lệ chạm optimum theo ngân sách bước. |
| Replay | Một HTML có dữ liệu nhúng: run/flow/time, topology, link utilization, đường cài/proposal, goodput và control events. | Nối quyết định scheduler với số đo thực tế; dùng lại kết quả mà không chạy simulator. |
| Chạy lại | `run-upgrade-study.sh`: build, tests, studies, validation, analysis và export replay vào output mới. | Quy trình tái lập có kiểm tra, giữ nguyên các kết quả trước nâng cấp. |

FIFO/coalesce, giới hạn tuổi kế hoạch, oracle và replay là các lựa chọn của project. Không mô tả chúng là những thuật toán mới được Hedera 2010 đề xuất. Oracle cũng không được dùng để giúp scheduler trong benchmark mạng.

## Những khác biệt vẫn còn

| Khía cạnh | Phạm vi hiện tại |
|---|---|
| Control messages | Không truyền counter/rule dưới dạng packet OpenFlow; chưa đo băng thông telemetry hoặc độ trễ cài từng switch. Delay là mô hình cấu hình. |
| Switch resources | Chưa có TCAM, giới hạn flow-table hoặc tốc độ cập nhật rule. |
| Failures | Chưa có link failure, scheduler replication/failover hoặc mô hình PortLand đầy đủ. |
| Quy mô | Các benchmark trước có 16 và 128 host; oracle/dynamic mới tập trung 16 host. Chưa đánh giá 1.024/8.192 host. |
| Rate / thời gian | Study mới dùng 20 Mbit/s và thời gian ngắn phù hợp WSL. Profile 1 Gbit/s/60 s đã có nhưng chưa thuộc kết quả xác minh này. |
| Traffic | Có nhiều pattern và pha có chủ đích, chưa tái hiện toàn bộ trace/thí nghiệm shuffle của tác giả. |
| Thước đo | Tổng application goodput và payload qua host-half-cut được lưu riêng. Không đổi tên tổng goodput thành bisection bandwidth. |
| Tối ưu | Exact H* chỉ cho snapshot nhỏ trong state space SA. Nonblocking reference vẫn là phép đo TCP/queue, không phải chứng nhận optimal goodput. |

## Cách diễn đạt kết luận

Project tái hiện pipeline phát hiện–ước lượng–placement–cài đường của Hedera trong mô hình packet-level và có các mở rộng để phân tích động học, chất lượng nghiệm và khả năng tái lập. Bằng chứng nằm ở test thuật toán, log điều khiển, kết quả workload khớp và dữ liệu CSV.

Chưa có căn cứ nhận tái lập toàn bộ định lượng của paper hoặc đạt mức “96% tối ưu” cho benchmark TCP hiện tại. H=0, oracle H* và goodput reference là ba khái niệm khác nhau, phải giữ riêng khi đọc kết quả.

Xem [kiến trúc và hợp đồng module](architecture.vi.md) và [kết quả nâng cấp](upgrade-results.vi.md) để biết cấu hình, số mẫu và các kiểm tra đã chạy.
