# Pet Care Planner — Hướng dẫn chạy

## Dữ liệu và kiến trúc

- Hai công cụ: `query_pet_care` (tra cứu) và `schedule_pet_care` (đặt lịch).
- Dữ liệu minh họa: `config/pet_care_seed.json`. PET001 là chó Mít, PET002 là chó Bông, PET003 là mèo Miu.
- Các lịch minh họa cố định vào ngày **20/09/2026**, múi giờ Asia/Bangkok. Đây là dữ liệu bài lab, không phải dịch vụ thực tế.
- Chế độ tương tác lưu lịch vào `data/pet_care.sqlite3` (không commit). `PET_CARE_DB` có thể chỉ định đường dẫn khác.
- Test suite tạo database riêng trong bộ nhớ cho mỗi test, không thay đổi lịch tương tác. TC05 chủ động tạo một đặt chỗ cạnh tranh; sự kiện này được ghi là `TEST_SETUP`.
- MCP server là mô phỏng trong cùng tiến trình theo starter lab, có envelope JSON-RPC 2.0; chưa triển khai giao thức MCP qua mạng.
- Các trường `thought` trong trace là mô tả hành động quan sát được, không phải suy luận nội bộ của mô hình. Latency được đo thực tế.

## Lệnh PowerShell

Theo README, sử dụng Python 3.10–3.12 và cài `requirements.txt` trong môi trường ảo.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/mcp_server.py
.\.venv\Scripts\python.exe src/app.py --all --provider mock
.\.venv\Scripts\python.exe src/app.py --all --require-live
.\.venv\Scripts\python.exe src/app.py --interactive --require-live --trace docs/trace_interactive_live.json
.\.venv\Scripts\python.exe src/app.py --baseline --require-live
```

Chọn `LLM_PROVIDER=gemini` cùng `GEMINI_API_KEY` và model Gemini, hoặc `LLM_PROVIDER=openai` cùng `OPENAI_API_KEY` và model OpenAI trong `.env`. Khi đổi provider, phải đổi `LLM_MODEL` cho phù hợp. Chương trình không chuyển về mock khi API thật lỗi.

Ví dụ hội thoại:

> Tôi là Ngọc. Tra cứu lần tắm gần nhất của PET001 rồi đặt lịch tắm ngày 20/09/2026 sau 14:00, không quá 200.000 đồng.

Mock là bộ mô phỏng quy tắc nhỏ dành cho năm tình huống mẫu, không phải bộ hiểu ngôn ngữ tổng quát. Chế độ tương tác bằng LLM thật giữ lịch sử hội thoại, nên có thể hỏi bổ sung thông tin qua nhiều lượt.

## Kết quả và nghiệm thu

- Offline: `docs/trace_offline.json`, `docs/eval_offline.json`.
- Live mặc định: `docs/trace_waterfall.json`, `docs/eval_live.json`.
- Dùng `--trace đường_dẫn.json` để chọn file trace khác.
- `--all` trả exit code 1 nếu bất kỳ test nào không đạt. Các kiểm tra tự động đánh giá hành động, trạng thái database và một số điều kiện câu trả lời; cần đọc lại câu trả lời cuối để kiểm tra chất lượng diễn đạt.
- Chỉ dùng trace API thật thành công làm bằng chứng trong `docs/trace_eval.md`. Không coi số test đã thực thi là số test đã đạt.

Tham khảo cách đưa kết quả tool trở lại hội thoại: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) và [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling).
