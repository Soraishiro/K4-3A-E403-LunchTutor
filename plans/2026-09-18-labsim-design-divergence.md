# Lab Simulator — Decision history và thay đổi thiết kế

**Trạng thái:** companion của `2026-09-18-labsim-unified-workflow-design.md`, để người dùng duyệt; không phải changelog đã ghi vào `labsim_submission/spec.md`. Đối chiếu tài liệu hiện có, không quy cho mọi dự thảo cũ là quyết định đã được chốt.

## 1. Các mốc thay đổi

| Mốc | Định vị/flow được đề xuất ở thời điểm đó | Tài liệu gốc |
|---|---|---|
| M0 — bài toán ban đầu | Học viên làm Lab khó xác định bước kế, phải ghép VLearn/README/code/log; mô phỏng chọn action và AI đánh giá hệ quả | `spec_under_review(2).md`, `labsim_submission/spec.md` §1/§4 |
| M1 — Decision Simulator | Chọn Lab 3 → bốn stage thực hành → lựa chọn 3–4 action hoặc nhập tự do → AI tự mô tả consequence → lưu state/debrief; BM25/label nguồn là đề xuất | `lab_simulator_workflow_features(1).md`, `lab_situation(1).md` |
| M2 — Case Detective | Một incident chưa rõ nguyên nhân → giả thuyết → evidence phi tuyến → AI chất vấn → giải thích lại; một case, không theo tiến độ Lab | `2026-09-18-labsim-case-detective-mvp-design.md` |
| M3 — giao điểm mới | Chọn Lab → checkpoint theo mạch Lab → đọc/điều tra linh hoạt và AI coach → quiz theo key → tips theo ngữ cảnh → tổng kết + self-report Lab thật; một workflow cho mọi học viên | Quyết định và phản hồi mới nhất trong hội thoại; `2026-09-18-labsim-unified-workflow-design.md` |

## 2. Khác biệt cụ thể, có hệ quả triển khai

| Trục | Trước đây | Thiết kế mới | Vì sao/cái phải thay |
|---|---|---|---|
| User/entry | Người mới đang làm Lab hoặc người điều tra một incident | Người muốn học từ đầu, đang làm, ôn tập; **không chọn mode** | Một luồng, người học tự chọn đọc thêm/xin hint/điều tra; tránh phân đoạn giả tạo |
| Navigation | Theo stage Lab 3 **hoặc** chỉ một incident độc lập | Lab library → checkpoint theo thứ tự đã biên soạn | Cần Lab manifest + checkpoint content; không viết hardcode 4 stage |
| Nội dung | AI tự lấy nguồn và có thể sinh situation/consequence runtime | Human-curated, source-versioned scenario/evidence/quiz/tip | Không để AI bịa fact; bắt buộc review và provenance |
| Phi tuyến | Cây action → consequence → new situation, hoặc chỉ thứ tự mở evidence | Checkpoint theo thứ tự; đọc/evidence/hypothesis/feedback bên trong linh hoạt | Không cần state graph hệ quả kỹ thuật mở vô hạn |
| AI decision | AI đề xuất action và đánh giá hypothetical consequence | AI coach chọn cách chất vấn/giải thích theo nhận định + evidence đã xem | Một call kiểm soát; deterministic outcome/key ở ứng dụng |
| Retrieval | Có tham vọng index toàn bộ lab để AI dựng scenario | Index lab-scoped hỗ trợ mở rộng/tìm nguồn; evidence chính được gắn ID trước | Không để sai retrieval thay đổi ground truth của quiz/case; BM25 optional trong MVP timebox |
| Quiz | Chưa có hoặc bài trắc nghiệm ba lựa chọn từ draft | Câu VLearn + answer key **được người biên soạn xác nhận**; rule grader | Nguồn VLearn có multi-select/matching/ordering nhưng không đủ key cho mọi câu; không auto-grade từ đáp án suy đoán |
| Đo lường | Lý do quyết định, later chất lượng explanation trước/sau do AI | Quiz first attempt theo answer key; hành vi event; tự khai lab completion; AI feedback định tính | Không dùng LLM score mơ hồ làm deterministic hoặc đồng nhất click với hiểu biết |
| Trạng thái Lab thật | Có nguy cơ nhầm giả lập fork/install/test với thực tế | Pure simulation, self-report riêng, không verification | Không truy cập GitHub/VLearn học viên; giữ khả năng nói thật về năng lực |
| Tips | Không có | Card ngẫu nhiên trong danh sách đã duyệt theo ngữ cảnh | Scheduler deterministic khi test; tránh spoiler và gián đoạn |
| Resume/checkpoint load | State manager + rewind từng nhánh hoặc có resume phiên | **PENDING** resume từ checkpoint; phiên demo mới, checkpoint navigation trong phiên | Giữ lời hứa khớp tính năng có thể build |
| Tài nguyên Lab 3 | README/CODELAB/code/trace, bộ case A/B/C tự soạn | Bổ sung VLearn Day03 knowledge map, câu hỏi thật, rubric, milestones; vẫn đối chiếu code | Có khác biệt TASK 2.1 VLearn vs CODELAB/MCP; không auto resolve |
| Multi-agent/tool | Có ý tưởng đầy đủ retrieval/agent/tool chaining | Một coach call, read-only app tools, rule grader, không agent tự trị | Chi phí/rủi ro không có căn cứ cho multi-agent trong timebox |
| Demo claim | AI mô phỏng hệ quả và cải thiện hiểu biết | Minh họa interaction, quiz có key, self-report; hiệu quả vs GPT **chưa chứng minh** | Muốn claim hiệu quả phải có kiểm thử so sánh và kiểm tra học viên |

