"""Xác thực (đăng nhập bằng session) và phân quyền RBAC.

RBAC = Role-Based Access Control: mỗi thành viên có 1 vai trò (role),
mỗi vai trò có 1 tập quyền (permission). Route kiểm tra quyền bằng
decorator @permission_required("..."), template ẩn/hiện menu bằng can("...").
"""
import functools
from datetime import datetime

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query
from .ui import field_error, form_failed

# ------------------------------------------------------------------
# MA TRẬN QUYỀN (dùng cho slide T2)
# ------------------------------------------------------------------
ROLE_LABELS = {
    "admin": "Quản trị hệ thống",
    "president": "Chủ nhiệm",
    "head": "Trưởng ban",
    "treasurer": "Thủ quỹ",
    "member": "Thành viên",
}

PERMISSIONS = {
    # mã quyền           : mô tả
    "member.view":        "Xem danh sách thành viên",
    "member.manage":      "Thêm/sửa/xóa thành viên, gán ban & vai trò",
    "member.import":      "Import thành viên từ CSV",
    "department.manage":  "Quản lý ban",
    "event.manage":       "Tạo/sửa sự kiện",
    "event.checkin":      "Quét QR điểm danh",
    "fund.view":          "Xem sổ thu chi",
    "fund.manage":        "Ghi thu/chi",
    "task.manage":        "Giao việc",
    "announcement.manage": "Đăng thông báo",
    "report.view":        "Xem & xuất báo cáo",
    "ai.use":             "Dùng trợ lý AI",
    "ai.approve":         "Duyệt bản nháp AI",
}

ROLE_PERMISSIONS = {
    "admin": set(PERMISSIONS),  # toàn quyền
    "president": {"member.view", "member.manage", "member.import", "department.manage",
                  "event.manage", "event.checkin", "fund.view", "task.manage",
                  "announcement.manage", "report.view", "ai.use", "ai.approve"},
    "head": {"member.view", "event.manage", "event.checkin", "task.manage",
             "announcement.manage", "ai.use"},
    "treasurer": {"member.view", "fund.view", "fund.manage", "report.view", "event.checkin"},
    "member": set(),  # chỉ các chức năng cá nhân: sự kiện, việc của tôi, thông báo
}


def has_permission(user, perm):
    if user is None:
        return False
    return perm in ROLE_PERMISSIONS.get(user["role_code"], set())


def can(perm):
    """Dùng trong template: {% if can('fund.view') %}"""
    return has_permission(g.get("user"), perm)


def is_dept_scoped(user):
    """Trưởng ban chỉ thao tác trong phạm vi ban của mình."""
    return user is not None and user["role_code"] == "head"


# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Vui lòng đăng nhập.", "warning")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def permission_required(perm):
    def decorator(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not has_permission(g.user, perm):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def load_user(member_id):
    return query(
        """SELECT m.*, r.code AS role_code, r.name AS role_name, d.name AS department_name
           FROM members m JOIN roles r ON r.id = m.role_id
           LEFT JOIN departments d ON d.id = m.department_id
           WHERE m.id = ? AND m.is_active = 1""",
        (member_id,), one=True)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_logged_in_user():
    uid = session.get("member_id")
    g.user = load_user(uid) if uid else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        login_id = request.form.get("login", "").strip().lower()
        password = request.form.get("password", "")
        user = query("SELECT * FROM members WHERE (lower(email)=? OR lower(student_id)=?) AND is_active=1",
                     (login_id, login_id), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Sai email/MSSV hoặc mật khẩu.", "danger")
        else:
            session.clear()
            session["member_id"] = user["id"]
            execute("UPDATE members SET last_login=? WHERE id=?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M"), user["id"]))
            flash(f"Xin chào {user['full_name']}!", "success")
            nxt = request.args.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    from .passwords import mail_configured, request_reset
    sent = False
    if request.method == "POST":
        login_id = request.form.get("login", "").strip()
        if not login_id:
            field_error("login", "Nhập email hoặc MSSV của bạn.")
            form_failed("Vui lòng nhập email hoặc MSSV.")
        else:
            request_reset(login_id)
            sent = True
    return render_template("auth/forgot.html", sent=sent, mail=mail_configured())


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from .passwords import find_valid, mark_used
    reset = find_valid(token)
    if reset is None:
        return render_template("auth/reset.html", link_invalid=True), 400
    if request.method == "POST":
        new, confirm = request.form.get("new", ""), request.form.get("confirm", "")
        if len(new) < 6:
            field_error("new", "Mật khẩu tối thiểu 6 ký tự.")
        elif new != confirm:
            field_error("confirm", "Nhập lại chưa khớp.")
        if not form_failed():
            execute("UPDATE members SET password_hash=? WHERE id=?", (generate_password_hash(new), reset["member_id"]))
            mark_used(reset["id"])
            flash("Đã đặt mật khẩu mới. Hãy đăng nhập.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", link_invalid=False, reset=reset)


@bp.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "info":
            execute("UPDATE members SET phone=?, faculty=?, class_name=?, birthday=?, gender=? WHERE id=?",
                    (request.form.get("phone"), request.form.get("faculty"), request.form.get("class_name"),
                     request.form.get("birthday"), request.form.get("gender"), g.user["id"]))
            flash("Đã cập nhật hồ sơ.", "success")
        elif action == "password":
            old, new, confirm = (request.form.get(k, "") for k in ("old", "new", "confirm"))
            row = query("SELECT password_hash FROM members WHERE id=?", (g.user["id"],), one=True)
            if not check_password_hash(row["password_hash"], old):
                field_error("old", "Mật khẩu cũ không đúng.")
            if len(new) < 6:
                field_error("new", "Mật khẩu mới tối thiểu 6 ký tự.")
            elif new != confirm:
                field_error("confirm", "Nhập lại chưa khớp với mật khẩu mới.")
            if not form_failed():
                execute("UPDATE members SET password_hash=? WHERE id=?",
                        (generate_password_hash(new), g.user["id"]))
                flash("Đã đổi mật khẩu.", "success")
            else:
                return _render_profile()
        return redirect(url_for("auth.profile"))
    return _render_profile()


def _render_profile():
    stats = query(
        """SELECT
             (SELECT COUNT(*) FROM registrations WHERE member_id=:id) AS registered,
             (SELECT COUNT(*) FROM registrations WHERE member_id=:id AND checked_in_at IS NOT NULL) AS attended,
             (SELECT COUNT(*) FROM tasks WHERE assignee_id=:id) AS tasks,
             (SELECT COUNT(*) FROM tasks WHERE assignee_id=:id AND status='done') AS tasks_done""",
        {"id": g.user["id"]}, one=True)
    return render_template("auth/profile.html", stats=stats)
