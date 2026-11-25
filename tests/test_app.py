"""Kiểm thử tự động: chạy `pytest -q` ở thư mục gốc dự án."""
import io
import re

import pytest

from clubhub import create_app
from clubhub.db import init_db, query
from clubhub.seed import seed

ACCOUNTS = {
    "admin": "admin@club.vn", "president": "chunhiem@club.vn", "head": "truongban@club.vn",
    "treasurer": "thuquy@club.vn", "member": "thanhvien@club.vn",
}


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "test",
                      "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""})
    with app.app_context():
        init_db()
        seed()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, role):
    return client.post("/login", data={"login": ACCOUNTS[role], "password": "123456"}, follow_redirects=True)


# ---------------------------------------------------------------- Task 1
def test_login_logout(client):
    assert client.get("/dashboard").status_code == 302
    r = login(client, "admin")
    assert "Tổng quan" in r.get_data(as_text=True)
    r = client.post("/login", data={"login": "admin@club.vn", "password": "sai"}, follow_redirects=True)
    client.get("/logout")
    r = client.post("/login", data={"login": "admin@club.vn", "password": "sai"}, follow_redirects=True)
    assert "Sai email" in r.get_data(as_text=True)


def test_login_by_student_id(client):
    r = client.post("/login", data={"login": "sv004", "password": "123456"}, follow_redirects=True)
    assert "Phạm Gia Thành" in r.get_data(as_text=True)


ALL_PAGES = ["/dashboard", "/profile", "/permissions", "/erd", "/events", "/events/stats", "/events/1",
             "/events/calendar.json", "/tasks/", "/tasks/?scope=mine", "/announcements/", "/members", "/members/2",
             "/departments", "/members/new", "/members/2/edit", "/members/import", "/members/export.csv",
             "/members/import/template.csv", "/events/new", "/events/1/edit", "/events/1/scan",
             "/events/1/attendance.csv", "/finance/", "/finance/new", "/finance/1/edit", "/finance/export.csv",
             "/finance/?month=&type=expense", "/tasks/new", "/tasks/1/edit", "/announcements/new",
             "/announcements/1/edit", "/reports/", "/reports/export.xlsx", "/reports/export.pdf", "/ai/",
             "/ai/assign", "/ai/engagement", "/ai/engagement?show=all&days=30", "/ai/meetings/1"]


@pytest.mark.parametrize("role", list(ACCOUNTS))
def test_every_page_no_server_error(client, role):
    login(client, role)
    for url in ALL_PAGES:
        r = client.get(url)
        assert r.status_code in (200, 302, 403), f"{role} {url} -> {r.status_code}"


def test_admin_can_open_everything(client):
    login(client, "admin")
    for url in ALL_PAGES:
        assert client.get(url).status_code == 200, url


# ---------------------------------------------------------------- Task 2: RBAC
def test_menu_differs_by_role(client):
    login(client, "member")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Sổ thu chi" not in html and "Thành viên</a>" not in html and "Trợ lý AI" not in html
    client.get("/logout")
    login(client, "treasurer")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Sổ thu chi" in html and "Trợ lý AI" not in html
    client.get("/logout")
    login(client, "president")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Sổ thu chi" in html and "Trợ lý AI" in html


@pytest.mark.parametrize("role,url,code", [
    ("member", "/members", 403), ("member", "/finance/", 403), ("member", "/reports/", 403), ("member", "/ai/", 403),
    ("treasurer", "/members/new", 403), ("treasurer", "/finance/new", 200), ("head", "/finance/", 403),
    ("head", "/members/import", 403), ("president", "/finance/new", 403), ("president", "/reports/", 200),
])
def test_permissions(client, role, url, code):
    login(client, role)
    assert client.get(url).status_code == code


def test_head_sees_only_own_department(client, app):
    login(client, "head")
    html = client.get("/members").get_data(as_text=True)
    with app.app_context():
        other = query("SELECT m.id, m.full_name FROM members m WHERE department_id != 2 AND department_id IS NOT NULL LIMIT 1",
                      one=True)
    assert other["full_name"] not in html
    assert client.get(f"/members/{other['id']}").status_code == 403