## 3. Các quyết định không nên lặng lẽ quay lại

1. **Không** phục hồi hai chế độ “Học hiểu/Thử sức”: người dùng đã bác bỏ phân chế độ.
2. **Không** đánh tráo `self_reported_completed` thành `verified_completed` hoặc `checkpoint_done` thành hoàn thành Lab thực tế.
3. **Không** cho model tự xây answer key hoặc observation/trace rồi xem đó là nguồn sự thật.
4. **Không** mặc định “load từ checkpoint” là feature đã có chỉ vì session state có `current_checkpoint_id`.
5. **Không** dùng số liệu khảo sát 60% tự đánh giá để suy ra tỷ lệ có năng lực chẩn đoán; không thay quality bar CP4 tùy tiện.
6. **Không** xem việc có nhiều Lab hoặc nhiều agent là điều kiện để MVP chứng minh giá trị; nếu nội dung chưa được duyệt thì không hiển thị là đã hỗ trợ.

## 4. Ảnh hưởng đến các artifact hiện có

- `labsim_submission/spec.md`: bản đã nộp là baseline lịch sử; **đề xuất** cập nhật §4, §5–§6 những flow/risk thay đổi, §8 phân công, §9 changelog bằng bản mới sau khi được duyệt. **Không tự sửa quality bar §7 đã khóa.** §1–§3 phải giữ ranh giới evidence chưa được xác minh; không đổi vấn đề/impact thành số liệu giả.
- `lab_simulator_workflow_features(1).md`, `lab_situation(1).md`: chuyển thành **idea bank/input cho content curation**, không coi consequence đã viết là observed fact, không lấy đúng/sai tuyệt đối nếu version Lab không thống nhất.
- `TEAM_TASK_SCENARIO_DESIGN.md`: tiếp tục giao việc human curation; bổ sung yêu cầu map checkpoint VLearn, fact/tip và verified answer key **sau khi nhóm duyệt quy trình mới**.
- Các design/plan cũ về AI tự sinh scenario hoặc Case Detective một incident: giữ làm lịch sử, đánh dấu superseded sau khi file thiết kế mới được người dùng duyệt; **không chạy nguyên xi implementation plan cũ**.

## 5. Hai bằng chứng cảnh báo từ nguồn được cung cấp

- `Pasted text(1).txt` (VLearn Day 03): Task 2.1 ghi hoàn thiện dispatcher trong `src/tools.py`; `CODELAB.md` của Lab 3 có Task 2.1 hoàn thiện `MCPAcademicServer.call_tool` trong `src/mcp_server.py`. Cần xác nhận version/lớp học trước khi dùng làm quiz về vị trí file.
- Nhiều câu VLearn là multi-select, matching và ordering; file text chỉ hiển thị một số dấu “Correct” của câu trả lời người học, **không phải một bảng đáp án đầy đủ có thể import thẳng vào grader**.

**Review gate:** Người dùng duyệt hai file này trước khi `writing-plans` xây implementation plan chính thức; không có claim đã triển khai, chạy thử hoặc commit Git.
