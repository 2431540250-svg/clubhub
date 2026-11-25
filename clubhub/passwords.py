"""Quên mật khẩu / đặt lại mật khẩu.

Luồng:
 1. Thành viên bấm "Quên mật khẩu?" -> nhập email hoặc MSSV.
 2. Hệ thống tạo mã ngẫu nhiên (chỉ lưu bản băm SHA-256, hết hạn sau 60 phút).
    - Nếu đã cấu hình máy chủ email (MAIL_SERVER...) -> gửi link qua email.
    - Nếu chưa -> yêu cầu hiện trong trang "Yêu cầu đặt lại mật khẩu" của Ban Chủ nhiệm.
      BCN bấm "Tạo link" (hạn 24 giờ) rồi gửi cho thành viên qua Zalo/Messenger.
 3. Thành viên mở link -> đặt mật khẩu mới. Link chỉ dùng được 1 lần.
Thông báo trả về luôn giống nhau dù tài khoản có tồn tại hay không (tránh dò tài khoản).
"""
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import current_app, url_for

from .db import execute, query

SELF_SERVICE_MINUTES = 60
ADMIN_LINK_HOURS = 24


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _fmt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def create_token(member_id, valid_for, emailed=False):
    """Tạo mã mới (vô hiệu các mã cũ chưa dùng) -> trả về mã gốc để đưa vào link."""
    now = datetime.now()
    execute("UPDATE password_resets SET used_at=? WHERE member_id=? AND used_at IS NULL", (_fmt(now), member_id))
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO password_resets(member_id, token_hash, created_at, expires_at, emailed) VALUES (?,?,?,?,?)",
            (member_id, _hash(token), _fmt(now), _fmt(now + valid_for), 1 if emailed else 0))
    return token


def find_valid(token):
    return query("""SELECT pr.*, m.full_name, m.email FROM password_resets pr JOIN members m ON m.id = pr.member_id
                    WHERE pr.token_hash=? AND pr.used_at IS NULL AND pr.expires_at > ? AND m.is_active=1""",
                 (_hash(token), _fmt(datetime.now())), one=True)


def mark_used(reset_id):
    execute("UPDATE password_resets SET used_at=? WHERE id=?", (_fmt(datetime.now()), reset_id))


def mail_configured():
    return bool(current_app.config.get("MAIL_SERVER"))


def send_reset_email(member, link):
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = f"[{cfg['CLUB_NAME']}] Đặt lại mật khẩu ClubHub"
    msg["From"] = cfg.get("MAIL_FROM") or cfg.get("MAIL_USERNAME")
    msg["To"] = member["email"]
    msg.set_content(f"Chào {member['full_name']},\n\nBạn (hoặc ai đó) vừa yêu cầu đặt lại mật khẩu ClubHub.\n"
                    f"Mở link sau trong {SELF_SERVICE_MINUTES} phút để đặt mật khẩu mới:\n{link}\n\n"
                    "Nếu không phải bạn, hãy bỏ qua email này.\n\n" + cfg["CLUB_NAME"])
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg.get("MAIL_PORT", 587), timeout=15) as s:
        if cfg.get("MAIL_USE_TLS", True):
            s.starttls()
        if cfg.get("MAIL_USERNAME"):
            s.login(cfg["MAIL_USERNAME"], cfg.get("MAIL_PASSWORD", ""))
        s.send_message(msg)


def request_reset(login_id):
    """Xử lý yêu cầu quên mật khẩu. Trả về 'emailed' | 'queued' | 'none' (chỉ dùng nội bộ/log)."""
    m = query("SELECT * FROM members WHERE (lower(email)=? OR lower(student_id)=?) AND is_active=1",
              (login_id.lower(), login_id.lower()), one=True)
    if m is None:
        return "none"
    # chống spam: đã có yêu cầu còn hạn trong 5 phút gần đây thì không tạo thêm
    recent = query("SELECT 1 FROM password_resets WHERE member_id=? AND used_at IS NULL AND created_at > ?",
                   (m["id"], _fmt(datetime.now() - timedelta(minutes=5))), one=True)
    if recent:
        return "queued"
    if mail_configured():
        token = create_token(m["id"], timedelta(minutes=SELF_SERVICE_MINUTES), emailed=True)
        try:
            send_reset_email(m, url_for("auth.reset_password", token=token, _external=True))
            return "emailed"
        except Exception as exc:  # gửi lỗi -> chuyển cho BCN xử lý
            current_app.logger.warning("Gửi email đặt lại mật khẩu lỗi: %s", exc)
            execute("UPDATE password_resets SET emailed=0 WHERE token_hash=?", (_hash(token),))
            return "queued"
    create_token(m["id"], timedelta(minutes=SELF_SERVICE_MINUTES))
    return "queued"


def pending_requests():
    return query("""SELECT pr.id, pr.created_at, pr.expires_at, m.id AS member_id, m.full_name, m.student_id, m.email,
                           d.name AS department_name
                    FROM password_resets pr JOIN members m ON m.id = pr.member_id
                    LEFT JOIN departments d ON d.id = m.department_id
                    WHERE pr.used_at IS NULL AND pr.emailed = 0 AND pr.expires_at > ?
                    ORDER BY pr.created_at DESC""", (_fmt(datetime.now()),))