def test_member_crud(client, app):
    login(client, "president")
    r = client.post("/members/new", data={"student_id": "SV999", "full_name": "Test User", "email": "t@club.vn",
                                          "role_id": "5", "department_id": "1"}, follow_redirects=True)
    assert "Đã thêm" in r.get_data(as_text=True)
    with app.app_context():
        mid = query("SELECT id FROM members WHERE student_id='SV999'", one=True)["id"]
    # trùng email
    r = client.post("/members/new", data={"student_id": "SV998", "full_name": "X", "email": "t@club.vn", "role_id": "5"},
                    follow_redirects=True)
    assert "đã được dùng" in r.get_data(as_text=True)
    # chủ nhiệm không được cấp quyền admin
    r = client.post(f"/members/{mid}/edit", data={"student_id": "SV999", "full_name": "Test", "email": "t@club.vn",
                                                  "role_id": "1", "is_active": "on"}, follow_redirects=True)
    assert "Chỉ quản trị" in r.get_data(as_text=True)
    r = client.post(f"/members/{mid}/edit", data={"student_id": "SV999", "full_name": "Test Đổi Tên", "email": "t@club.vn",
                                                  "role_id": "3", "department_id": "2", "is_active": "on"},
                    follow_redirects=True)
    assert "Test Đổi Tên" in r.get_data(as_text=True)
    client.post(f"/members/{mid}/delete")
    with app.app_context():
        assert query("SELECT id FROM members WHERE id=?", (mid,), one=True) is None
    # người mới đăng nhập bằng MSSV làm mật khẩu – đã xóa nên không đăng nhập được
    client.get("/logout")
    r = client.post("/login", data={"login": "SV999", "password": "SV999"}, follow_redirects=True)
    assert "Sai email" in r.get_data(as_text=True)


