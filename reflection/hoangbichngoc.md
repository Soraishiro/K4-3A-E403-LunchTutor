# Thu hoạch cá nhân — Hoàng Bích Ngọc (2A202602766)

## Vai trò
Content + evidence owner

## Phần việc trực tiếp
- Rà soát nguồn dữ liệu Lab 3: VLearn Day 03 `Pasted text(1).txt`, README, CODELAB, LAB-GUIDE, source code, test, trace — xác định phiên bản cohort và độ chính xác của từng nguồn.
- Phát hiện mâu thuẫn giữa VLearn và CODELAB ở Task 2.1 (dispatcher trong `src/tools.py` vs `src/mcp_server.py` MCP), gắn nhão `conflict` và chưa publish fact liên quan đến vị trí file cho đến khi có kết quả review cohort.
- Xây dựng nguồn evidence bundle cho checkpoint 1 (truncated ReAct loop): 11 EvidenceCard với chunk ID tham chiếu đến `data/generated/day03/source_chunks.jsonl`, đã gán nhãn instruction/code/reported/verified_observation.
- Xác minh và duyệt quiz key: chốt answer key từ nguồn VLearn, không tự suy đáp án từ nhãn "Your answer".

## Ứng dụng AI trong quá trình xây dựng
- Dùng AI hỗ trợ inventory và phân loại nguồn: tự động gán nhãn instruction/code/reported/hypothetical cho các chunk, sau đó review thủ công.
- Sử dụng AI để đối chiếu nội dung giữa README và CODELAB, phát hiện điểm mâu thuẫn ở Task 2.1.
- Thiết kế filter cho evidence retrieval: chỉ trả về evidence thuộc cùng lab_id, có provenance, đã được duyệt — AI không được dùng kết quả search tùy ý thay thế đáp án.

## Bài học thực tế từ trường hợp thất bại của nhóm
- **Mâu thuẫn VLearn vs CODELAB (R01):** Khi tích hợp nội dung Task 2.1, nhóm nhận ra VLearn chỉ dispatcher trong `src/tools.py` còn CODELAB chỉ `src/mcp_server.py`. Nếu không cẩn trọng, coach sẽ dẫn đến đường link sai. Bài học: luôn đối chiếu đa nguồn trước khi publish fact, và thiết kế error case R01 ngay từ đầu.
- **Quiz key chưa đủ:** Một số case quiz từ VLearn chỉ có đáp án "Your answer" chứ không có key đầy đủ. Nhóm đã loại bỏ các câu hỏi này khỏi golden set thay vì ép buộc rule-grade.
