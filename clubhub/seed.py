"""Sinh dữ liệu mẫu để demo. Mọi tài khoản mật khẩu: 123456"""
import random
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from .db import execute, get_db, query

ROLES = [
    ("admin", "Quản trị hệ thống", "Toàn quyền hệ thống"),
    ("president", "Chủ nhiệm", "Điều hành CLB, duyệt nội dung AI"),
    ("head", "Trưởng ban", "Quản lý ban, giao việc, tổ chức sự kiện"),
    ("treasurer", "Thủ quỹ", "Quản lý sổ thu chi"),
    ("member", "Thành viên", "Tham gia hoạt động"),
]

DEPARTMENTS = [
    ("Ban Chuyên môn", "Tổ chức workshop, mentor lập trình Python"),
    ("Ban Truyền thông", "Fanpage, thiết kế ấn phẩm, viết bài"),
    ("Ban Sự kiện", "Lên kế hoạch và vận hành sự kiện"),
    ("Ban Đối ngoại", "Tìm tài trợ, liên kết doanh nghiệp"),
    ("Ban Hậu cần", "Cơ sở vật chất, thiết bị, check-in"),
]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
DEM = ["Văn", "Thị", "Minh", "Ngọc", "Gia", "Thanh", "Quốc", "Hoài", "Đức", "Bảo", "Khánh", "Anh"]
TEN = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hải", "Hùng", "Khoa", "Linh", "Long", "Mai",
       "Nam", "Nhi", "Phúc", "Quân", "Quỳnh", "Sơn", "Tâm", "Thảo", "Trang", "Tú", "Uyên", "Vy", "Yến"]
FACULTIES = ["CNTT", "Khoa học dữ liệu", "Điện tử viễn thông", "Kinh tế", "Toán - Tin"]


def _fmt(d):
    return d.strftime("%Y-%m-%d %H:%M")


