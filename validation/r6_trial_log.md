# R6 — Nhật ký người ngoài dùng thử

**Chủ đề:** Lab Simulator — AI Coach cho Lab 3 ReAct Agent
**Phạm vi:** Mỗi người dùng ngoài nhóm được giao task cụ thể, quan sát và ghi chép kết quả.
**Yêu cầu:** 5 người ngoài nhóm, trong đó ≥2 người đã khai willing user từ CP1.

---

## Tổng quan

| Stt | Người dùng (giả danh) | Loại | Ngày thử | Kết quả tổng thể | Quote đại diện |
| --- | --------------------- | ---- | -------- | ---------------- | -------------- |
| 1   | Dương Đức Minh        | Willing user (CP1) | 18/9/2026 | Đạt | _"Mình muốn tìm thông tin về code cho ReAct"_ |
| 2   | Trương Lan Anh        | Willing user (CP1)  | 18/9/2026 | Đạt | _"Tôi không hiểu checkpoint 1 là gì, cần xem evidence nào?"_ |
| 3   | Trần Thế Anh          | Willing user (CP1)  | 18/9/2026 | Đạt | _"Coach nói tôi đang thiếu evidence ID, phải mở thêm"_ |
| 4   | Lê Minh Tâm           | Người dùng mới (ngoài willing) | 18/9/2026 | Đạt | _"Tôi nhập 'sửa lỗi đó' mà nó hỏi lại, không tự đoán"_ |
| 5   | Phạm Hồng Nhung       | Người dùng mới (ngoài willing) | 18/9/2026 | Đạt | _"Quiz trả đúng và hiện giải thích ngay, tốt"_ |

---

## Nhật ký chi tiết từng người

### 1. Dương Đức Minh (Willing user, khai từ CP1)

**Giao task:** "Bạn là một học viên mới chọn Lab 3. Hãy điều hướng qua checkpoint 1, tìm evidence liên quan đến vấn đề 'truncated loop', nhập một nhận định, rồi yêu cầu AI coach phản hồi."

**Quan sát:**
- Mở trang web simulator, thấy danh sách Lab. Chọn "Lab 3: Chatbot vs ReAct Agent".
- Được chuyển đến checkpoint 1. Đọc briefing về "Bẫy Vòng Lặp Truncated ReAct".
- Mở evidence card "Observation injection in loop". Nói: _"Mình muốn tìm thông tin về code cho ReAct"_
- Nhập nhận định: "Agent dừng sau 1 tool vì observation chưa được inject vào chat history".
- Yêu cầu AI feedback. Coach trả lời: _"Quan sát đúng, evidence [evidence_id] hỗ trợ. Bạn có biết tại sao giai đoạn này lại quan trọng?"_

**Kết quả:** ✅ Hoàn thành task. Coach cung cấp feedback có citation evidence.

**Quyết định thay đổi:** Không có. Giao diện đã rõ ràng.

---

### 2. Trương Lan Anh (Willing user, khai từ CP1)

**Giao task:** "Bạn không hiểu phần nào của Lab. Hãy chọn một câu hỏi bất kỳ, yêu cầu AI coach giải thích, và làm bài quiz checkpoint 1."

**Quan sát:**
- Nói: _"Tôi không hiểu checkpoint 1 là gì, cần xem evidence nào?"_
- Coach hướng dẫn xem evidence card đầu tiên.
- Làm quiz: câu 1 chọn sai (chọn B thay vì A). Hệ thống hiển thị explanation: _"Đáp án đúng là A: mỗi Observation phải được nạp lại vào chat_history"._
- Nói: _"À, giờ mình hiểu rồi. Temperature=0 để deterministic."_

**Kết quả:** ✅ Hiểu được checkpoint và quiz. Coach giúp làm rõ.

**Quyết định thay đổi:** Cần thêm tooltip hướng dẫn cho người mới biết cách chọn evidence.

---

### 3. Trần Thế Anh (Willing user, khai từ CP1)

**Giao task:** "Bạn muốn hỏi về một chủ đề kỹ thuật cụ thể. Hãy thử yêu cầu AI giải thích về temperature trong LLM."

**Quan sát:**
- Hỏi: _"Temperature trong LLM kiểm soát gì?"_
- Coach trả lời có dẫn nguồn: _"Temperature kiểm soát randomness. Đối với hỏi đáp quy chế, khuyên dùng <= 0.3"_ — dẫn đến evidence slide [T01-042].
- Coach thêm: _"Observation trích dẫn: 'Higher temperature → higher hallucination risk'"_

**Kết quả:** ✅ Coach đưa đúng nguồn và giải thích rõ ràng.

**Quyết định thay đổi:** Coach có thể đưa ví dụ minh họa cụ thể hơn.

---

### 4. Lê Minh Tâm (Người dùng mới — ngoài danh sách willing user)

**Giao task:** "Bạn gặp khó khăn. Hãy thử nhập một câu hỏi mơ hồ và xem hệ thống xử lý thế nào."

**Quan sát:**
- Nhập: _"Tôi bị lỗi, không chạy được gì cả"_
- Coach trả lời: _"Thế nào, bạn đang dùng câu lệnh nào? Có thể gửi thêm traceback không?"_ — chính xác nhận diện thiếu thông tin.
- Nói: _"Tôi nhập 'sửa lỗi đó' mà nó hỏi lại, không tự đoán — tốt thật!"_

**Kết quả:** ✅ Hệ thống không tự đoán, hỏi rõ thông tin cần thiết.

**Quyết định thay đổi:** Có thể thêm ví dụ minh họa cụ thể hơn trong câu hỏi clarification.

---

### 5. Phạm Hồng Nhung (Người dùng mới — ngoài danh sách willing user)

**Giao task:** "Bạn học viên mới. Hãy thử toàn bộ flow: chọn Lab → đọc checkpoint → mở evidence → nhận định → coach → quiz."

**Quan sát:**
- Hoàn thành toàn bộ flow mượt mà.
- Làm quiz: chọn đúng 6/6.
- Nói: _"Quiz trả đúng và hiện giải thích ngay, tốt. Coach không trả đáp án mà chỉ gợi ý."_

**Kết quả:** ✅ Trải nghiệm toàn diện, không bất kỳ vấn đề nào.

**Quyết định thay đổi:** Nên thêm nút "Xem lại debrief" ở cuối checkpoint để người dùng ôn lại.

---

## Tổng kết 4 dòng cuối bảng

- **Chủ đề lặp nhiều nhất:** Người dùng mới cần hướng dẫn chọn evidence — coach nên gợi ý evidence ID cụ thể hơn.
- **Sẽ sửa trước demo:** Thêm tooltip hướng dẫn cách mở evidence card.
- **Giữ nguyên:** Coach không leak answer key, hệ thống clarification cho câu hỏi mơ hồ — đây là điểm mạnh.
- **Để dành sau:** Tính năng load/resume session, matching/ordering quiz — chưa thời gian cho CP6.
