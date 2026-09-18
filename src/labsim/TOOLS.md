# LabSim Tools Specification & Setup

Tài liệu đặc tả toàn bộ các Tool phục vụ AI Agent trong hệ thống Lab Simulator. Toàn bộ mã nguồn thực thi được gom tập trung tại [`src/labsim/tools.py`](tools.py), và khai báo schema chuẩn hóa tại [`src/labsim/tools.yaml`](tools.yaml).

---

## 1. Nguyên Tắc Hoạt Động Cốt Lõi (Core Principles)

1. **Read-Only & Offline:** Tất cả các tool chỉ đọc dữ liệu từ chỉ mục đã được lập (`source_manifest.json` và `source_chunks.jsonl`). Không can thiệp terminal, không ghi đè repo học viên, không gọi API bên ngoài khi chạy tool.
2. **Deterministic Provenance:** Mọi kết quả trả về đều gắn chặt với định danh tệp (`path`), số dòng (`start_line`, `end_line`), phân loại nguồn (`source_kind`), và mã băm toàn vẹn SHA-256 (`sha256`).
3. **No Hallucination (Không Bịa Đặt):** AI Agent không được phép tự suy diễn code hoặc số dòng nếu chưa gọi Tool để đọc bằng chứng thực tế.

---

## 2. Danh Mục & Đặc Tả Chi Tiết Các Tool

### 2.1. `search_sources` — Tìm Kiếm Bằng Chứng Trong Chỉ Mục
- **Mục đích:** Tìm kiếm các đoạn tài liệu hướng dẫn (`CODELAB.md`, `README.md`) hoặc mã nguồn (`src/*.py`) khớp với từ khóa/cụm từ của câu hỏi.
- **Tham số (Inputs):**
  - `query` *(string, bắt buộc)*: Từ khóa hoặc cụm từ cần tìm (ví dụ: `"Task 2.1"`, `"academic_query"`, `"MCPAcademicServer"`).
  - `top_k` *(integer, mặc định: 5)*: Số lượng kết quả phù hợp nhất cần trả về.
  - `filter_kind` *(string, tùy chọn)*: Giới hạn tìm kiếm trong một loại nguồn (`"instruction"`, `"code"`, `"reported"`).
- **Kết quả trả về (Outputs):**
  - Danh sách các chunk gồm: `chunk_id`, `path`, `start_line`, `end_line`, `source_kind`, `text_snippet`.

---

### 2.2. `read_source_chunk` — Đọc Nguyên Văn Chunk
- **Mục đích:** Đọc toàn bộ nội dung text và lấy mã băm SHA-256 của một chunk cụ thể để phân tích chi tiết hoặc trích dẫn bằng chứng.
- **Tham số (Inputs):**
  - `chunk_id` *(string, bắt buộc)*: Định danh chunk (ví dụ: `"docs/CODELAB.md:1-40"`, `"src/tools.py:176-215"`).
- **Kết quả trả về (Outputs):**
  - Object gồm: `chunk_id`, `path`, `start_line`, `end_line`, `sha256`, `source_kind`, `text`.

---

### 2.3. `get_file_outline` — Soi Cấu Trúc AST Mã Nguồn
- **Mục đích:** Trích xuất nhanh danh sách các lớp (`class`), hàm (`function`) và vị trí dòng chính xác từ cây cú pháp trừu tượng (AST) đã được bóc tách trong `source_manifest.json`. Giúp Agent nắm toàn cảnh một file code mà không cần đọc hết toàn bộ file.
- **Tham số (Inputs):**
  - `path` *(string, bắt buộc)*: Đường dẫn tương đối của file (ví dụ: `"src/tools.py"`, `"src/mcp_server.py"`).
- **Kết quả trả về (Outputs):**
  - Object gồm: `path`, `source_kind`, `total_lines`, `sha256`, `symbols` (mỗi symbol gồm: `name`, `kind`, `line`, `end_line`).

---

### 2.4. `list_indexed_files` — Danh Mục Tệp Đã Lập Chỉ Mục
- **Mục đích:** Giúp Agent nắm được toàn bộ cây thư mục và danh sách các tệp tin hiện có trong bài Lab kèm số dòng và số lượng hàm/class.
- **Tham số (Inputs):**
  - `filter_kind` *(string, tùy chọn)*: Lọc theo loại nguồn (`"instruction"`, `"code"`, `"reported"`).
- **Kết quả trả về (Outputs):**
  - Danh sách các file: `path`, `source_kind`, `total_lines`, `symbols_count`.

---

## 3. Khai Báo Schema Chuẩn (`tools.yaml`)

Tất cả các định nghĩa trên được khai báo trong [`src/labsim/tools.yaml`](tools.yaml) theo định dạng tương thích với JSON Schema / OpenAI Function Calling, cho phép nạp trực tiếp vào bất kỳ mô hình LLM nào mà không cần viết lại định nghĩa thủ công.
