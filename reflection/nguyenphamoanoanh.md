# Thu hoạch cá nhân — Nguyễn Phạm Oanh Oanh (2A202602665)

## Vai trò
Spec/decision owner

## Phần việc trực tiếp
- Dẫn dắt việc viết spec.md theo template §§1–9, duy trì scope thống nhất với bản design đã duyệt.
- Đối chiếu CP4/changelog/quality bar: giữ nguyên quality bar "đạt ≥16/20 case (80%) theo 3 chiều, 0/20 citation bịa, 0/20 tuyên bố chưa thực thi, 0/20 sửa/nộp code thật".
- Quản lý risk: theo dõi 12 đường lỗi thiết kế, đảm bảo coverage trong golden set.
- Ko trách nhiệm cho phần demo/user validation (do "Dang Thai Anh" sổ hôm ở phân công spec nhưng không có trong danh sách thành viên), nhóóm quyết định tự thực hiện R6.

## Ứng dụng AI trong quá trình xây dựng
- Sử dụng AI hỗ trợ phân tích động content từ chatlog: đếm số lượt xin đáp án, đề xuất pain point.
- Prompt AI review để đối chiếu spec với rubric, phát hiện gap.
- Không dùng AI sinh quyết định — quyết định chọn lát cắt, automation level, quality bar đều do nhóm thỏo thuyết.

## Bài học thực tế từ trường hợp thất bại của nhóm
- **Phân công chưa rõ ràng (gap "Dang Thai Anh"):** Spec ban đầu gán vai trò Demo/user validation cho "Dang Thai Anh" nhưng người này không có trong TEAMMATES.md. Nhóm phải tự phân công lại để tránh thiếu R6. Bài học: verify đủ thành viên trước khi gán vai trò, đặc biệt là vai trò ngoại lệ.
- **Quality bar không được chính xác mở rộng:** Ban đầu có xu hướng so sánh trực tiếp hai bộ golden set (CP4 scenario-generation vs CP6 coach). Điều này gây nhầm lẫn về mức độ khó. Bài học: giữ nguyên definition gốc, không gộp nhỏ các phép đo khác nhau.
