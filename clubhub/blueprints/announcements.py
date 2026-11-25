"""Task 4c – Thông báo nội bộ."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..auth import has_permission, is_dept_scoped, login_required, permission_required
from ..db import execute, query
from ..ui import field_error, form_failed

bp = Blueprint("announcements", __name__, url_prefix="/announcements")


@bp.route("/")
@login_required
def list_all():
    sql = """SELECT a.*, m.full_name AS author, d.name AS department_name FROM announcements a
             LEFT JOIN members m ON m.id=a.author_id LEFT JOIN departments d ON d.id=a.department_id"""
    args = ()
    if g.user["role_code"] not in ("admin", "president"):
        sql += " WHERE a.department_id IS NULL OR a.department_id=?"
        args = (g.user["department_id"],)
    rows = query(sql + " ORDER BY a.is_pinned DESC, a.created_at DESC", args)
    seen = g.user["announcements_seen_id"] or 0
    new_ids = {r["id"] for r in rows if r["id"] > seen and r["author_id"] != g.user["id"]}
    # đánh dấu đã xem -> huy hiệu "chưa đọc" trên menu về 0
    if rows:
        execute("UPDATE members SET announcements_seen_id=? WHERE id=?",
                (max(seen, max(r["id"] for r in rows)), g.user["id"]))
    return render_template("announcements/list.html", rows=rows, new_ids=new_ids, UNREAD=0)


def _get(ann_id):
    a = query("SELECT * FROM announcements WHERE id=?", (ann_id,), one=True)
    if a is None:
        abort(404)
    if is_dept_scoped(g.user) and a["author_id"] != g.user["id"]:
        abort(403)
    return a


def _save(form, ann_id=None):
    title, content = form.get("title", "").strip(), form.get("content", "").strip()
    if not title:
        field_error("title", "Nhập tiêu đề.")
    if not content:
        field_error("content", "Nhập nội dung thông báo.")
    if form_failed():
        return False
    dept = form.get("department_id", type=int) or None
    if is_dept_scoped(g.user) and dept not in (None, g.user["department_id"]):
        dept = g.user["department_id"]
    pinned = 1 if form.get("is_pinned") and g.user["role_code"] in ("admin", "president") else 0
    if ann_id:
        execute("UPDATE announcements SET title=?, content=?, department_id=?, is_pinned=? WHERE id=?",
                (title, content, dept, pinned, ann_id))
    else:
        execute("INSERT INTO announcements(title,content,department_id,author_id,is_pinned,is_ai_generated) "
                "VALUES (?,?,?,?,?,?)", (title, content, dept, g.user["id"], pinned,
                                          1 if form.get("is_ai_generated") else 0))
    flash("Đã đăng thông báo.", "success")
    return True


@bp.route("/new", methods=["GET", "POST"])
@permission_required("announcement.manage")
def create():
    if request.method == "POST" and _save(request.form):
        return redirect(url_for("announcements.list_all"))
    return render_template("announcements/form.html", a=None, departments=query("SELECT * FROM departments"))


@bp.route("/<int:ann_id>/edit", methods=["GET", "POST"])
@permission_required("announcement.manage")
def edit(ann_id):
    a = _get(ann_id)
    if request.method == "POST" and _save(request.form, ann_id):
        return redirect(url_for("announcements.list_all"))
    return render_template("announcements/form.html", a=a, departments=query("SELECT * FROM departments"))


@bp.route("/<int:ann_id>/delete", methods=["POST"])
@permission_required("announcement.manage")
def delete(ann_id):
    _get(ann_id)
    execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    flash("Đã xóa thông báo.", "info")
    return redirect(url_for("announcements.list_all"))