def seed():
    rnd = random.Random(2026)
    db = get_db()
    pw = generate_password_hash("123456")
    now = datetime.now().replace(second=0, microsecond=0)

    for code, name, desc in ROLES:
        execute("INSERT INTO roles(code,name,description) VALUES (?,?,?)", (code, name, desc), commit=False)
    role = {r["code"]: r["id"] for r in query("SELECT id, code FROM roles")}

    for name, desc in DEPARTMENTS:
        execute("INSERT INTO departments(name,description) VALUES (?,?)", (name, desc), commit=False)
    dept_ids = [r["id"] for r in query("SELECT id FROM departments ORDER BY id")]

    # ---- Tài khoản demo cố định ----
    fixed = [
        ("ADMIN01", "Quản Trị Viên", "admin@club.vn", "admin", None),
        ("SV001", "Nguyễn Minh Chủ", "chunhiem@club.vn", "president", dept_ids[0]),
        ("SV002", "Trần Thu Truyền", "truongban@club.vn", "head", dept_ids[1]),
        ("SV003", "Lê Ngọc Quỹ", "thuquy@club.vn", "treasurer", dept_ids[4]),
        ("SV004", "Phạm Gia Thành", "thanhvien@club.vn", "member", dept_ids[1]),
    ]
    for sid, name, email, rc, dep in fixed:
        execute("""INSERT INTO members(student_id,full_name,email,phone,faculty,class_name,password_hash,
                   role_id,department_id,joined_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (sid, name, email, "09" + str(rnd.randint(10000000, 99999999)), "CNTT", "K66-CNTT1",
                 pw, role[rc], dep, (now - timedelta(days=300)).strftime("%Y-%m-%d")), commit=False)

    # trưởng ban cho các ban còn lại
    for i, dep in enumerate(dept_ids[2:], start=5):
        name = f"{rnd.choice(HO)} {rnd.choice(DEM)} {rnd.choice(TEN)}"
        execute("""INSERT INTO members(student_id,full_name,email,faculty,class_name,password_hash,role_id,
                   department_id,joined_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (f"SV{i:03d}", name, f"sv{i:03d}@club.vn", rnd.choice(FACULTIES), "K66", pw, role["head"],
                 dep, (now - timedelta(days=250)).strftime("%Y-%m-%d")), commit=False)

    # thành viên thường
    for i in range(8, 36):
        name = f"{rnd.choice(HO)} {rnd.choice(DEM)} {rnd.choice(TEN)}"
        execute("""INSERT INTO members(student_id,full_name,email,phone,faculty,class_name,gender,password_hash,
                   role_id,department_id,joined_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"SV{i:03d}", name, f"sv{i:03d}@club.vn", "03" + str(rnd.randint(10000000, 99999999)),
                 rnd.choice(FACULTIES), f"K{rnd.choice([66, 67, 68])}", rnd.choice(["Nam", "Nữ"]), pw,
                 role["member"], rnd.choice(dept_ids),
                 (now - timedelta(days=rnd.randint(20, 280))).strftime("%Y-%m-%d")), commit=False)
    db.commit()

    members = query("SELECT id, department_id FROM members WHERE role_id != ?", (role["admin"],))
    member_ids = [m["id"] for m in members]
    # nhóm "ít tương tác" cố định để demo AI phát hiện
    lazy = set(rnd.sample(member_ids[5:], 6))
    active = [m for m in member_ids if m not in lazy]

    # ---- Sự kiện ----
    events = [
        ("Workshop Python cơ bản", "Nhập môn Python cho tân thành viên", "Phòng A2-301", -75, 3, 60, 0),
        ("Hackathon mini 24h", "Thi lập trình theo nhóm", "Hội trường B1", -50, 24, 80, 2),
        ("Talkshow: Nghề Data Engineer", "Khách mời từ doanh nghiệp", "Phòng hội thảo C", -30, 2, 100, 3),
        ("Workshop Flask & Web", "Xây dựng web với Flask", "Phòng A2-301", -12, 3, 50, 0),
        ("Team building cuối kỳ", "Gắn kết thành viên", "Công viên Thống Nhất", -4, 5, 0, 2),
        ("Workshop AI & LLM ứng dụng", "Gọi API LLM bằng Python", "Phòng A2-301", 2, 3, 60, 0),
        ("Ngày hội tuyển thành viên", "Tuyển thành viên Gen mới", "Sảnh nhà A", 9, 6, 0, 2),
    ]
    creator = 2
    for title, desc, loc, day_off, hours, cap, dep_idx in events:
        start = (now + timedelta(days=day_off)).replace(hour=8 if hours > 4 else 18, minute=0)
        eid = execute("""INSERT INTO events(title,description,location,start_time,end_time,capacity,department_id,
                         checkin_token,checkin_open,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (title, desc, loc, _fmt(start), _fmt(start + timedelta(hours=hours)), cap,
                       dept_ids[dep_idx], secrets.token_urlsafe(10), 1 if day_off == 2 else 0, creator),
                      commit=False)
        past = day_off < 0
        regs = rnd.sample(active, rnd.randint(int(len(active) * .5), int(len(active) * .85)))
        regs += rnd.sample(sorted(lazy), 1)  # thỉnh thoảng người ít tương tác vẫn đăng ký nhưng không đến
        for mid in regs:
            checked = past and mid not in lazy and rnd.random() < 0.82
            execute("""INSERT INTO registrations(event_id,member_id,ticket_code,registered_at,checked_in_at,
                       checkin_method) VALUES (?,?,?,?,?,?)""",
                    (eid, mid, secrets.token_hex(6).upper(), _fmt(start - timedelta(days=rnd.randint(1, 6))),
                     _fmt(start + timedelta(minutes=rnd.randint(0, 40))) if checked else None,
                     rnd.choice(["scan", "self"]) if checked else None), commit=False)

    # ---- Quỹ ----
    ev_ids = [r["id"] for r in query("SELECT id FROM events ORDER BY id")]
    for back in range(4, -1, -1):
        month_day = (now.replace(day=1) - timedelta(days=30 * back)).replace(day=5)
        execute("INSERT INTO funds(type,amount,category,description,txn_date,created_by) VALUES "
                "('income',?,?,?,?,4)", (len(member_ids) * 20000, "Hội phí", "Thu hội phí tháng",
                                         month_day.strftime("%Y-%m-%d")), commit=False)
    fund_rows = [
        ("income", 5000000, "Tài trợ", "Tài trợ Hackathon từ công ty ABC", -52, 1),
        ("expense", 1800000, "Ăn uống", "Đồ ăn đêm Hackathon", -50, 1),
        ("expense", 1200000, "Quà tặng - giải thưởng", "Giải thưởng Hackathon", -49, 1),
        ("expense", 350000, "In ấn - truyền thông", "In banner workshop", -76, 0),
        ("expense", 600000, "Tổ chức sự kiện", "Thuê âm thanh talkshow", -31, 2),
        ("expense", 400000, "Quà tặng - giải thưởng", "Quà cảm ơn khách mời", -30, 2),
        ("income", 2000000, "Hỗ trợ từ trường", "Kinh phí hoạt động học kỳ", -20, None),
        ("expense", 250000, "Thiết bị - văn phòng phẩm", "Mua bút, giấy", -14, None),
        ("expense", 2200000, "Tổ chức sự kiện", "Chi phí team building", -4, 4),
        ("income", 1500000, "Bán vé sự kiện", "Vé team building", -6, 4),
        ("expense", 300000, "In ấn - truyền thông", "In poster tuyển thành viên", -1, 6),
    ]
    for t, amt, cat, desc, off, ev in fund_rows:
        execute("INSERT INTO funds(type,amount,category,description,txn_date,event_id,created_by) "
                "VALUES (?,?,?,?,?,?,4)",
                (t, amt, cat, desc, (now + timedelta(days=off)).strftime("%Y-%m-%d"),
                 ev_ids[ev] if ev is not None else None), commit=False)

    # ---- Công việc ----
    task_titles = ["Thiết kế poster sự kiện", "Viết bài giới thiệu workshop", "Chuẩn bị slide bài giảng",
                   "Liên hệ khách mời", "Đặt phòng hội thảo", "Mua quà tặng", "Chạy quảng cáo fanpage",
                   "Tổng hợp form đăng ký", "Chuẩn bị máy chiếu, micro", "Viết đề thi Hackathon",
                   "Quay video recap", "Soạn thư mời tài trợ", "Cập nhật danh sách thành viên",
                   "Chụp ảnh sự kiện", "Kiểm kê thiết bị"]
    by_dept = {}
    for m in members:
        by_dept.setdefault(m["department_id"], []).append(m["id"])
    for i, title in enumerate(task_titles * 2):
        dep = rnd.choice(dept_ids)
        pool = [x for x in by_dept.get(dep, active) if x in active] or active
        assignee = rnd.choice(pool) if i % 7 else rnd.choice(sorted(lazy))
        deadline = now + timedelta(days=rnd.randint(-40, 14))
        if assignee in lazy:
            status = rnd.choice(["todo", "todo", "doing"])
        else:
            status = "done" if deadline < now and rnd.random() < .85 else rnd.choice(["todo", "doing", "done"])
        execute("""INSERT INTO tasks(title,description,assignee_id,assigner_id,department_id,priority,status,
                   deadline,created_at,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (title, f"Chi tiết: {title.lower()}.", assignee, 2, dep, rnd.choice(["low", "normal", "high"]),
                 status, deadline.strftime("%Y-%m-%d"), _fmt(deadline - timedelta(days=10)),
                 _fmt(deadline - timedelta(days=1)) if status == "done" else None), commit=False)

    # việc giao cho tài khoản demo "thanhvien" (id 5) để thử nút đổi trạng thái
    for title, status, off, prio in [("Thiết kế banner Ngày hội tuyển thành viên", "todo", 5, "high"),
                                     ("Viết caption fanpage cho Workshop AI", "doing", 1, "normal"),
                                     ("Tổng hợp ảnh Team building", "todo", -2, "low")]:
        execute("""INSERT INTO tasks(title,description,assignee_id,assigner_id,department_id,priority,status,deadline)
                   VALUES (?,?,5,3,?,?,?,?)""",
                (title, "Giao bởi Trưởng ban Truyền thông.", dept_ids[1], prio, status,
                 (now + timedelta(days=off)).strftime("%Y-%m-%d")), commit=False)

    # ---- Thông báo & biên bản ----
    execute("INSERT INTO announcements(title,content,author_id,is_pinned) VALUES (?,?,?,1)",
            ("Chào mừng đến với ClubHub!",
             "CLB chính thức dùng hệ thống ClubHub để quản lý thành viên, sự kiện và quỹ. "
             "Mọi người vào mục Hồ sơ để cập nhật thông tin nhé.", 2), commit=False)
    execute("INSERT INTO announcements(title,content,author_id,department_id) VALUES (?,?,?,?)",
            ("Họp Ban Truyền thông tối thứ 5",
             "Ban Truyền thông họp lúc 20h thứ 5 qua Google Meet để chốt kế hoạch tuyển thành viên.", 3,
             dept_ids[1]), commit=False)
    execute("INSERT INTO meetings(title,meeting_date,raw_notes,summary,created_by) VALUES (?,?,?,?,2)",
            ("Họp BCH tháng trước", (now - timedelta(days=20)).strftime("%Y-%m-%d"),
             "Thống nhất tổ chức Workshop Flask. Ban Chuyên môn phụ trách nội dung.",
             "- Quyết định: tổ chức Workshop Flask\n- Ban Chuyên môn phụ trách nội dung"), commit=False)
    db.commit()
