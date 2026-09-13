# Kiểm tra tương thích Python 3.10

Môi trường: `.venv310`, CPython **3.10.11**, Windows. Phiên bản này nằm trong phạm vi 3.10–3.12 mà README yêu cầu. Không thay đổi môi trường `.venv` cũ.

| Kiểm tra | Kết quả |
| :--- | :--- |
| Cài đủ `requirements.txt` | Thành công |
| `python -m pip check` | No broken requirements found |
| Unit tests | 10/10 đạt |
| Năm tình huống offline | 5/5 đạt |
| Năm tình huống OpenAI `gpt-4o-mini` | 5/5 đạt; đã đọc các câu trả lời cuối |
| MCP server độc lập | Công bố 2 tools, tra cứu PET001 thành công |

Đã sửa lỗi `UnicodeEncodeError` của lệnh MCP server độc lập bằng cách cấu hình stdout UTF-8 trên Windows. Không cần thay đổi logic nghiệp vụ để chạy trên Python 3.10.

## Bằng chứng

- `trace_waterfall.json`: trace OpenAI thật từ Python 3.10.
- `eval_live.json`: kết quả năm test live; 7 lượt thực thi MCP, một đề xuất mã chưa được cung cấp bị chặn trước MCP.
- `trace_offline.json` và `eval_offline.json`: kết quả offline.
- `requirements-tested.txt`: phiên bản các thư viện đã cài trong môi trường kiểm tra.

## Chạy lại từ thư mục gốc

```powershell
.\.venv310\Scripts\python.exe --version
.\.venv310\Scripts\python.exe -m pip check
.\.venv310\Scripts\python.exe -m unittest discover -s tests -v
.\.venv310\Scripts\python.exe src/mcp_server.py
.\.venv310\Scripts\python.exe src/app.py --all --provider mock --trace docs/python310/trace_offline.json
.\.venv310\Scripts\python.exe src/app.py --all --provider openai --require-live --trace docs/python310/trace_waterfall.json
```

Phạm vi xác minh: Python 3.10.11; chưa chạy riêng trên Python 3.11 hoặc 3.12. Kết quả live phụ thuộc mô hình và có thể thay đổi giữa các lần chạy.
