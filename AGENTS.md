# AGENTS.md — Code Conventions

## Enhance agent rules

Cac vi du la minh hoa only, dung bat chuoc 100%.

### Eval-first

Chạy Baseline v0 & Phân tích Failure Traces

Mục tiêu của pha này là đánh giá năng lực của Prompt khởi tạo (Baseline v0) tại starter_v0/artifacts/system_prompt.md và mô tả công cụ tại starter_v0/artifacts/tools.yaml trên bộ dữ liệu kiểm thử chuẩn data/eval_base.json.
Bước 3.1: Đánh giá Run Baseline (Version v0)

Chạy bộ kiểm thử cơ bản (Base Suite gồm 30 test cases: 20 single-turn + 10 multi-turn):

python run_eval.py --provider openrouter --version v0 --suite base --eval-cases data/eval_base.json

Sau khi chạy xong, kết quả đánh giá và file trace chi tiết sẽ được ghi tự động vào thư mục runs/.
💡 Điều kiện để một Run được công nhận làm bằng chứng (Evidence): Kết quả đo lường chỉ có giá trị khi: ``text provider_error_cases == 0 measured_cases == total_cases ` Nếu có lỗi kết nối Provider (provider_error`), hãy kiểm tra đường truyền và quota trước khi lấy dữ liệu làm báo cáo.
Bước 3.2: Phân tích 5 Nhóm Lỗi Thường Gặp

Đừng chỉ nhìn vào điểm số tổng thể. Hãy mở các file JSON trong runs/ và trích xuất ít nhất một trường hợp lỗi đại diện thuộc 5 nhóm sau:

    1. Wrong-tool Case (Lỗi chọn sai công cụ): Người dùng hỏi về trạng thái VPN chung của công ty nhưng Agent lại gọi inspect_device thay vì check_service_status.
    2. Wrong-argument Case (Lỗi tham số): Agent chọn đúng tool lookup_user nhưng tự bịa ra mã EMP-9999 thay vì trích xuất đúng EMP-1007 từ câu hỏi.
    3. Missing-information Case (Lỗi thiếu thông tin): Người dùng hỏi "Kiểm tra máy laptop của tôi", Agent không biết mã Asset ID nhưng tự chọn đại một laptop trong danh sách thay vì dùng tool clarify để hỏi lại.
    4. Multi-turn / Multi-tool Case (Lỗi nhiều lượt / nhiều công cụ): Người dùng đính chính lại thông tin ở câu thoại thứ 2, nhưng Agent vẫn lấy tham số cũ từ câu thoại 1.
    5. Confirmation / Security Boundary Case (Lỗi an toàn & xác nhận): Agent thực hiện tạo ticket (create_ticket với confirmed=True) khi người dùng chưa xác nhận rõ ràng.

### Enhance rules

Tối ưu System Prompt & Tools Declaration (v1, v2, v3)

Quá trình Prompt Engineering chuẩn chỉnh tuân theo quy trình vòng lặp thực nghiệm (Experiment Loop): Đặt giả thuyết → Sửa Artifact → Chạy Eval → Ghi Log → Rà soát Regression.

1. Phân tích Failure Trace

2. Viết Giả thuyết (Hypothesis)

3. Sửa system_prompt.md / tools.yaml

4. Chạy python run_eval.py

5. So sánh Metric & Kiểm tra Regression

6. Cập nhật version_log.csv
   Bước 4.1: Quy tắc Phân chia Nơi Cần Chỉnh Sửa
   Nguyên nhân gốc (Root Cause) Nơi cần tập trung chỉnh sửa Ví dụ cụ thể
   Nguyên tắc ứng xử toàn cục, quy định an toàn, cách xử lý khi thiếu thông tin artifacts/system_prompt.md "NẾU thiếu Asset ID hoặc Employee ID, BẮT BUỘC dùng tool clarify để hỏi người dùng, KHÔNG ĐƯỢC tự đoán ID."
   Mô tả công cụ mơ hồ, tham số chưa rõ định dạng, ranh giới giữa 2 tool bị chồng lấp artifacts/tools.yaml Cập nhật description của check_service_status: "Dùng để tra cứu dịch vụ hạ tầng chung (VPN, Email, Printing). KHÔNG dùng tra cứu thiết bị cá nhân."
   Bước 4.2: Đặt Giả thuyết & Tiến hành Cải tiến từng Phiên bản

Mỗi phiên bản nâng cấp phải đi kèm một mục nhập trong file starter_v0/artifacts/version_log.csv.
Ví dụ Vòng lặp v1 (Cải thiện Routing & Clarification):

    Giả thuyết: "Nếu quy định rõ trong system_prompt.md rằng không tự đoán ID và làm rõ phân biệt giữa shared service status với single device inspection trong tools.yaml, tỷ lệ chọn sai tool ở nhóm case thiếu thông tin sẽ giảm 50%."
    Thực thi: Sửa system_prompt.md và tools.yaml.

Ví dụ Vòng lặp v2 (Xử lý Context Carry-over & Confirmation):

    Tối ưu quy tắc giữ ngữ cảnh multi-turn và yêu cầu xác nhận confirmed: true trước khi tạo ticket.

Ví dụ Vòng lặp v3 (Hoàn thiện Ranh giới An toàn Data Exfiltration):

    Giới hạn tham số truyền ra search_device_info chỉ gồm manufacturer và public model name; cấm truyền serial, hostname, employee ID ra bên ngoài.

## Core Principles

1. **Minimal code** — Write the least code that solves the problem. No abstraction layers unless proven necessary.
2. **Few files** — Consolidate related logic. Avoid creating new files unless the module is genuinely reusable.
3. **No `scripts/` folder spam** — Operational scripts go in `tools.py` or `Makefile`, not a separate folder.
4. **Minimal filesystem** — Flat structure preferred. Deep nesting only when domain demands it.
5. **Performance first** — Profile before optimizing. Prefer vectorized ops, batching, async I/O, caching. Avoid premature micro-optimizations.

## Python Specific

- Type hints on all public functions
- No `Optional` abuse — use `| None` or `Annotated`
- Dataclasses over dicts for structured data
- `pathlib` over `os.path`
- Single `__init__.py` per package, empty or exports only

## Structure

```
codebase/
├── app.py              # Entry point
├── decision_core.py    # Core logic
├── engine.py           # Processing engine
├── ingest.py           # Data ingestion
├── agent.py            # Agent implementation
├── tools.py            # Tool definitions + CLI
├── tools.yaml          # Tool registry
├── ui.html             # Frontend (single file)
├── tests/              # Only if coverage > 80% justified
└── data/               # Static assets only
```

## Forbidden

- Creating `scripts/`, `utils/`, `helpers/`, `common/` folders
- More than 3 files for a single feature
- Code that exists "for future use"
- Duplicate logic across files
