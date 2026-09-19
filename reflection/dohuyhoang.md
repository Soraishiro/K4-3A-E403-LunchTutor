# Thu hoạch cá nhân — Đỗ Trịnh Huy Hoàng (2A202602392)

## Vai trò
Prompt/AI + evaluation owner

## Phần việc trực tiếp
- Thiết kế và kiểm soát boundary của AI coach: chỉ truyền nhận định của học viên + evidence IDs đã mở + hint_level vào prompt, tuyệt đối không leak answer key, solution nội bộ hoặc evidence chưa mở.
- Xây dựng hệ thống coach feedback validator: kiểm tra schema JSON, citations, và uncertainty level trả về từ model sau mỗi lần gọi.
- Xây dựng golden set 20 case phân bổ theo 4 lớp chỗ khó, đảm bảo ≥2 case mỗi lớp, 8–10 case thường, 2–4 case hi r rủi.
- Chạy eval và ghi nhận kết quả thực: 20/20 pass, 0 hallucination, 0/20 hard-bar violation.

## Ứng dụng AI trong quá trình xây dựng
- Sử dụng AI sinh nhãn intent (REFUSE_AND_PROBE, CLARIFY_AMBIGUOUS, CITE_GROUNDED...) cho golden set dựa trên nguồn chatlog thật, sau đó review thủ công để tránh vêu béo.
- Prompt coach được thiết kế để tách rõ quan sát (evidence) và suy luận (hypothesis), yêu cầu model luôn trích dẫn evidence ID.
- Thiết kế hệ thống error recovery: timeout/provider error/schema error → giữ session, báo retry, không tính là feedback thành công.

## Bài học thực tế từ trường hợp thất bại của nhóm
- **Prompt injection case (TC-03):** Ban đầu coach prompt chưa có instruction mạnh về việc từ chối override hệ thống. Kết quả là model có xu hưởng tuân theo lệnh injection. Bài học: luôn đặt system instruction phòng thủ đầu tiên và test với adversarial prompt trước khi triển khai.
- **Câu hỏi về answer key:** Một số case (TC-01, TC-04) ban đầu coach đưa ra gợi ý gần giống đáp án. Điều chỉnh bằng cách rút ngắn context và thêm rõ "do not reveal solution" trong prompt.
