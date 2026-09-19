# Thu hoạch cá nhân — Vũ Hiếu Thiên (2A202602867)

## Vai trò
Code + UX owner

## Phần việc trực tiếp
- Cài đặt hệ thống session management: tạo session mới, lưu lab_id, current_checkpoint, checkpoint_completed, viewed_evidence_ids, viewed_tip_ids, hypothesis_versions, hint_level.
- Xây dựng API endpoints: GET /api/labs, POST /api/session, POST /api/session/checkpoint, POST /api/session/next-checkpoint, POST /api/session/tip, POST /api/session/evidence, POST /api/session/hypothesis, POST /api/session/self-report.
- Triển khai module labs.py: LabBundle, LabCheckpoint, EvidenceCard, TipCard dataclasses; day03 bundle với 2 checkpoint, 11 evidence cards, 4 tip cards.
- Cập nhật models.py: thêm lab_id, current_checkpoint, checkpoint_completed dict, viewed_tip_ids vào SessionState.
- Cập nhật quiz.py: 6 câu hỏi Lab 3 với rule-based grading (q1_tool_schema, q2_error_propagation, q3_react_order, q4_break_fix, q5_guardrail_logic, q6_dangerous_keywords).
- Xây dựng tip scheduler: chọn ngẫu nhiên trong tập hợp hợp lệ, tránh lặp, tránh spoiler cho checkpoint hiện tại, dùng seed cố định trong test.

## Ứng dụng AI trong quá trình xây dựng
- Sử dụng AI code completion (Copilot) để hỗ trợ implement các endpoint và data structures, nhưng review thủ công từng dòng.
- Thiết kế tip scheduler với random seeded để có tính tái lập trong test.
- Debug lỗi UnboundLocalError trong tip endpoint: session được retrieve sau khi tham chiếu đến session.current_checkpoint → sắp xếp lại thứ tự.

## Bài học thực tế từ trường hợp thất bại của nhóm
- **Lỗi thứ tự khai báo biến (UnboundLocalError):** Trong endpoint /api/session/tip, tham chiếu `session.current_checkpoint` trước khi gán `session = get_session(session_id)`. Python báo lỗi UnboundLocalError. Bài học: luôn đặt việc lấy dữ liệu (get_session) trước khi sử dụng, và dùng static analysis để kiểm tra.
- **Import pydantic:** models.py phụ thuộc vào pydantic nhưng môi trường chạy test chưa cài đặt. Phát hiện thông qua pytest và phải chuyển sang Python có pydantic đã cài. Bài học: kiểm tra dependency trong CI ngay từ đầu.
