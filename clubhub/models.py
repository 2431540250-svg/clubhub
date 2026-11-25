"""Mô hình dữ liệu (ERD) của ứng dụng.

Thực thể chính theo đề bài: Member, Department, Role, Event, Fund
+ các bảng phụ trợ: Registration (đăng ký/điểm danh), Task, Announcement,
  Meeting (biên bản), AIDraft (bản nháp AI chờ duyệt).

Quan hệ:
  Role 1—n Member            Department 1—n Member
  Event 1—n Registration n—1 Member     (Member n—n Event qua Registration)
  Event 1—n Fund (khoản thu/chi gắn sự kiện, có thể NULL)
  Member 1—n Task (người được giao) ; Member 1—n Task (người giao)
  Department 1—n Announcement (NULL = gửi toàn CLB)
"""

SCHEMA = """
DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS ai_drafts;
DROP TABLE IF EXISTS meetings;
DROP TABLE IF EXISTS announcements;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS funds;
DROP TABLE IF EXISTS registrations;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS members;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS roles;

CREATE TABLE roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,      -- admin | president | head | treasurer | member
    name        TEXT NOT NULL,
    description TEXT
);

CREATE TABLE departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL UNIQUE,    -- MSSV
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    phone         TEXT,
    faculty       TEXT,
    class_name    TEXT,
    gender        TEXT,
    birthday      TEXT,
    password_hash TEXT NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    joined_at     TEXT NOT NULL DEFAULT (date('now','localtime')),
    last_login    TEXT,
    announcements_seen_id INTEGER NOT NULL DEFAULT 0  -- id thông báo mới nhất đã xem (tính 'chưa đọc')
);

CREATE TABLE events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    location      TEXT,
    start_time    TEXT NOT NULL,           -- 'YYYY-MM-DD HH:MM'
    end_time      TEXT NOT NULL,
    capacity      INTEGER NOT NULL DEFAULT 0,  -- 0 = không giới hạn
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    checkin_token TEXT NOT NULL UNIQUE,    -- mã QR chung của sự kiện (tự check-in)
    checkin_open  INTEGER NOT NULL DEFAULT 0,  -- 0 = tự động theo giờ, 1 = mở ngay, 2 = đóng
    created_by    INTEGER REFERENCES members(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE registrations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id      INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    ticket_code    TEXT NOT NULL UNIQUE,   -- mã QR vé cá nhân
    registered_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    checked_in_at  TEXT,
    checkin_method TEXT,                   -- scan | self | manual
    UNIQUE(event_id, member_id)
);

CREATE TABLE funds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL CHECK (type IN ('income','expense')),
    amount      INTEGER NOT NULL CHECK (amount > 0),   -- VNĐ
    category    TEXT NOT NULL,
    description TEXT,
    txn_date    TEXT NOT NULL,             -- 'YYYY-MM-DD'
    event_id    INTEGER REFERENCES events(id) ON DELETE SET NULL,
    created_by  INTEGER REFERENCES members(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    assignee_id   INTEGER REFERENCES members(id) ON DELETE SET NULL,
    assigner_id   INTEGER REFERENCES members(id) ON DELETE SET NULL,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    event_id      INTEGER REFERENCES events(id) ON DELETE SET NULL,
    priority      TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high')),
    status        TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
    deadline      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at  TEXT
);

CREATE TABLE announcements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    department_id   INTEGER REFERENCES departments(id) ON DELETE SET NULL,  -- NULL = toàn CLB
    author_id       INTEGER REFERENCES members(id) ON DELETE SET NULL,
    is_pinned       INTEGER NOT NULL DEFAULT 0,
    is_ai_generated INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE meetings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    meeting_date TEXT NOT NULL,
    raw_notes    TEXT NOT NULL,
    summary      TEXT,
    created_by   INTEGER REFERENCES members(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE ai_drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,             -- announcement | minutes
    title       TEXT,
    input_text  TEXT NOT NULL,
    output_text TEXT NOT NULL,
    provider    TEXT,                      -- gemini | openai | local
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected')),
    created_by  INTEGER REFERENCES members(id) ON DELETE SET NULL,
    reviewed_by INTEGER REFERENCES members(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    reviewed_at TEXT
);

CREATE TABLE password_resets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,      -- chỉ lưu bản băm SHA-256 của mã
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    emailed     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_members_dept ON members(department_id);
CREATE INDEX idx_reg_event ON registrations(event_id);
CREATE INDEX idx_funds_date ON funds(txn_date);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
"""

# Nhãn hiển thị tiếng Việt
TASK_STATUS = {"todo": "Chưa làm", "doing": "Đang làm", "done": "Hoàn thành"}
TASK_PRIORITY = {"low": "Thấp", "normal": "Bình thường", "high": "Cao"}
FUND_TYPE = {"income": "Thu", "expense": "Chi"}
INCOME_CATEGORIES = ["Hội phí", "Tài trợ", "Bán vé sự kiện", "Hỗ trợ từ trường", "Khác"]
EXPENSE_CATEGORIES = ["Tổ chức sự kiện", "In ấn - truyền thông", "Ăn uống", "Quà tặng - giải thưởng",
                      "Thiết bị - văn phòng phẩm", "Khác"]

# Cập nhật CSDL cũ (tạo từ phiên bản trước) mà không mất dữ liệu
MIGRATIONS = [
    ("members", "announcements_seen_id", "ALTER TABLE members ADD COLUMN announcements_seen_id INTEGER NOT NULL DEFAULT 0"),
]
EXTRA_TABLES = """
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    expires_at TEXT NOT NULL,
    used_at TEXT,
    emailed INTEGER NOT NULL DEFAULT 0
);
"""
