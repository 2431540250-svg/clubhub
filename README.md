# ClubHub – Ứng dụng quản lý câu lạc bộ sinh viên có AI hỗ trợ vận hành

**Nhóm 9 · WEB 6 · Môn Lập trình Python** — Flask + SQLite + Bootstrap 5, trợ lý AI (Gemini/OpenAI hoặc chạy offline).

Giao diện: chủ đề **thiên hà** cho **Học viện Hàng không Việt Nam** (nền vũ trụ, thẻ kính mờ, nhấn cyan – tím). Đổi tên trường/CLB bằng biến `SCHOOL_NAME`, `CLUB_NAME` trong `.env`; đặt logo chính thức vào `clubhub/static/img/logo.png`; đổi bảng màu ở đầu file `clubhub/static/css/app.css`.

## 1. Chạy thử trong 3 phút

```bash
# 1) Tạo môi trường ảo
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2) Cài thư viện
pip install -r requirements.txt

# 3) (Tùy chọn) cấu hình AI
copy .env.example .env         # Windows  (macOS/Linux: cp .env.example .env)
#   -> điền GEMINI_API_KEY (lấy miễn phí tại https://aistudio.google.com/apikey)

# 4) Chạy
python run.py
```

Mở http://127.0.0.1:5000. Lần chạy đầu, hệ thống **tự tạo CSDL + dữ liệu mẫu** (36 thành viên, 5 ban, 7 sự kiện, sổ quỹ 5 tháng, 30 công việc).

| Tài khoản (mật khẩu `123456`) | Vai trò |
|---|---|
| admin@club.vn | Quản trị hệ thống |
| chunhiem@club.vn | Chủ nhiệm |
| truongban@club.vn | Trưởng ban Truyền thông |
| thuquy@club.vn | Thủ quỹ |
| thanhvien@club.vn | Thành viên |

Muốn reset dữ liệu: `flask --app run seed` (xóa sạch và tạo lại dữ liệu mẫu).
Chạy kiểm thử tự động: `pytest -q` (42 test, bao phủ cả 5 task và các tiện ích sử dụng).

> **Không có API key vẫn chạy được AI**: hệ thống tự chuyển sang bộ xử lý nội bộ (mẫu soạn văn bản, tóm tắt trích xuất theo tần suất từ khóa, chấm điểm theo dữ liệu). Có key thì dùng LLM thật; nếu LLM lỗi mạng hoặc hết quota, hệ thống tự quay về bộ xử lý nội bộ.

## 2. Chức năng theo từng Task

| Task | Code chính | Chức năng | Demo |
|---|---|---|---|
| **T1** ERD, auth, khung | `models.py`, `db.py`, `auth.py`, `seed.py`, `__init__.py` | 10 bảng (Member/Department/Role/Event/Fund + Registration, Task, Announcement, Meeting, AIDraft), đăng nhập bằng email hoặc MSSV, mật khẩu băm, dữ liệu mẫu | Trang **Sơ đồ ERD** (`/erd`, đăng nhập admin) và **Tổng quan** |
| **T2** Hồ sơ, ban, phân quyền | `blueprints/members.py`, `auth.py` | CRUD hồ sơ, gán ban/vai trò, RBAC 5 vai trò × 13 quyền, trưởng ban chỉ thấy ban mình, import/export CSV | Đăng nhập lần lượt 5 tài khoản để thấy **menu khác nhau**; trang `/permissions` |
| **T3** Sự kiện & QR | `blueprints/events.py` | Tạo sự kiện, lịch tháng, đăng ký, **vé QR cá nhân**, **máy quét QR bằng camera**, QR sự kiện để tự check-in, nhập tay MSSV, thống kê, xuất CSV | Đăng ký bằng tài khoản thành viên → mở vé QR → dùng tài khoản khác mở **Quét QR** |
| **T4** Quỹ, việc, thông báo, báo cáo | `blueprints/finance.py`, `tasks.py`, `announcements.py`, `reports.py` | Sổ thu chi (biểu đồ), Kanban kéo thả, thông báo theo ban, báo cáo tháng **xuất Excel và PDF** (hỗ trợ tiếng Việt) | **Báo cáo** → Xuất PDF/Excel |
| **T5** AI & deploy | `ai_service.py`, `blueprints/ai.py`, `Procfile`, `render.yaml` | Soạn nháp thông báo, tóm tắt biên bản, đề xuất phân công, phát hiện thành viên ít tương tác, soạn tin hỏi thăm; quy trình **AI nháp → người duyệt → công bố** | **Trợ lý AI** → "Dùng biên bản mẫu" → Tóm tắt → Duyệt |

