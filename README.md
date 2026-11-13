# Hedera

Tái hiện bộ lập lịch luồng động Hedera trên mạng fat-tree bằng ns-3.47. Dự án so sánh ECMP, Global First Fit (GFF) và Simulated Annealing (SA) qua goodput, mức sử dụng liên kết và chi phí lập lịch, rồi đối chiếu với [bài báo Hedera tại NSDI 2010](https://www.usenix.org/legacy/event/nsdi10/tech/full_papers/al-fares.pdf).

[Báo cáo PDF](output/pdf/hedera-public.pdf) · [Nguồn LaTeX](report/hedera-paper-vi/) · [Đối chiếu với bài báo và cách chạy lại](docs/paper-reproduction.vi.md)

## Mô hình và kết quả

- Mô phỏng cấp gói trên ns-3 với 16 máy. Các thí nghiệm quy mô 1.024 và 8.192 máy dùng mô hình C++ cấp luồng.
- Ở tải song ánh 1 Gbit/s trên ns-3, GFF và SA đều đạt goodput cao hơn ECMP trên ba ánh xạ đã thử. Mức tăng tương đối trung bình theo cặp là 45,0% với GFF và 59,4% với SA. [Dữ liệu theo seed](report/hedera-paper-vi/data/gigabit-bijection.csv)
- Hai bộ kiểm thử C++ kiểm tra cấu trúc mạng, bộ ước lượng, bộ lập lịch và logic cài đường. Trình kiểm tra dữ liệu xác thực 119 lượt ns-3 dùng trong báo cáo.

## Chạy lại trong Ubuntu hoặc WSL2

Cần [ns-3.47](https://www.nsnam.org/releases/ns-3-47/), CMake, Ninja, trình biên dịch C++ và Python 3.11 trở lên. Cài thêm NumPy và Matplotlib để tạo hình. Chạy từ thư mục repo và chỉnh `NS3_DIR` theo nơi đã cài ns-3.

```bash
export NS3_DIR="$HOME/network-perf/ns-3"
HEDERA_PAPER_BUILD=1 bash scripts/build-wsl.sh
python3 scripts/validate-results.py results/paper-reproduction/gigabit-bijection
```

Chạy lại các kịch bản chính vào thư mục mới. Thêm `--long` để chạy các cấu hình dài và các phép đo 1 Gbit/s.

```bash
bash scripts/run-paper-reproduction.sh results/paper-reproduction-new
```

Dựng lại hình và số liệu từ dữ liệu đã công bố.

```bash
python3 scripts/analyze-paper-reproduction.py \
    results/paper-reproduction results/report-rebuilt
```

`sim/` chứa mã mô phỏng. `tests/` chứa kiểm thử và mô hình cấp luồng. `results/paper-reproduction/` chứa dữ liệu cấp gói, cấu hình, tóm tắt và chuỗi thời gian cấp luồng. Có thể sinh lại các danh sách luồng quy mô lớn từ cấu hình và seed trong manifest.
