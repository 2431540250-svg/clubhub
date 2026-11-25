"""Task 2 – Hồ sơ thành viên, ban, vai trò, import/export CSV."""
import csv
import io
import re
import sqlite3

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template,
                   request, url_for)
from werkzeug.security import generate_password_hash

from ..auth import has_permission, is_dept_scoped, permission_required
from ..db import execute, query, scalar
from ..ui import Pagination, field_error, form_failed

bp = Blueprint("members", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CSV_FIELDS = ["student_id", "full_name", "email", "phone", "faculty", "class_name", "department", "role"]


def _roles_for_select():
    rows = query("SELECT * FROM roles ORDER BY id")
    # chỉ admin mới được cấp quyền admin
    if g.user["role_code"] != "admin":
        rows = [r for r in rows if r["code"] != "admin"]
    return rows


def _validate(form, member_id=None):
    """Kiểm tra form thành viên; lỗi gắn vào từng ô. Trả về True nếu hợp lệ."""
    sid, name, email = form.get("student_id", "").strip(), form.get("full_name", "").strip(), \
        form.get("email", "").strip().lower()
    if not sid:
        field_error("student_id", "Nhập MSSV.")
    elif query("SELECT 1 FROM members WHERE lower(student_id)=lower(?) AND id != ?", (sid, member_id or 0), one=True):
        field_error("student_id", "MSSV này đã tồn tại.")
    if not name:
        field_error("full_name", "Nhập họ tên.")
    if not EMAIL_RE.match(email):
        field_error("email", "Email không hợp lệ (vd: ten@club.vn).")
    elif query("SELECT 1 FROM members WHERE lower(email)=? AND id != ?", (email, member_id or 0), one=True):
        field_error("email", "Email này đã được dùng.")
    if form.get("password") and len(form["password"]) < 6:
        field_error("password", "Mật khẩu tối thiểu 6 ký tự.")
    role = query("SELECT code FROM roles WHERE id=?", (form.get("role_id"),), one=True)
    if role is None:
        field_error("role_id", "Chọn vai trò.")
    elif role["code"] == "admin" and g.user["role_code"] != "admin":
        field_error("role_id", "Chỉ quản trị hệ thống mới cấp được vai trò admin.")
    return not form_failed()


def _get_member_or_404(member_id):
    m = query("""SELECT m.*, r.code AS role_code, r.name AS role_name, d.name AS department_name
                 FROM members m JOIN roles r ON r.id=m.role_id LEFT JOIN departments d ON d.id=m.department_id
                 WHERE m.id=?""", (member_id,), one=True)
    if m is None:
        abort(404)
    if is_dept_scoped(g.user) and m["department_id"] != g.user["department_id"]:
        abort(403)
    return m


# ------------------------------------------------------------------ Thành viên
@bp.route("/members")
@permission_required("member.view")
def list_members():
    q = request.args.get("q", "").strip()
    dept = request.args.get("department", type=int)
    role = request.args.get("role", "")
    status = request.args.get("status", "active")
    sql = """SELECT m.*, r.code AS role_code, r.name AS role_name, d.name AS department_name
             FROM members m JOIN roles r ON r.id=m.role_id LEFT JOIN departments d ON d.id=m.department_id
             WHERE 1=1"""
    args = []
    if is_dept_scoped(g.user):  # trưởng ban chỉ thấy ban mình
        sql += " AND m.department_id=?"
        args.append(g.user["department_id"])
    elif dept:
        sql += " AND m.department_id=?"
        args.append(dept)
    if q:
        sql += " AND (m.full_name LIKE ? OR m.student_id LIKE ? OR m.email LIKE ?)"
        args += [f"%{q}%"] * 3
    if role:
        sql += " AND r.code=?"
        args.append(role)
    if status == "active":
        sql += " AND m.is_active=1"
    elif status == "inactive":
        sql += " AND m.is_active=0"
    sql += " ORDER BY r.id, m.full_name"
    pager = Pagination(scalar(f"SELECT COUNT(*) FROM ({sql})", args), request.args.get("page", 1, type=int), 20)
    members = query(sql + " LIMIT ? OFFSET ?", args + [pager.per_page, pager.offset])
    from ..passwords import pending_requests
    pending = len(pending_requests()) if has_permission(g.user, "member.manage") else 0
    return render_template("members/list.html", members=members, pager=pager, pending_resets=pending,
                           departments=query("SELECT * FROM departments ORDER BY name"),
                           roles=query("SELECT * FROM roles ORDER BY id"),
                           filters=dict(q=q, department=dept, role=role, status=status))


@bp.route("/members/<int:member_id>")
@permission_required("member.view")
def detail(member_id):
    m = _get_member_or_404(member_id)
    events = query("""SELECT e.title, e.start_time, r.checked_in_at FROM registrations r
                      JOIN events e ON e.id=r.event_id WHERE r.member_id=? ORDER BY e.start_time DESC""",
                   (member_id,))
    tasks = query("SELECT * FROM tasks WHERE assignee_id=? ORDER BY created_at DESC", (member_id,))
    return render_template("members/detail.html", m=m, events=events, tasks=tasks)


@bp.route("/members/new", methods=["GET", "POST"])
@permission_required("member.manage")
def create():
    if request.method == "POST":
        if _validate(request.form):
            f = request.form
            pw = f.get("password") or f.get("student_id").strip()
            mid = execute("""INSERT INTO members(student_id,full_name,email,phone,faculty,class_name,gender,
                             birthday,password_hash,role_id,department_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (f["student_id"].strip(), f["full_name"].strip(), f["email"].strip().lower(),
                           f.get("phone"), f.get("faculty"), f.get("class_name"), f.get("gender"),
                           f.get("birthday"), generate_password_hash(pw), f["role_id"],
                           f.get("department_id") or None))
            flash("Đã thêm thành viên. Mật khẩu mặc định là MSSV nếu không nhập.", "success")
            return redirect(url_for("members.detail", member_id=mid))
    return render_template("members/form.html", m=request.form or None, roles=_roles_for_select(),
                           departments=query("SELECT * FROM departments ORDER BY name"))


@bp.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
@permission_required("member.manage")
def edit(member_id):
    m = _get_member_or_404(member_id)
    if m["role_code"] == "admin" and g.user["role_code"] != "admin":
        abort(403)
    if request.method == "POST":
        if _validate(request.form, member_id):
            f = request.form
            execute("""UPDATE members SET student_id=?, full_name=?, email=?, phone=?, faculty=?, class_name=?,
                       gender=?, birthday=?, role_id=?, department_id=?, is_active=? WHERE id=?""",
                    (f["student_id"].strip(), f["full_name"].strip(), f["email"].strip().lower(), f.get("phone"),
                     f.get("faculty"), f.get("class_name"), f.get("gender"), f.get("birthday"), f["role_id"],
                     f.get("department_id") or None, 1 if f.get("is_active") else 0, member_id))
            if f.get("password"):
                execute("UPDATE members SET password_hash=? WHERE id=?",
                        (generate_password_hash(f["password"]), member_id))
            flash("Đã cập nhật.", "success")
            return redirect(url_for("members.detail", member_id=member_id))
        # giữ lại dữ liệu người dùng vừa nhập để sửa tiếp
        m = {**dict(m), **request.form.to_dict(), "is_active": 1 if request.form.get("is_active") else 0}
    return render_template("members/form.html", m=m, roles=_roles_for_select(),
                           departments=query("SELECT * FROM departments ORDER BY name"))


@bp.route("/members/<int:member_id>/delete", methods=["POST"])
@permission_required("member.manage")
def delete(member_id):
    m = _get_member_or_404(member_id)
    if m["id"] == g.user["id"] or (m["role_code"] == "admin" and g.user["role_code"] != "admin"):
        flash("Không thể xóa tài khoản này.", "danger")
    else:
        execute("DELETE FROM members WHERE id=?", (member_id,))
        flash(f"Đã xóa {m['full_name']}.", "info")
    return redirect(url_for("members.list_members"))


# ------------------------------------------------------------------ Đặt lại mật khẩu (BCN)
@bp.route("/members/password-requests")
@permission_required("member.manage")
def password_requests():
    from ..passwords import pending_requests
    return render_template("members/password_requests.html", rows=pending_requests(), link=None)


@bp.route("/members/<int:member_id>/reset-link", methods=["POST"])
@permission_required("member.manage")
def reset_link(member_id):
    """Tạo link đặt lại mật khẩu (hạn 24h) để BCN gửi cho thành viên qua Zalo/Messenger."""
    from datetime import timedelta

    from ..passwords import ADMIN_LINK_HOURS, create_token, pending_requests
    m = _get_member_or_404(member_id)
    if m["role_code"] == "admin" and g.user["role_code"] != "admin":
        abort(403)
    token = create_token(member_id, timedelta(hours=ADMIN_LINK_HOURS), emailed=True)
    link = url_for("auth.reset_password", token=token, _external=True)
    return render_template("members/password_requests.html", rows=pending_requests(), link=link, target=m,
                           hours=ADMIN_LINK_HOURS)


# ------------------------------------------------------------------ Import / Export CSV
@bp.route("/members/import", methods=["GET", "POST"])
@permission_required("member.import")
def import_csv():
    result = None
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("Hãy chọn file .csv", "danger")
            return redirect(request.url)
        text = file.read().decode("utf-8-sig", errors="replace")
        result = import_members_from_text(text, update_existing=bool(request.form.get("update")))
        flash(f"Thêm mới {result['created']}, cập nhật {result['updated']}, lỗi {len(result['errors'])}.",
              "success" if not result["errors"] else "warning")
    return render_template("members/import.html", result=result, fields=CSV_FIELDS)


def import_members_from_text(text, update_existing=False):
    """Đọc CSV -> thêm/cập nhật thành viên. Trả về thống kê. (Tách hàm để dễ kiểm thử.)"""
    reader = csv.DictReader(io.StringIO(text))
    depts = {r["name"].strip().lower(): r["id"] for r in query("SELECT id, name FROM departments")}
    roles = {}
    for r in query("SELECT id, code, name FROM roles"):
        roles[r["code"]] = r["id"]
        roles[r["name"].lower()] = r["id"]
    created = updated = 0
    errors = []
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        sid, name, email = row.get("student_id"), row.get("full_name"), row.get("email", "").lower()
        if not sid or not name or not EMAIL_RE.match(email):
            errors.append(f"Dòng {line_no}: thiếu MSSV/họ tên hoặc email sai.")
            continue
        role_id = roles.get(row.get("role", "").lower() or "member", roles["member"])
        if role_id == roles["admin"]:
            role_id = roles["member"]  # không cho import tài khoản admin
        dept_name = row.get("department", "").lower()
        dept_id = depts.get(dept_name)
        if dept_name and dept_id is None:  # tự tạo ban mới nếu chưa có
            dept_id = execute("INSERT INTO departments(name) VALUES (?)", (row["department"],))
            depts[dept_name] = dept_id
        existing = query("SELECT id FROM members WHERE lower(student_id)=lower(?)", (sid,), one=True)
        try:
            if existing:
                if update_existing:
                    execute("""UPDATE members SET full_name=?, email=?, phone=?, faculty=?, class_name=?,
                               department_id=?, role_id=? WHERE id=?""",
                            (name, email, row.get("phone"), row.get("faculty"), row.get("class_name"),
                             dept_id, role_id, existing["id"]))
                    updated += 1
                else:
                    errors.append(f"Dòng {line_no}: MSSV {sid} đã tồn tại (bỏ qua).")
            else:
                execute("""INSERT INTO members(student_id,full_name,email,phone,faculty,class_name,password_hash,
                           role_id,department_id) VALUES (?,?,?,?,?,?,?,?,?)""",
                        (sid, name, email, row.get("phone"), row.get("faculty"), row.get("class_name"),
                         generate_password_hash(sid), role_id, dept_id))
                created += 1
        except sqlite3.IntegrityError:
            errors.append(f"Dòng {line_no}: email {email} bị trùng.")
    return {"created": created, "updated": updated, "errors": errors}


@bp.route("/members/import/template.csv")
@permission_required("member.import")
def csv_template():
    sample = ",".join(CSV_FIELDS) + "\n" + \
        "SV100,Nguyễn Văn Mới,sv100@club.vn,0912345678,CNTT,K68,Ban Sự kiện,member\n" + \
        "SV101,Trần Thị Hai,sv101@club.vn,0987654321,Kinh tế,K68,Ban Truyền thông,Thành viên\n"
    return Response("﻿" + sample, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=mau_import_thanh_vien.csv"})


@bp.route("/members/export.csv")
@permission_required("member.view")
def export_csv():
    sql = """SELECT m.student_id, m.full_name, m.email, m.phone, m.faculty, m.class_name,
                    d.name AS department, r.code AS role, m.joined_at
             FROM members m JOIN roles r ON r.id=m.role_id LEFT JOIN departments d ON d.id=m.department_id
             WHERE m.is_active=1"""
    args = ()
    if is_dept_scoped(g.user):
        sql += " AND m.department_id=?"
        args = (g.user["department_id"],)
    rows = query(sql + " ORDER BY m.student_id", args)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_FIELDS + ["joined_at"])
    for r in rows:
        w.writerow(list(r))
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=thanh_vien.csv"})


# ------------------------------------------------------------------ Ban
@bp.route("/departments", methods=["GET", "POST"])
@permission_required("member.view")
def departments():
    if request.method == "POST":
        if not has_permission(g.user, "department.manage"):
            abort(403)
        name = request.form.get("name", "").strip()
        dept_id = request.form.get("id", type=int)
        if not name:
            flash("Tên ban là bắt buộc.", "danger")
        else:
            try:
                if dept_id:
                    execute("UPDATE departments SET name=?, description=? WHERE id=?",
                            (name, request.form.get("description"), dept_id))
                else:
                    execute("INSERT INTO departments(name, description) VALUES (?,?)",
                            (name, request.form.get("description")))
                flash("Đã lưu ban.", "success")
            except sqlite3.IntegrityError:
                flash("Tên ban đã tồn tại.", "danger")
        return redirect(url_for("members.departments"))
    rows = query("""SELECT d.*, COUNT(m.id) AS member_count,
                    (SELECT full_name FROM members h JOIN roles r ON r.id=h.role_id
                     WHERE h.department_id=d.id AND r.code IN ('head','president') LIMIT 1) AS head_name
                    FROM departments d LEFT JOIN members m ON m.department_id=d.id AND m.is_active=1
                    GROUP BY d.id ORDER BY d.name""")
    return render_template("departments/list.html", departments=rows)


@bp.route("/departments/<int:dept_id>/delete", methods=["POST"])
@permission_required("department.manage")
def delete_department(dept_id):
    execute("DELETE FROM departments WHERE id=?", (dept_id,))
    flash("Đã xóa ban (thành viên trong ban chuyển về 'chưa phân ban').", "info")
    return redirect(url_for("members.departments"))