### Tiện ích sử dụng (bản cập nhật)
- **Đổi trạng thái việc bằng nút** ngay trên thẻ (Bắt đầu / Xong / Tạm dừng / Mở lại), dùng tốt trên điện thoại; máy tính vẫn kéo thả được. Trang Tổng quan có nút "Xong" nhanh.
- **Báo lỗi ngay tại ô nhập**: ô sai được tô đỏ kèm lời nhắc, dữ liệu đã nhập được giữ lại. Thông báo lỗi không tự biến mất.
- **Quên mật khẩu**: có cấu hình email (`MAIL_*` trong `.env`) thì gửi link qua email. Chưa cấu hình thì yêu cầu chuyển tới Ban Chủ nhiệm (*Thành viên → Xử lý*), BCN bấm "Tạo link" rồi gửi qua Zalo. Link dùng 1 lần, chỉ lưu bản băm.
- **Thông báo chưa đọc**: chuông ở thanh trên và huy hiệu ở menu, tin mới gắn nhãn "MỚI".
- **Tìm kiếm** sự kiện (theo tên, ban, "tôi đã đăng ký") và công việc (theo từ khóa, "chỉ việc quá hạn"); danh sách thành viên **phân trang** 20 người/trang.
- **Tự check-in theo giờ**: QR sự kiện tự mở 30 phút trước giờ bắt đầu, đóng khi kết thúc. BTC vẫn có thể chọn "Mở ngay" hoặc "Đóng".
- **Camera không chạy** (khi mở qua IP, không có HTTPS): trang quét hiện hướng dẫn, gồm nhập mã/MSSV hoặc quét từ ảnh. Muốn có HTTPS trong mạng LAN: `pip install pyopenssl`, đặt biến `HTTPS=1` rồi `python run.py`.
- **Bảng trên điện thoại** tự chuyển thành dạng thẻ, có nhãn từng cột, không cần vuốt ngang.

## 3. Cấu trúc thư mục

```
clubhub/
├── run.py                  # điểm chạy app (gunicorn dùng run:app)
├── requirements.txt  .env.example  Procfile  render.yaml
├── clubhub/
│   ├── __init__.py         # create_app: đăng ký blueprint, filter, error handler
│   ├── config.py           # đọc cấu hình từ .env
│   ├── db.py               # kết nối SQLite, hàm query/execute, lệnh CLI init-db/seed
│   ├── models.py           # SCHEMA (ERD) + hằng số danh mục
│   ├── auth.py             # đăng nhập, decorator, MA TRẬN QUYỀN
│   ├── seed.py             # dữ liệu mẫu
│   ├── ai_service.py       # toàn bộ logic AI (LLM + bộ xử lý nội bộ)
│   ├── passwords.py        # quên/đặt lại mật khẩu
│   ├── ui.py               # báo lỗi theo ô nhập, phân trang
│   ├── reports.py          # tổng hợp báo cáo, xuất Excel/PDF
│   ├── blueprints/         # main, members, events, finance, tasks, announcements, reports, ai
│   ├── templates/          # giao diện Jinja2 + Bootstrap 5
│   └── static/             # css, js, font DejaVu cho PDF tiếng Việt
├── tests/test_app.py       # 42 test tự động
└── docs/
    ├── diagrams.md         # mã Mermaid 5 sơ đồ cho slide
    └── img/                # 5 sơ đồ đã xuất sẵn PNG
```

## 4. Deploy (có HTTPS, để quét QR bằng camera điện thoại)

**Render.com (miễn phí):** đưa code lên GitHub → Render → *New → Blueprint* → chọn repo (dùng sẵn `render.yaml`) → thêm biến `GEMINI_API_KEY` → Deploy.
Lưu ý: bản miễn phí của Render xóa ổ đĩa mỗi lần khởi động lại, nên dữ liệu sẽ quay về bộ mẫu (phù hợp để demo). Muốn giữ dữ liệu lâu dài thì gắn *Persistent Disk* và đặt `DATABASE_PATH=/var/data/clubhub.db`.

