# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Lê Quang Ngọc
> **Mã Sinh Viên / Mã Học viên:** 2A202602664
> **Chủ đề Lựa chọn:** Đề tài Mở — Pet Care Planner (Trợ lý lập lịch chăm sóc thú cưng)

### Mô tả bài toán và phạm vi triển khai

Trợ lý giúp chủ nuôi tra cứu hồ sơ, lịch sử chăm sóc và đặt lịch dịch vụ tắm, chải hoặc cắt tỉa lông cho thú cưng. Người dùng đưa ra mã thú cưng, dịch vụ mong muốn, khoảng thời gian và ngân sách. Agent kiểm tra lần chăm sóc gần nhất, lịch đã đặt và các khung giờ dịch vụ còn trống, sau đó chọn lịch đáp ứng yêu cầu để đặt khi đã đủ thông tin. Nếu không có lịch phù hợp, Agent thông báo và đề xuất lựa chọn khác dựa trên dữ liệu công cụ trả về.

**Hai công cụ đã triển khai qua MCP mô phỏng của bài lab:**

| Công cụ | Chức năng | Tham số chính |
| :--- | :--- | :--- |
| `query_pet_care` | Tra cứu hồ sơ thú cưng, lịch sử chăm sóc, lịch hẹn hiện có và các khung giờ phù hợp với loại thú cưng, dịch vụ và khoảng ngày; trả về mã khung giờ, thời gian, thời lượng và giá. | `pet_id`, `service_type`, `date_from`, `date_to` |
| `schedule_pet_care` | Kiểm tra lại khung giờ còn trống và xung đột lịch của thú cưng, tạo lịch hẹn và cập nhật trạng thái khung giờ; trả về mã lịch hẹn hoặc lý do thất bại. | `pet_id`, `slot_id`, `owner_name` |

**Ví dụ yêu cầu:** “Tôi là Ngọc. Kiểm tra lần tắm gần nhất của bé Mít, mã PET001, rồi đặt một lịch tắm còn trống trong ngày 20/09/2026, sau 14:00, giá không quá 200.000 đồng.”

**Phạm vi bài lab:** Hồ sơ, lịch sử chăm sóc, khung giờ dịch vụ và lịch hẹn được lưu bằng SQLite, khởi tạo từ `config/pet_care_seed.json`. Dữ liệu là minh họa, các lịch mẫu vào ngày 20/09/2026, múi giờ Asia/Bangkok. Chương trình sử dụng native tool calling và MCP mô phỏng trong cùng tiến trình theo starter lab, chưa triển khai MCP qua mạng. Tập trung vào lịch chăm sóc thông thường; chưa tích hợp tư vấn y tế thú y, thanh toán, thông báo tự động hay cơ sở dịch vụ thực tế.

**Kiểm soát đã bổ sung:** Chặn mã thú cưng chưa được người dùng cung cấp; kiểm tra dịch vụ theo loại thú cưng; kiểm tra trùng lịch và khung giờ đã được đặt trong transaction SQLite. Khi đặt thất bại, Agent chỉ được tra cứu lại để đề xuất phương án, không tự tạo lịch thay thế trong cùng lượt. API lỗi được ghi rõ, không tự chuyển sang mock.

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Agent xác định thú cưng và dịch vụ, tra cứu lịch sử chăm sóc, đối chiếu lịch hẹn hiện có, thời gian và giá rồi mới đặt lịch. Các bước phụ thuộc nhau nhưng chuỗi xử lý vẫn tương đối ngắn. |
| **2. Tool Interaction** | 5 / 5 | Agent phải gọi `query_pet_care` để đọc hồ sơ, lịch sử và khung giờ trống, sau đó gọi `schedule_pet_care` để tạo lịch hẹn qua MCP. Chatbot chỉ sinh văn bản không thể xác nhận lịch trống hoặc lưu lịch hẹn. |
| **3. Dynamic Decision** | 4 / 5 | Agent quyết định theo kết quả công cụ: đặt khi đủ điều kiện, hỏi thêm khi thiếu thông tin hoặc đề xuất khung giờ khác khi trùng lịch, hết chỗ hay vượt ngân sách. Nếu khung giờ vừa bị đặt trước bước tạo lịch, Agent phải xử lý lỗi trả về. |
| **4. Long Horizon Goal** | 2 / 5 | Agent giữ các ràng buộc của người dùng trong chuỗi tra cứu và đặt lịch của một yêu cầu. Việc đọc lịch sử hỗ trợ lựa chọn nhưng phạm vi hiện tại chưa có lập kế hoạch dài hạn, bộ nhớ qua nhiều phiên hoặc tự theo dõi hoàn thành chăm sóc. |
| **TỔNG ĐIỂM AGENTIC FIT** | **15 / 20** | *Vượt ngưỡng 12/20: Phù hợp triển khai ReAct Agent vì cần tra cứu, quyết định theo dữ liệu và thực hiện hành động cập nhật.* |

### Kế hoạch 5 test cases

Các tình huống đã được đồng bộ vào `config/test_cases.json`. Mỗi test dùng database riêng trong bộ nhớ để kết quả không phụ thuộc lần chạy trước; TC05 có fixture chiếm khung giờ ngay trước lần đặt của Agent, được ghi rõ bằng sự kiện `TEST_SETUP`.

