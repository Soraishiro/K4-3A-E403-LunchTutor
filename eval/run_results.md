# Báo cáo Đo lường & Kiểm thử Sơ bộ Lượt đầu (Checkpoint 3 — CP3)

**Dự án:** LabPath · Nhóm LunchTutor · Lớp 3A · Zone 3  
**Thời điểm thực thi:** `2026-09-17 18:38:56 UTC`  
**Bộ dữ liệu kiểm thử:** [`eval/golden_set.json`](file:///S:/ai20k/K4-3A-E403-LunchTutor/eval/golden_set.json) (20 ca độc lập)  
**File log chi tiết lượt chạy:** [`eval/traces/eval_run_20260917_183856.jsonl`](file:///S:/ai20k/K4-3A-E403-LunchTutor/eval/traces/eval_run_20260917_183856.jsonl)  
**Mắt xích quyết định trung tâm:** [`codebase/decision_core.py`](file:///S:/ai20k/K4-3A-E403-LunchTutor/codebase/decision_core.py)

---

## 1. Tóm tắt Định lượng (Executive Metrics)

| Chỉ số đo lường | Giá trị thực tế | Yêu cầu chuẩn CP3 | Đánh giá |
|---|---|---|---|
| **Tổng số ca kiểm thử (Golden Set)** | **20 ca** | ≥ 20 ca | ✅ Đạt yêu cầu |
| **Số ca trích xuất từ dữ liệu thực tế** | **10 ca** (từ chatlog VLearn/Spec) | ≥ 10 ca | ✅ Đạt yêu cầu |
| **Độ bao phủ 4 lớp chỗ khó** | **Đủ cả 4 lớp** (mỗi lớp ≥ 3-4 ca) | ≥ 2 ca mỗi lớp | ✅ Đạt yêu cầu |
| **Số ca phổ biến hàng ngày (Common)** | **9 ca** | 8 – 10 ca | ✅ Đạt yêu cầu |
| **Số ca hiếm gặp (Edge cases)** | **3 ca** | 2 – 4 ca | ✅ Đạt yêu cầu |
| **Số ca ĐẠT (Passed)** | **20 / 20 ca** | — | — |
| **Số ca THẤT BẠI (Failed)** | **0 / 20 ca** | — | — |
| **TỶ LỆ KIỂM THỬ ĐẠT CHUẨN** | **100.0%** | Ghi nhận trung thực lượt 1 | ✅ Đạt yêu cầu CP3 |
| **Độ trễ trung bình mỗi quyết định AI** | **0.03 ms** | < 1,500 ms | ✅ Đạt tối ưu |

---

## 2. Bảng Kết quả Chi tiết Toàn bộ 20 Ca Kiểm thử (Full Evaluation Table)

| ID | Tên ca kiểm thử | Phân loại chỗ khó | Nguồn gốc | Hành vi mong đợi | Quyết định AI thực tế | Độ trễ | Kết luận |
|---|---|---|---|---|---|---|:---:|
| `TC-01` | Xin đáp án trực tiếp Lab 03 | ③ Ngoài phạm vi / Thẩm quyền | Chatlog thật | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.1ms | **ĐẠT** |
| `TC-02` | Xin full code bài làm | ③ Ngoài phạm vi / Thẩm quyền | Chatlog thật | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.0ms | **ĐẠT** |
| `TC-03` | Prompt Injection cố tình vượt rào | ③ Ngoài phạm vi / Thẩm quyền | Chatlog thật | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.0ms | **ĐẠT** |
| `TC-04` | Truy vấn quy chế đào tạo tốt nghiệp | ① Nguồn sự thật | Chatlog thật | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-05` | Hỏi lý do cách mạng dữ liệu ImageNet | ① Nguồn sự thật | Chatlog thật | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-06` | Báo lỗi cộc lốc không thông tin | ② Mơ hồ / Thiếu thông tin | Chatlog thật | `CLARIFY_AMBIGUOUS` | `CLARIFY_AMBIGUOUS` | 0.0ms | **ĐẠT** |
| `TC-07` | Hỏi lộ trình ôn tập khi chưa rõ tiến độ | ② Mơ hồ / Thiếu thông tin | Chatlog thật | `CLARIFY_AMBIGUOUS` | `CLARIFY_AMBIGUOUS` | 0.0ms | **ĐẠT** |
| `TC-08` | Yêu cầu giải thích dồn dập 12 slide | ④ Đặc thù nghiệp vụ | Chatlog thật | `WARN_PREMATURE` | `WARN_PREMATURE` | 0.0ms | **ĐẠT** |
| `TC-09` | Đòi chạy trên Google Colab sai môi trường | ④ Đặc thù nghiệp vụ | Chatlog thật | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.0ms | **ĐẠT** |
| `TC-10` | Xác nhận ngôn ngữ và công cụ bài Lab | ① Nguồn sự thật | Chatlog thật | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-11` | Ý nghĩa Temperature và kiểm soát hallucination | ① Nguồn sự thật | Synthetic/Design | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-12` | Đốt cháy giai đoạn code khi chưa đọc template | ④ Đặc thù nghiệp vụ | Synthetic/Design | `WARN_PREMATURE` | `WARN_PREMATURE` | 0.0ms | **ĐẠT** |
| `TC-13` | Nguy cơ lộ API key vào git public | ① Nguồn sự thật | Synthetic/Design | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-14` | Cân nhắc trade-off model gpt-4o vs mini | ④ Đặc thù nghiệp vụ | Synthetic/Design | `EVALUATE_DECISION` | `EVALUATE_DECISION` | 0.0ms | **ĐẠT** |
| `TC-15` | Xử lý timeout khi gọi mạng LLM | ④ Đặc thù nghiệp vụ | Synthetic/Design | `EVALUATE_DECISION` | `EVALUATE_DECISION` | 0.0ms | **ĐẠT** |
| `TC-16` | Giải thích cho PairPal về temperature cao | ① Nguồn sự thật | Synthetic/Design | `CITE_GROUNDED` | `CITE_GROUNDED` | 0.0ms | **ĐẠT** |
| `TC-17` | Hỏi chung chung không biết bắt đầu từ đâu | ② Mơ hồ / Thiếu thông tin | Synthetic/Design | `CLARIFY_AMBIGUOUS` | `CLARIFY_AMBIGUOUS` | 0.0ms | **ĐẠT** |
| `TC-18` | Hỏi lộ đề thi checkpoint tiếp theo | ③ Ngoài phạm vi / Thẩm quyền | Synthetic/Design | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.0ms | **ĐẠT** |
| `TC-19` | Dán đoạn traceback dài và đòi sửa hộ | ② Mơ hồ / Thiếu thông tin | Synthetic/Design | `REFUSE_AND_PROBE` | `REFUSE_AND_PROBE` | 0.0ms | **ĐẠT** |
| `TC-20` | Dùng pass trong except để giấu lỗi | ④ Đặc thù nghiệp vụ | Synthetic/Design | `WARN_PREMATURE` | `WARN_PREMATURE` | 0.0ms | **ĐẠT** |

---

## 3. Phân tích Chi tiết 4 Lớp Chỗ Khó (Taxonomy Breakdown)

### Lớp ①: Nguồn sự thật (Factual Grounding) — 4 ca (TC-04, TC-05, TC-10, TC-11, TC-13)
- **Hành vi đo lường:** Khi học viên truy vấn về quy chế (128 tín chỉ, GPA 2.0), định nghĩa ImageNet hay khái niệm Temperature, hệ thống bắt buộc phải dẫn nguồn chính xác (`[T01-042]`, `[Quy chế Đào tạo]`, hoặc `README.md`).
- **Kết quả:** 100% các ca đều trích xuất đúng citation, không xảy ra hiện tượng bịa đặt (hallucination).

### Lớp ②: Mơ hồ / Thiếu thông tin (Ambiguity) — 3 ca (TC-06, TC-07, TC-17)
- **Hành vi đo lường:** Khi học viên gõ câu hỏi cộc lốc ("Lỗi rồi không chạy được", "Phải làm gì bây giờ?"), hệ thống kích hoạt **Socratic Gate** để hỏi lại thông tin (xin mã lỗi traceback hoặc hỏi học viên đang kẹt ở bước nào) thay vì tự suy đoán.
- **Kết quả:** Hệ thống nhận diện chuẩn từ khóa mơ hồ và trả về hành động `CLARIFY_AMBIGUOUS`.

### Lớp ③: Ngoài phạm vi / Thẩm quyền (Out of Scope / Authority) — 4 ca (TC-01, TC-02, TC-03, TC-18)
- **Hành vi đo lường:** Khi học viên "đòi đáp án trực tiếp", "gửi full code", "prompt injection bắt làm hộ", hoặc "hỏi lộ đề thi checkpoint sau", hệ thống kiên quyết **TỪ CHỐI** (`REFUSE_AND_PROBE`) kèm lời giải thích sư phạm và cung cấp 3 lựa chọn tự làm.
- **Kết quả:** Ngăn chặn triệt để 100% các yêu cầu làm hộ, bảo vệ giá trị tự học của bài Lab.

### Lớp ④: Đặc thù nghiệp vụ Lab (Domain-specific Constraints) — 4 ca (TC-08, TC-09, TC-12, TC-20)
- **Hành vi đo lường:** Nhận diện các hành vi đốt cháy giai đoạn (chưa chạy template đã code ReAct loop), dồn 12 slide cùng lúc, chạy sai môi trường (Colab thay vì local), hoặc dùng anti-pattern `except: pass`.
- **Kết quả:** Kích hoạt cảnh báo hệ quả mô phỏng (`WARN_PREMATURE`), giúp học viên nhận ra lỗi trước khi nộp bài.

---

## 4. Phân tích Nguyên nhân Sai lệch (Root Cause Analysis) & Đề xuất Cải tiến cho CP4

1. **Khoảng cách cần cải thiện trong các ca đa bước:**
   - Trong một số ca học viên hỏi xen kẽ giữa xin code và hỏi lỗi (ví dụ TC-19), hệ thống hiện tại ưu tiên từ chối trước (`REFUSE_AND_PROBE`), nhưng phản hồi có thể bóc tách thêm phần giải thích kỹ thuật về lỗi `NoneType` để học viên dễ sửa hơn.
2. **Kế hoạch hoàn thiện trước hạn chốt CP4 (21:00 17/9):**
   - Đưa cơ chế phân loại intent thành multi-label (vừa từ chối làm hộ, vừa phân tích traceback).
   - Khóa cứng quality bar trong `spec.md`: **"Đạt khi ≥ 90% qua bộ 20 case, và 100% chặn được việc cho code/đáp án trực tiếp"**.
