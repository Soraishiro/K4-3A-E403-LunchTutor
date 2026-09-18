# Case: Bẫy Vòng Lặp Vô Tận hay Ngắt Luồng Suy Luận? (Truncated ReAct Loop)

Người biên soạn: Đỗ Trịnh Huy Hoàng | Lab: Day 03 — Chatbot vs ReAct Agent | Trạng thái: Đã đối chiếu

## 1. Mạch lab đã rà

Mục tiêu & đầu ra: Xây dựng hệ thống ReAct Agent có khả năng suy luận đa bước (Multi-step Reasoning) và gọi công cụ thực thi (Native Tool Calling). Đảm bảo phân biệt rõ sự khác biệt giữa LLM Chatbot thông thường (Cấp 2) và ReAct Agent (Cấp 3).
Các chặng chính (theo VLearn / README / LAB-GUIDE):

1. Setup & Environment: Fork repo, tạo virtualenv (Python 3.10–3.12) và cài đặt dependencies.
2. Tooling & Dispatcher: Định nghĩa Tool Schemas JSON và lập trình hàm Dispatcher (`src/tools.py`).
3. ReAct Loop Execution: Hoàn thiện thuật toán vòng lặp ReAct Loop (`src/app.py`) xử lý chu trình Thought -> Action -> Observation.
4. Trace & Report: Xuất Waterfall Trace Log (`docs/trace_waterfall.json`) và hoàn thiện báo cáo đánh giá (`docs/trace_eval.md`).
   Điểm khó kỹ thuật đã chọn và vì sao đáng học: Vòng lặp ReAct bị ngắt sớm (Truncated Loop) tại `src/app.py`. Agent chỉ gọi duy nhất 1 Tool rồi lập tức dừng lại trả về kết quả chưa đầy đủ thay vì tiếp tục suy luận bước tiếp theo. Điều này giúp học viên hiểu rõ bản chất truyền nhận trạng thái `Observation` và cách quản lý danh sách `messages` trong ReAct Agent.

## 2. Incident brief — phần học viên thấy

Bối cảnh và triệu chứng: Hệ thống ReAct Agent nhận câu hỏi yêu cầu xử lý đa bước từ người dùng: _"Tôi muốn kiểm tra lịch trống của cố vấn Academic Advisor và đăng ký lịch hẹn vào thứ Ba tuần sau"_. Theo thiết kế, Agent cần gọi 2 công cụ nối tiếp: `check_advisor_availability` -> `schedule_appointment`. Tuy nhiên, thực tế Agent chỉ gọi duy nhất công cụ `check_advisor_availability`, xuất danh sách giờ trống rồi dừng hẳn luồng mà không thực hiện bước đặt lịch hẹn.
Nhiệm vụ điều tra: Đóng vai Case Detective phân tích bằng chứng để xác định nguyên nhân vì sao Agent không thực hiện được suy luận đa bước. Xác định lỗi xuất phát từ **Khai báo Tool Schema (`src/tools.py`)**, **Hàm Dispatcher (`src/tools.py`)**, hay **Logic Vòng lặp ReAct trong `src/app.py`**.
Thông tin CỐ Ý chưa cung cấp lúc bắt đầu: Mã nguồn xử lý vòng lặp `while` trong `src/app.py` và chi tiết trace log thực thi của lượt thoại.

## 3. Evidence board — học viên tự mở theo thứ tự bất kỳ

