# Đối chiếu mở rộng với Hedera NSDI 2010

Bài báo chỉnh sửa được nằm tại [main.tex](../report/hedera-paper-vi/main.tex). Mở cả thư mục khi biên dịch để tìm được font, hình và bảng số. [Paper gốc](https://www.usenix.org/legacy/event/nsdi10/tech/full_papers/al-fares.pdf)

| Mốc đối chiếu | Phép đo hoặc triển khai | Nguồn dữ liệu |
|---|---|---|
| Hình 9, §6.2 | ns-3 ở 16 host với stride 1/2/4/8, song ánh và hotspot. Ma trận chính dùng 20 Mbit/s, cửa sổ 2–8 giây, băm IP đích và RTO tối thiểu 200 ms. | compact16/, data/packet16.csv |
| Hình 9, cấu hình dài | Hai profile 60 giây, cửa sổ 10–50 giây, polling 5 giây. Profile 20 Mbit/s quét sáu workload. Profile 1 Gbit/s dùng stride 8. | scaled16/, gigabit16/ |
| Hình 9, đối chứng TCP | Stride 8 ở 1 Gbit/s. Lượt trace 60 giây tái hiện reference gốc. Bốn lượt ngắn trên reference xét từng thay đổi delayed ACK, số gói mỗi ACK hoặc RTO tối thiểu. | gigabit-tcp/, gigabit-tcp-short/, data/gigabit-tcp.csv |
| Bổ sung tại 1 Gbit/s | Tải song ánh với ba seed. Trong từng seed, bốn phương pháp dùng cùng danh sách luồng. ACK mỗi gói, RTO tối thiểu 200 ms, đo từ 0,8 đến 2,8 giây. | gigabit-bijection/, data/gigabit-bijection.csv, data/gigabit-bijection-summary.csv |
| Hình 10–11, §5.5 và §6.4 | Mô phỏng C++ cấp luồng dùng chung topology và thuật toán. Chạy tám mẫu ở 8.192 host và tải song ánh ở 1.024 host. | flow/manifest.json, flow/summary.csv, trace và workload CSV |
| Bảng 3, §4.4 | Thay ngân sách 100/1.000/10.000 và trạng thái khởi tạo. Đối chiếu SA theo đích và theo flow với hai oracle trên snapshot nhỏ. | flow/, core-verified/scheduler-quality.csv |
| Bảng 4–5 | Benchmark Release theo số host/luồng công bố, năm snapshot mỗi điểm. Estimator lên tới 27.648 host và 250.000 luồng. | core-verified/scheduler-estimate.csv, scheduler-runtime.csv, machine.txt |
| §4.5 và Bảng 6 | So GFF kích hoạt sau phát hiện với GFF/SA định kỳ. Ghi số byte và các mốc điều khiển theo switch. Dùng dự báo theo mô hình để đối chiếu Bảng 6. | switch-control.csv, control-events.csv, data/control-projection.csv |
| §4.6 | Tiêm mất liên kết aggregation–core. Chuyển luồng bị ảnh hưởng, kiểm tra kế hoạch cũ và đo goodput phục hồi. | mechanisms/outage-*, mechanisms/healthy-*, data/recovery.csv |
| Bảng 2 | Shuffle tuần tự theo nguồn ở 1 MiB và 256 KiB mỗi cặp. Giữ các host chưa hoàn thành trong mẫu số. | mechanisms/sequential-shuffle-*, shuffle-ack/, data/shuffle.csv |

Các kết quả thô nằm trong [results/paper-reproduction](../results/paper-reproduction). CSV dẫn xuất, hình PDF vector và numbers.tex nằm trong project LaTeX.

## Kiến trúc theo vòng điều khiển của Hedera

| Bước của Hedera | Thành phần của dự án | Trace đối chiếu |
|---|---|---|
| Fabric nhiều đường và mặc định ECMP | hedera-data-plane.cc dựng fat-tree, phân tuyến data/ACK, giữ phiên bản đường và xử lý lỗi link. | nodes.csv, links.csv, routes.csv |
| Phát hiện luồng lớn ở edge | hedera-monitoring.cc quản lý tuổi trạng thái và phát hiện theo mẫu payload nguồn. hedera-control-plane.cc tập hợp các luồng lớn đã phát hiện. | flows.csv, controller.csv, controller-flows.csv khi bật chẩn đoán |
| Ước lượng nhu cầu và đặt đường | hedera-core.cc thực hiện estimator, GFF và SA theo đích. hedera-control-plane.cc quyết định kỳ chạy và hàng đợi kế hoạch. | controller.csv, control-events.csv |
| Phân phối rule về switch | hedera-control-plane.cc mô hình hóa quá trình thu thống kê, tính toán và gửi bản ghi từng switch. Data plane nhận đường mới qua mốc kích hoạt chung. | switch-control.csv, control-events.csv |

Bốn lượt 1 Gbit/s gốc dùng snapshot scenario lưu trước khi thêm các chức năng lỗi liên kết, shuffle và cài rule theo switch. Snapshot đi kèm manifest và dữ liệu thô. Trong cửa sổ 10–50 giây, reference đạt 0,93 Mbit/s sau đợt truyền đầu. Lượt có trace dùng bản scenario mới tái hiện goodput này. Cả 128 mẫu cwnd trong cửa sổ đều bằng một MSS. Đối chứng ACK/RTO ngắn dùng cùng lịch mở kết nối nhưng dừng sớm hơn để tập trung vào giai đoạn khởi phát.

## Hợp đồng mô phỏng

- Switch control sử dụng cổng 1 Gbit/s, uplink controller 10 Gbit/s, 72 byte mỗi mục và trễ một chặng 10 microgiây. Kế hoạch dựa trên snapshot đã lấy tại edge. Mỗi switch có thời điểm nhận rule riêng. Data plane kích hoạt phiên bản đường tại hàng rào cuối đợt.
- Mất liên kết dùng lỗi nhận 100% ở hai đầu. Sau thời gian nhận biết cấu hình được, các đường mới loại liên kết hỏng. Gói cũ giữ phiên bản đường cũ. Thí nghiệm xét một link có sẵn đường thay thế.
- Mỗi host có một lượt truyền shuffle tại một thời điểm. Workload.csv mô tả thứ tự. Workload-events.csv ghi thời điểm các nguồn thực sự được khởi động.
- Runtime dùng snapshot tổng hợp. Tỷ lệ giữa hai biến thể SA bao gồm khác biệt về dựng đầu ra. Oracle áp dụng cho không gian nghiệm đủ nhỏ để duyệt toàn bộ.

## Chạy lại

Trong WSL, cần ns-3.47, CMake/Ninja, trình biên dịch C++ và Python 3.11 trở lên với NumPy, Matplotlib.

    bash scripts/run-paper-reproduction.sh results/paper-reproduction-new

Thêm tùy chọn --long để chạy hai profile 60 giây, các đối chứng TCP và bộ song ánh ở 1 Gbit/s. Script dùng target hedera-paper-sim trong thư mục scratch riêng.

    bash scripts/run-paper-reproduction.sh results/paper-reproduction-long --long

Chạy riêng bộ song ánh ở 1 Gbit/s sau khi đã biên dịch target hedera-paper-sim.

    python3 scripts/benchmark-study.py --paper-build --suite paper-gigabit-bijection \
        --output results/gigabit-bijection-new --jobs 4 --timeout 5400
    python3 scripts/validate-results.py results/gigabit-bijection-new

Tạo lại hình và số từ dữ liệu đang có.

    python3 scripts/analyze-paper-reproduction.py \
        results/paper-reproduction report/hedera-paper-vi --allow-partial-gigabit

Các profile packet-level chỉ đưa lượt có summary.json vào CSV. Manifest lưu cấu hình, revision ns-3 và hash mã nguồn của scenario. Manifest của mô phỏng cấp luồng cũng lưu hash binary. Stag(0,5; 0) lấy theo nhãn Hình 10. Dữ liệu Stag(0,5; 0,3) từ lượt trước được giữ riêng trong CSV và không tham gia Hình 10 tái hiện.
