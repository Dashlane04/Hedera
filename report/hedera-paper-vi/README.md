# Tái hiện và kiểm chứng Hedera trên mạng fat-tree

Project LaTeX hai cột, tiếng Việt, dùng lớp IEEEtran ở chế độ hội nghị. Mở main.tex trong thư mục này bằng XeLaTeX. Nếu biên dịch trên TeX Live, cần các gói ieeetran, pgf, unicode-math, tex-gyre và tex-gyre-math. Thông tin tác giả nằm trong khối author của main.tex.

    xelatex -interaction=nonstopmode -halt-on-error main.tex
    xelatex -interaction=nonstopmode -halt-on-error main.tex

- main.tex chứa bài báo, bảng, chú thích hình và tài liệu tham khảo.
- diagrams/ chứa mã TikZ của sơ đồ fat-tree, ví dụ ECMP–GFF và bước hoán đổi core của SA.
- figures/ chứa hình PDF vector sinh từ dữ liệu.
- numbers.tex chứa số liệu đưa trực tiếp vào bài.
- data/ chứa CSV dẫn xuất. data/provenance/ chứa manifest, thông tin môi trường đo runtime và log CTest.

Trong workspace, scripts/analyze-paper-reproduction.py tái tạo số liệu và hình từ results/paper-reproduction/. Giao thức chạy lại nằm trong docs/paper-reproduction.vi.md.