def test_import_csv(client, app):
    login(client, "admin")
    csv_text = ("student_id,full_name,email,phone,faculty,class_name,department,role\n"
                "SV500,Nguyễn Văn A,a500@club.vn,0911,CNTT,K68,Ban Sự kiện,member\n"
                "SV501,Trần Thị B,b501@club.vn,0922,CNTT,K68,Ban Mới Toanh,Trưởng ban\n"
                "SV502,,bad,,,,,\n"
                "SV503,Lê C,a500@club.vn,,,,,\n")
    r = client.post("/members/import", data={"file": (io.BytesIO(("﻿" + csv_text).encode()), "ds.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Thêm mới: <strong>2</strong>" in html and "Lỗi: <strong>2</strong>" in html
    with app.app_context():
        b = query("SELECT m.*, r.code, d.name AS dn FROM members m JOIN roles r ON r.id=m.role_id "
                  "JOIN departments d ON d.id=m.department_id WHERE student_id='SV501'", one=True)
        assert b["code"] == "head" and b["dn"] == "Ban Mới Toanh"
    client.get("/logout")
    r = client.post("/login", data={"login": "SV500", "password": "SV500"}, follow_redirects=True)
    assert "Nguyễn Văn A" in r.get_data(as_text=True)


def test_department_crud(client, app):
    login(client, "president")
    client.post("/departments", data={"name": "Ban Kỹ thuật", "description": "abc"})
    with app.app_context():
        d = query("SELECT id FROM departments WHERE name='Ban Kỹ thuật'", one=True)
    assert d
    client.post(f"/departments/{d['id']}/delete")
    with app.app_context():
        assert query("SELECT id FROM departments WHERE name='Ban Kỹ thuật'", one=True) is None


# ---------------------------------------------------------------- Task 3: sự kiện & QR
def test_event_register_and_checkin_flow(client, app):
    login(client, "head")
    r = client.post("/events/new", data={"title": "Sự kiện test", "start_time": "2030-01-01T18:00",
                                         "end_time": "2030-01-01T20:00", "capacity": "2", "location": "A1"},
                    follow_redirects=True)
    assert "Đã tạo sự kiện" in r.get_data(as_text=True)
    with app.app_context():
        eid = query("SELECT id, department_id FROM events WHERE title='Sự kiện test'", one=True)
    assert eid["department_id"] == 2  # trưởng ban -> ban của mình
    eid = eid["id"]
    client.get("/logout")

    login(client, "member")
    r = client.post(f"/events/{eid}/register", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Vé QR của tôi" in html
    ticket = re.search(r'font-monospace">([0-9A-F]{12})<', html).group(1)
    assert client.get(f"/events/{eid}/scan").status_code == 403  # thành viên không được quét
    client.get("/logout")

    login(client, "treasurer")  # thủ quỹ có quyền hỗ trợ check-in
    r = client.post(f"/events/{eid}/checkin", json={"code": "CLUBHUB:" + ticket})
    assert r.get_json()["status"] == "ok" and r.get_json()["attended"] == 1
    r = client.post(f"/events/{eid}/checkin", json={"code": ticket})
    assert r.get_json()["status"] == "already"
    r = client.post(f"/events/{eid}/checkin", json={"code": "KHONGTONTAI"})
    assert r.status_code == 404
    r = client.post(f"/events/{eid}/checkin", json={"code": "SV010"})  # nhập tay MSSV (khách vãng lai)
    assert r.get_json()["status"] == "ok"
    csv_data = client.get(f"/events/{eid}/attendance.csv").get_data(as_text=True)
    assert "SV004" in csv_data and "SV010" in csv_data


def test_capacity_and_self_checkin(client, app):
    with app.app_context():
        e = query("SELECT * FROM events WHERE checkin_open=1", one=True)
    login(client, "member")
    r = client.get(f"/checkin/{e['checkin_token']}")
    assert "Điểm danh thành công" in r.get_data(as_text=True) or "Đã điểm danh" in r.get_data(as_text=True)
    r = client.get(f"/checkin/{e['checkin_token']}")
    assert "Đã điểm danh" in r.get_data(as_text=True)
    with app.app_context():
        closed = query("SELECT * FROM events WHERE checkin_open=0", one=True)
    r = client.get(f"/checkin/{closed['checkin_token']}")
    assert "chưa mở check-in" in r.get_data(as_text=True)
    # ticket of other event rejected
    client.get("/logout")
    login(client, "admin")
    with app.app_context():
        reg = query("SELECT ticket_code, event_id FROM registrations WHERE event_id != ? LIMIT 1", (e["id"],), one=True)
    r = client.post(f"/events/{e['id']}/checkin", json={"code": reg["ticket_code"]})
    assert r.status_code == 400


def test_self_checkin_requires_login(client, app):
    with app.app_context():
        e = query("SELECT * FROM events LIMIT 1", one=True)
    r = client.get(f"/checkin/{e['checkin_token']}")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ---------------------------------------------------------------- Task 4
def test_finance_and_report(client, app):
    login(client, "treasurer")
    r = client.post("/finance/new", data={"type": "income", "amount": "1000000", "category": "Tài trợ",
                                          "txn_date": "2026-11-20", "description": "Test thu"}, follow_redirects=True)
    assert "Đã lưu" in r.get_data(as_text=True)
    r = client.post("/finance/new", data={"type": "expense", "amount": "-5", "category": "Khác"}, follow_redirects=True)
    assert "Số tiền phải lớn hơn 0" in r.get_data(as_text=True) and "is-invalid" in r.get_data(as_text=True)
    r = client.get("/reports/export.xlsx?month=2026-11")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    r = client.get("/reports/export.pdf?month=2026-11")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert client.get("/reports/?month=2026-13").status_code == 400


def test_task_flow(client, app):
    login(client, "head")
    with app.app_context():
        other_dept = query("SELECT id FROM members WHERE department_id=1 LIMIT 1", one=True)["id"]
        own = query("SELECT id FROM members WHERE department_id=2 AND id NOT IN (3, 5) LIMIT 1", one=True)["id"]
    r = client.post("/tasks/new", data={"title": "Giao sai ban", "assignee_id": other_dept}, follow_redirects=True)
    assert "trong ban của mình" in r.get_data(as_text=True)
    r = client.post("/tasks/new", data={"title": "Việc test", "assignee_id": own, "priority": "high",
                                        "deadline": "2030-01-01"}, follow_redirects=True)
    assert "Đã giao việc" in r.get_data(as_text=True)
    with app.app_context():
        tid = query("SELECT id FROM tasks WHERE title='Việc test'", one=True)["id"]
    assert client.post(f"/tasks/{tid}/status", json={"status": "done"}).get_json() == {"ok": True}
    with app.app_context():
        t = query("SELECT status, completed_at FROM tasks WHERE id=?", (tid,), one=True)
        assert t["status"] == "done" and t["completed_at"]
    client.get("/logout")
    login(client, "member")  # thành viên khác không được đổi việc người khác
    assert client.post(f"/tasks/{tid}/status", json={"status": "todo"}).status_code == 403


def test_announcement(client):
    login(client, "president")
    r = client.post("/announcements/new", data={"title": "TB test", "content": "Nội dung"}, follow_redirects=True)
    assert "TB test" in r.get_data(as_text=True)


# ---------------------------------------------------------------- Task 5: AI
def test_ai_announcement_draft_approve(client, app):
    login(client, "head")
    r = client.post("/ai/announcement", data={"topic": "Workshop Docker", "details": "18h thứ 6\nPhòng A2",
                                              "tone": "exciting"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Workshop Docker" in html and "Chỉ Chủ nhiệm" in html
    with app.app_context():
        did = query("SELECT id FROM ai_drafts ORDER BY id DESC LIMIT 1", one=True)["id"]
    assert client.post(f"/ai/drafts/{did}", data={"action": "approve", "output_text": "x"}).status_code == 403
    client.get("/logout")
    login(client, "president")
    r = client.post(f"/ai/drafts/{did}", data={"action": "approve", "title": "Workshop Docker",
                                               "output_text": "[Thông báo] Workshop Docker\nNội dung đã sửa"},
                    follow_redirects=True)
    assert "Nội dung đã sửa" in r.get_data(as_text=True)
    with app.app_context():
        a = query("SELECT * FROM announcements WHERE is_ai_generated=1", one=True)
        assert a["title"] == "[Thông báo] Workshop Docker"


def test_ai_minutes(client, app):
    login(client, "president")
    notes = ("Họp BCH về ngày hội tuyển thành viên. Cả nhóm thống nhất tổ chức vào 05/12. "
             "Ban Truyền thông phụ trách poster, hạn chót 28/11. Vấn đề: thiếu người trực buổi chiều.")
    r = client.post("/ai/minutes", data={"title": "Họp test", "notes": notes}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "QUYẾT ĐỊNH" in html and "thống nhất" in html and "VIỆC CẦN LÀM" in html
    with app.app_context():
        did = query("SELECT id FROM ai_drafts ORDER BY id DESC LIMIT 1", one=True)["id"]
    r = client.post(f"/ai/drafts/{did}", data={"action": "approve", "title": "Họp test",
                                               "output_text": "tóm tắt", "meeting_date": "2026-11-25"},
                    follow_redirects=True)
    assert "Họp test" in r.get_data(as_text=True)


def test_ai_assign_and_engagement(client, app):
    login(client, "president")
    r = client.post("/ai/assign", data={"title": "Thiết kế poster sự kiện", "department_id": "2"})
    html = r.get_data(as_text=True)
    assert "Đề xuất giao cho" in html and "Giao việc" in html
    r = client.get("/ai/engagement")
    html = r.get_data(as_text=True)
    assert "Ít tương tác" in html
    with app.app_context():
        from clubhub.ai_service import engagement_report
        rows = engagement_report()
        assert any(x["level"] == "low" for x in rows)
    r = client.post("/ai/engagement/10/message", json={"reasons": ["vắng 3/5 sự kiện"]})
    assert r.get_json()["text"]


def test_llm_failure_falls_back_to_local(app):
    """Có key nhưng không gọi được mạng -> vẫn trả kết quả nội bộ."""
    app.config.update(GEMINI_API_KEY="fake-key", AI_TIMEOUT=2)
    with app.test_request_context():
        from clubhub import ai_service
        import requests

        def boom(*a, **k):
            raise requests.ConnectionError("offline")
        orig = requests.post
        requests.post = boom
        try:
            text, provider = ai_service.draft_announcement("Test", "chi tiết")
        finally:
            requests.post = orig
        assert "Test" in text and provider.startswith("local")


# ================================================================ Cải thiện trải nghiệm
def test_task_status_buttons_for_assignee(client, app):
    """(1) Thành viên đổi trạng thái việc của mình bằng nút (không cần kéo thả)."""
    with app.app_context():
        t = query("SELECT id FROM tasks WHERE assignee_id=5 AND status!='done' LIMIT 1", one=True)
        if t is None:
            from clubhub.db import execute
            tid = execute("INSERT INTO tasks(title, assignee_id, status) VALUES ('Việc nút', 5, 'todo')")
        else:
            tid = t["id"]
    login(client, "member")
    html = client.get("/tasks/").get_data(as_text=True)
    assert f'/tasks/{tid}/status' in html and "Bắt đầu" in html
    r = client.post(f"/tasks/{tid}/status", data={"status": "doing", "next": "/tasks/"}, follow_redirects=True)
    assert "Đang làm" in r.get_data(as_text=True)
    r = client.post(f"/tasks/{tid}/status", data={"status": "done", "next": "/dashboard"})
    assert r.headers["Location"].endswith("/dashboard")
    r = client.post(f"/tasks/{tid}/status", data={"status": "done", "next": "//evil.com"})
    assert "evil" not in r.headers["Location"]


def test_field_errors_highlighted(client):
    """(2) Lỗi hiện ngay dưới ô nhập và form giữ lại dữ liệu đã nhập."""
    login(client, "president")
    r = client.post("/members/new", data={"student_id": "", "full_name": "Giữ Lại Tên", "email": "sai", "role_id": "5"})
    html = r.get_data(as_text=True)
    assert html.count("is-invalid") >= 2 and "Nhập MSSV." in html and "Email không hợp lệ" in html
    assert 'value="Giữ Lại Tên"' in html
    r = client.post("/events/new", data={"title": "", "start_time": "2030-01-01T20:00", "end_time": "2030-01-01T18:00"})
    html = r.get_data(as_text=True)
    assert "Nhập tên sự kiện." in html and "phải sau thời gian bắt đầu" in html
    r = client.post("/announcements/new", data={"title": "Có tiêu đề", "content": ""})
    assert "Nhập nội dung thông báo." in r.get_data(as_text=True)
    r = client.post("/profile", data={"action": "password", "old": "sai", "new": "123", "confirm": "123"})
    html = r.get_data(as_text=True)
    assert "Mật khẩu cũ không đúng." in html and "tối thiểu 6 ký tự" in html


def test_forgot_password_admin_link_flow(client, app):
    """(3) Quên mật khẩu khi chưa cấu hình email: BCN tạo link, thành viên tự đặt lại."""
    r = client.get("/login")
    assert "Quên mật khẩu?" in r.get_data(as_text=True)
    r = client.post("/forgot-password", data={"login": "SV004"})
    assert "Ban Chủ nhiệm" in r.get_data(as_text=True)
    r2 = client.post("/forgot-password", data={"login": "khongtontai@x.vn"})  # cùng thông báo, không lộ tài khoản
    assert "Đã ghi nhận yêu cầu" in r2.get_data(as_text=True)
    login(client, "president")
    html = client.get("/members").get_data(as_text=True)
    assert "yêu cầu đặt lại mật khẩu" in html
    html = client.get("/members/password-requests").get_data(as_text=True)
    assert "Phạm Gia Thành" in html
    r = client.post("/members/5/reset-link")
    link = re.search(r'id="resetLink"[^>]*value="([^"]+)"', r.get_data(as_text=True)).group(1)
    path = link.replace("http://localhost", "")
    client.get("/logout")
    r = client.post(path, data={"new": "abc", "confirm": "abc"})
    assert "tối thiểu 6 ký tự" in r.get_data(as_text=True)
    r = client.post(path, data={"new": "matkhaumoi", "confirm": "matkhaumoi"}, follow_redirects=True)
    assert "Đã đặt mật khẩu mới" in r.get_data(as_text=True)
    assert client.get(path).status_code == 400  # link dùng 1 lần
    r = client.post("/login", data={"login": "thanhvien@club.vn", "password": "matkhaumoi"}, follow_redirects=True)
    assert "Phạm Gia Thành" in r.get_data(as_text=True)
    with app.app_context():
        assert all(len(x["token_hash"]) == 64 for x in query("SELECT token_hash FROM password_resets"))


def test_forgot_password_email(client, app, monkeypatch):
    """(3) Có cấu hình email -> gửi link qua email."""
    sent = {}
    import clubhub.passwords as pw
    monkeypatch.setattr(pw, "send_reset_email", lambda m, link: sent.update(to=m["email"], link=link))
    app.config["MAIL_SERVER"] = "smtp.example.com"
    r = client.post("/forgot-password", data={"login": "thanhvien@club.vn"})
    assert "email" in r.get_data(as_text=True) and sent["to"] == "thanhvien@club.vn"
    assert client.get(sent["link"].replace("http://localhost", "")).status_code == 200


def test_unread_announcements(client):
    """(4) Huy hiệu thông báo chưa đọc, xem xong thì về 0."""
    login(client, "member")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "unread-badge" in html
    html = client.get("/announcements/").get_data(as_text=True)
    assert "MỚI" in html
    html = client.get("/dashboard").get_data(as_text=True)
    assert "unread-badge" not in html
    client.get("/logout")
    login(client, "president")
    client.post("/announcements/new", data={"title": "Tin nóng", "content": "abc"})
    client.get("/logout")
    login(client, "member")
    assert 'title="1 thông báo chưa đọc"' in client.get("/dashboard").get_data(as_text=True)


def test_search_and_pagination(client):
    """(5) Tìm kiếm sự kiện, công việc; phân trang thành viên."""
    login(client, "admin")
    html = client.get("/events?q=Hackathon").get_data(as_text=True)
    assert "Hackathon mini 24h" in html and "Talkshow" not in html
    assert "Không tìm thấy" in client.get("/events?q=zzzz").get_data(as_text=True)
    html = client.get("/tasks/?q=poster").get_data(as_text=True)
    assert "Thiết kế poster" in html and "Kiểm kê thiết bị" not in html
    html = client.get("/members").get_data(as_text=True)
    assert "pagination" in html and "Hiển thị 1–20 / 36" in html
    html = client.get("/members?page=2").get_data(as_text=True)
    assert "Hiển thị 21–36 / 36" in html
    assert "Hiển thị 21–36" in client.get("/members?page=99").get_data(as_text=True)


def test_checkin_auto_window(client, app):
    """(6) Tự check-in tự mở 30 phút trước giờ bắt đầu, không cần BTC nhớ bấm."""
    from datetime import datetime, timedelta
    from clubhub.blueprints.events import checkin_state
    now = datetime(2030, 1, 1, 17, 45)
    e = {"checkin_open": 0, "start_time": "2030-01-01 18:00", "end_time": "2030-01-01 20:00"}
    assert checkin_state(e, now)[0] is True
    assert checkin_state(e, now - timedelta(minutes=30))[0] is False
    assert checkin_state(e, datetime(2030, 1, 1, 20, 30))[0] is False
    assert checkin_state({**e, "checkin_open": 2}, now)[0] is False
    assert checkin_state({**e, "checkin_open": 1}, now - timedelta(days=3))[0] is True
    # sự kiện đang diễn ra -> thành viên tự check-in được dù BTC chưa bấm gì
    login(client, "head")
    s = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
    en = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/events/new", data={"title": "Đang diễn ra", "start_time": s, "end_time": en})
    with app.app_context():
        ev = query("SELECT * FROM events WHERE title='Đang diễn ra'", one=True)
    html = client.get(f"/events/{ev['id']}").get_data(as_text=True)
    assert "Đang mở tự động" in html
    client.post(f"/events/{ev['id']}/checkin-mode", data={"mode": "2"})
    assert "đóng thủ công" in client.get(f"/events/{ev['id']}").get_data(as_text=True)
    client.post(f"/events/{ev['id']}/checkin-mode", data={"mode": "0"})
    client.get("/logout")
    login(client, "member")
    assert "Điểm danh thành công" in client.get(f"/checkin/{ev['checkin_token']}").get_data(as_text=True)


def test_scan_page_has_insecure_warning_and_stack_tables(client):
    """(6)(7) Cảnh báo camera khi không HTTPS; bảng có class responsive."""
    login(client, "admin")
    assert "insecureWarn" in client.get("/events/1/scan").get_data(as_text=True)
    for url in ["/members", "/finance/", "/events/1", "/ai/engagement"]:
        assert "table-stack" in client.get(url).get_data(as_text=True), url


def test_migrate_old_database(tmp_path):
    """CSDL tạo từ bản cũ (thiếu cột/bảng mới) được nâng cấp tự động, không mất dữ liệu."""
    import sqlite3
    from clubhub.db import migrate_db
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "old.db")})
    with app.app_context():
        init_db(); seed()
        from clubhub.db import get_db
        db = get_db()
        db.execute("DROP TABLE password_resets")
        db.execute("ALTER TABLE members DROP COLUMN announcements_seen_id")
        db.commit()
        migrate_db()
        cols = {r["name"] for r in db.execute("PRAGMA table_info(members)")}
        assert "announcements_seen_id" in cols
        assert db.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 36