**PythonAnywhere (giữ dữ liệu, miễn phí):** upload code → `pip install --user -r requirements.txt` → Web tab → *Manual config* → trong file WSGI: `from run import app as application` → đặt biến môi trường trong `.env`.

> Camera trình duyệt chỉ chạy trên `localhost` hoặc `https://`. Khi demo trên laptop thì cứ mở trang Quét QR ở `localhost`. Với cách tự check-in, điện thoại quét QR sự kiện bằng app camera thường nên không cần HTTPS, nhưng điện thoại phải truy cập được địa chỉ của server (cùng mạng Wi-Fi và chạy `python run.py`, hoặc dùng bản đã deploy).

## 5. Gợi ý chia việc 5 thành viên

| Thành viên | Phụ trách code | Slide/sơ đồ |
|---|---|---|
| TV1 | `models.py`, `db.py`, `auth.py` (đăng nhập), `seed.py`, dashboard | T1 – ERD |
| TV2 | `members.py`, RBAC trong `auth.py`, import CSV | T2 – sơ đồ thành viên–ban–vai trò, ma trận quyền |
| TV3 | `events.py`, `scan.html` (QR) | T3 – lưu đồ check-in QR |
| TV4 | `finance.py`, `tasks.py`, `announcements.py`, `reports.py` | T4 – luồng thu chi & giao việc |
| TV5 | `ai_service.py`, `blueprints/ai.py`, deploy | T5 – lưu đồ AI nháp rồi duyệt |

## 6. Kịch bản demo (khoảng 10 phút)

1. **T1**: đăng nhập `admin` → *Sơ đồ ERD* → *Tổng quan* (thẻ số liệu, biểu đồ điểm danh, thu chi).
2. **T2**: mở *Phân quyền* → đăng xuất, lần lượt đăng nhập `thanhvien` / `thuquy` / `truongban` để so sánh menu. Trưởng ban vào *Thành viên* chỉ thấy ban mình. Đăng nhập `chunhiem` → *Import CSV* → tải file mẫu → import.
3. **T3**: `thanhvien` mở sự kiện "Workshop AI & LLM ứng dụng" → *Đăng ký* → hiện vé QR. Mở thêm 1 cửa sổ ẩn danh, đăng nhập `truongban` → *Mở máy quét vé QR* → đưa vé (trên điện thoại hoặc màn hình) vào camera → hiện "Điểm danh thành công". Xem *Thống kê*.
4. **T4**: `thuquy` → *Sổ thu chi* → ghi 1 khoản chi → *Báo cáo* → Xuất PDF và Excel. `truongban` → *Công việc* → kéo thả thẻ trên Kanban.
5. **T5**: `chunhiem` → *Trợ lý AI* → "Dùng biên bản mẫu" → *Tóm tắt* → sửa → *Duyệt & lưu biên bản*. Soạn nháp thông báo → duyệt → thông báo xuất hiện, gắn nhãn AI. Mở *Đề xuất phân công* và *Mức độ tương tác* → bấm *Soạn tin*.

## 7. Câu hỏi thường gặp khi bảo vệ

- **Vì sao dùng `sqlite3` thuần thay vì ORM?** Để thể hiện rõ SQL và quan hệ trong ERD, ít phụ thuộc thư viện, dễ giải thích. Mọi truy vấn đều dùng tham số `?` nên chống được SQL injection.
- **Bảo mật mật khẩu?** Mật khẩu được băm bằng `werkzeug.security.generate_password_hash` (scrypt), không lưu dạng gốc.
- **Phân quyền ở đâu?** Có 2 lớp: giao diện ẩn/hiện menu qua `can()`, và server chặn bằng `@permission_required` (trả 403). Ngoài ra còn giới hạn theo ban với trưởng ban.
- **AI có "bịa" nội dung không?** Prompt yêu cầu chỉ dùng thông tin được cung cấp, và mọi đầu ra đều là bản nháp phải qua người duyệt. Đề xuất phân công và mức độ tương tác được tính bằng công thức minh bạch từ dữ liệu thật (ghi rõ trên giao diện); LLM chỉ giải thích thêm.