| Test case | Tình huống | Kết quả mong đợi |
| :--- | :--- | :--- |
| TC01 | Tra cứu lần tắm gần nhất và lịch hẹn hiện có của PET001. | Gọi công cụ tra cứu, trả lời theo dữ liệu và không tự tạo lịch hẹn. |
| TC02 | Đặt lịch tắm cho PET001 trong khoảng thời gian và ngân sách cụ thể, có đủ tên chủ nuôi. | Tra cứu trước, chọn khung giờ đáp ứng điều kiện và không trùng lịch; chỉ báo thành công khi công cụ trả về mã lịch hẹn. |
| TC03 | Yêu cầu đặt dịch vụ vào thời gian thú cưng đã có lịch hẹn. | Không tạo lịch chồng chéo; giải thích và đề xuất khung giờ khác nếu có. |
| TC04 | Yêu cầu đặt lịch chăm sóc nhưng thiếu mã thú cưng. | Hỏi bổ sung mã thú cưng, không tự đoán hồ sơ để đặt lịch. |
| TC05 | Khung giờ còn trống khi tra cứu nhưng bị đặt trước lúc tạo lịch hẹn. | Xử lý lỗi công cụ, không báo thành công; tra cứu lại để đề xuất khung giờ khác, không tự nới điều kiện của người dùng. |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ⚠️ **YÊU CẦU NGHIỆM THU:** Mở tệp `.env` điền `GEMINI_API_KEY` (hoặc `OPENAI_API_KEY`) để kết nối LLM thật trước khi thực thi `python src/app.py --all`. Bài nộp chỉ dùng Mock Offline Provider sẽ không đạt điểm nghiệm thực tế.

Dán 1 đoạn trích xuất log tiêu biểu từ file `docs/trace_waterfall.json` sinh ra từ phản hồi LLM API thật:

**Nghiệm thu bằng OpenAI `gpt-4o-mini`: 5/5 test cases đạt kiểm tra tự động; đã đọc lại các câu trả lời cuối.** Trace đầy đủ: `docs/trace_waterfall.json`; bảng kết quả: `docs/eval_live.json`. Thời điểm bắt đầu (UTC): `2026-09-13T08:22:09.746080+00:00`.

TC02 thực hiện tra cứu → đặt lịch → trả lời cuối. Đoạn dưới đây được trích trực tiếp từ sự kiện đặt lịch trong trace thật:

```json
{
  "query": "Tôi là Ngọc. Tra cứu lần tắm gần nhất của PET001 rồi đặt lịch tắm ngày 20/09/2026 sau 14:00, không quá 200.000 đồng.",
  "case_id": "TC02",
  "provider": "OpenAIProvider",
  "model": "gpt-4o-mini",
  "is_mock": false,
  "started_at": "2026-09-13T08:22:14.627236+00:00",
  "step": 2,
  "action_type": "TOOL_EXECUTION",
  "thought": "Model selected schedule_pet_care; observable action summary, not hidden reasoning.",
  "tool_name": "schedule_pet_care",
  "arguments": {
    "pet_id": "PET001",
    "slot_id": "SLOT001",
    "owner_name": "Ngọc"
  },
  "observation": {
    "status": "SUCCESS",
    "booking_id": "PC-0002",
    "pet_id": "PET001",
    "owner_name": "Ngọc",
    "slot_id": "SLOT001",
    "service_type": "bath",
    "species": "dog",
    "starts_at": "2026-09-20T14:30:00",
    "ends_at": "2026-09-20T15:30:00",
    "price_vnd": 150000,
    "message": "Đã lưu lịch chăm sóc thú cưng."
  },
  "request_id": 2,
  "executed": true,
  "llm_latency_ms": 1304.25,
  "latency_ms": 0.49
}
```

TC05 nhận `SLOT_UNAVAILABLE`, tra cứu lại và đề xuất 16:00–17:00, giá 180.000 đồng; không tạo lịch thay thế. TC04 có một đề xuất gọi công cụ với mã chưa được người dùng cung cấp, bị chặn ở Agent Core (`executed: false`, `CLARIFICATION_REQUIRED`), sau đó Agent hỏi bổ sung mã. Sự kiện bị chặn không được tính là lượt thực thi MCP.

Các trường `thought` mô tả hành động quan sát được, không phải suy luận nội bộ của mô hình. `latency_ms` đo thời gian công cụ hoặc phản hồi cuối; `llm_latency_ms` đo lượt gọi mô hình đề xuất công cụ.

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Đã cấu hình `.env` dùng OpenAI, model `gpt-4o-mini`, và chạy nghiệm thu bằng API thật.
- **Tổng số Test Cases đã chạy thành công:** **5 / 5** test cases trên OpenAI; đã kiểm tra trạng thái và đọc lại phản hồi cuối.
- **Số lượt thực thi Tool qua MCP Server:** **7 lượt**, gồm **6 SUCCESS** và **1 SLOT_UNAVAILABLE** đúng tình huống TC05. Một đề xuất thiếu mã hợp lệ bị Agent Core chặn trước MCP.
- [x] **10/10 unit tests** đạt: kiểm tra dữ liệu, trùng lịch, lưu trữ, slot bị chiếm, giới hạn vòng lặp, lỗi API và chặn mã tự đoán.
- [x] Chạy interactive bằng OpenAI: hỏi mã thú cưng còn thiếu, giữ ngữ cảnh lượt trước, đặt thành công sau khi nhận PET001. Bằng chứng: `docs/trace_interactive_live.json`.
- [x] **Đã kiểm tra tương thích Python 3.10.11** bằng môi trường riêng `.venv310`, đáp ứng yêu cầu Python 3.10–3.12 của README: **10/10 unit tests**, **5/5 offline**, **5/5 OpenAI live**; `pip check` không phát hiện xung đột phụ thuộc. Trace và kết quả lần chạy này nằm trong `docs/python310/`. Đã sửa encoding UTF-8 để lệnh kiểm tra MCP server in tiếng Việt trên Windows thành công. Chưa kiểm tra riêng Python 3.11 hoặc 3.12.
- **Hướng dẫn chạy lại:** `docs/PET_CARE_USAGE.md`. Lệnh nghiệm thu: `python src/app.py --all --require-live`.
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