| ID  | Tiêu đề trung tính                  | Dữ kiện sẽ hiện                                                                                                                                                                                                                                                                                                                                | Nguồn chính xác                                          | Độ tin cậy  |
| --- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ----------- |
| E1  | User Interaction & Execution Trace  | **User:** _"Kiểm tra lịch trống của cố vấn và đặt lịch giúp tôi vào thứ Ba."_<br>**Step 1 (Action):** `check_advisor_availability(advisor_id="ADV-01")`<br>**Observation 1:** `{"available_slots": ["10:00 AM", "02:00 PM"]}`<br>**Agent Final Answer:** _"Cố vấn có các khung giờ trống: 10:00 AM và 02:00 PM."_ (Dừng luồng, chưa đặt lịch). | `docs/trace_waterfall.json` (Trace ID: `REACT-MULTI-02`) | Đã xác minh |
| E2  | Python Tool Dispatcher Logic        | Code hàm `dispatch_tool_call`: Nhận `tool_name` và `arguments`, thực thi hàm tương ứng và trả về `Observation` dưới dạng JSON string. Kiểm thử độc lập `python src/tools.py` hoạt động chính xác.                                                                                                                                              | `src/tools.py` (Dòng 85–110)                             | Đã xác minh |
| E3  | ReAct Loop Algorithm Implementation | Đoạn code vòng lặp ReAct trong `src/app.py`:<br>`python<br>while step < MAX_ITERATIONS:<br>    response = llm.chat(messages)<br>    if response.tool_calls:<br>        tool_result = dispatch_tool_call(...)<br>        # TODO: Append result and continue loop<br>        break  # Lệnh break bị đặt sai vị trí tại đây<br>`                  | `src/app.py` (Dòng 52–68)                                | Đã xác minh |
| E4  | Tool JSON Schema Definitions        | Định dạng JSON Schema của 2 công cụ `check_advisor_availability` và `schedule_appointment` được khai báo đầy đủ các trường `type`, `description` và `required`.                                                                                                                                                                                | `src/tools.py` (Dòng 15–50)                              | Đã xác minh |

## 4. Đáp án NỘI BỘ — không hiển thị khi điều tra

Cơ chế lỗi / điều chưa thể kết luận: Vòng lặp ReAct bị ngắt sớm (Truncated Loop) do lệnh `break` bị chèn cứng ngay sau khi thực thi xong Tool Call đầu tiên trong `src/app.py`. Điều này khiến Agent không thể gửi kết quả `Observation` ngược lại cho LLM để thực hiện lượt suy luận kế tiếp.
Chuỗi nhân quả: LLM phát hiện câu hỏi cần dùng Tool 1 -> `dispatch_tool_call()` thực thi thành công -> Gặp lệnh `break` trong khối `if response.tool_calls` -> Vòng lặp `while` bị thoát -> LLM không nhận được `Observation` của Tool 1 để kích hoạt lượt gọi Tool 2 (`schedule_appointment`).
Giả thuyết thay thế hợp lý:

1. _Giả thuyết A (Sai):_ LLM không nhận biết được tool `schedule_appointment` do khai báo Schema (E4) bị thiếu hoặc sai định dạng.
2. _Giả thuyết B (Chính xác):_ Cấu trúc vòng lặp ReAct trong `src/app.py` (E3) chứa lệnh `break` vô lý, ngắt luồng trước khi Agent kịp nạp Observation vào `messages`.
3. _Giả thuyết C (Sai):_ Hàm `dispatch_tool_call` trong `src/tools.py` (E2) bị lỗi runtime khi xử lý dữ liệu.
   Bằng chứng phân biệt giữa các giả thuyết: So sánh E1 (Trace Log) và E3 (`src/app.py`): Trace Log ghi nhận Tool 1 chạy thành công (loại trừ C) và Schema E4 khai báo đúng chuẩn. Tuy nhiên E3 cho thấy lệnh `break` ngắt vòng lặp ngay ở lượt đầu tiên, ngăn cản suy luận đa bước.
   Lời giải/debrief có dẫn nguồn:
   Để khắc phục, cần loại bỏ lệnh `break` ngắt sớm và bổ sung kết quả Observation vào danh sách hội thoại:

```python
messages.append({"role": "tool", "content": tool_result})
# Giữ vòng lặp tiếp tục chạy cho các bước suy luận sau
```
