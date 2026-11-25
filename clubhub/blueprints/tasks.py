"""Task 4b – Giao việc nội bộ (bảng Kanban)."""
from datetime import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..auth import has_permission, is_dept_scoped, login_required, permission_required
from ..db import execute, query
from ..ui import field_error, form_failed
from ..models import TASK_PRIORITY, TASK_STATUS

bp = Blueprint("tasks", __name__, url_prefix="/tasks")


def _assignable_members():
    sql = "SELECT id, full_name, student_id, department_id FROM members WHERE is_active=1"
    args = ()
    if is_dept_scoped(g.user):
        sql += " AND department_id=?"
        args = (g.user["department_id"],)
    return query(sql + " ORDER BY full_name", args)


def _get_task(task_id):
    t = query("SELECT * FROM tasks WHERE id=?", (task_id,), one=True)
    if t is None:
        abort(404)
    return t


def _can_manage_task(t):
    if not has_permission(g.user, "task.manage"):
        return False
    if is_dept_scoped(g.user):
        return t["department_id"] == g.user["department_id"] or t["assigner_id"] == g.user["id"]
    return True


@bp.route("/")
@login_required
def board():
    """Mặc định: việc của tôi. Người có quyền giao việc: xem toàn bộ (trưởng ban: ban mình)."""
    scope = request.args.get("scope", "all" if has_permission(g.user, "task.manage") else "mine")
    if scope == "all" and not has_permission(g.user, "task.manage"):
        scope = "mine"
    sql = """SELECT t.*, a.full_name AS assignee_name, d.name AS department_name, e.title AS event_title
             FROM tasks t LEFT JOIN members a ON a.id=t.assignee_id
             LEFT JOIN departments d ON d.id=t.department_id LEFT JOIN events e ON e.id=t.event_id WHERE 1=1"""
    args = []
    if scope == "mine":
        sql += " AND t.assignee_id=?"
        args.append(g.user["id"])
    elif is_dept_scoped(g.user):
        sql += " AND t.department_id=?"
        args.append(g.user["department_id"])
    dept = request.args.get("department", type=int)
    if dept and scope == "all" and not is_dept_scoped(g.user):
        sql += " AND t.department_id=?"
        args.append(dept)
    q = request.args.get("q", "").strip()
    if q:
        sql += " AND (t.title LIKE ? OR t.description LIKE ? OR a.full_name LIKE ?)"
        args += [f"%{q}%"] * 3
    if request.args.get("overdue"):
        sql += " AND t.status != 'done' AND t.deadline < date('now','localtime')"
    tasks = query(sql + " ORDER BY CASE t.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, t.deadline",
                  args)
    columns = {s: [t for t in tasks if t["status"] == s] for s in TASK_STATUS}
    return render_template("tasks/board.html", columns=columns, scope=scope, dept=dept, q=q,
                           overdue=bool(request.args.get("overdue")),
                           departments=query("SELECT * FROM departments ORDER BY name"))


def _save(form, task_id=None):
    assignee = form.get("assignee_id", type=int)
    allowed = {m["id"]: m for m in _assignable_members()}
    if not form.get("title", "").strip():
        field_error("title", "Nhập tiêu đề công việc.")
    if assignee and assignee not in allowed:
        field_error("assignee_id", "Bạn chỉ được giao việc cho thành viên trong ban của mình.")
    if form_failed():
        return None
    dept = form.get("department_id", type=int)
    if is_dept_scoped(g.user):
        dept = g.user["department_id"]
    elif not dept and assignee:
        dept = allowed[assignee]["department_id"]
    status = form.get("status", "todo")
    vals = (form["title"].strip(), form.get("description"), assignee, dept, form.get("event_id") or None,
            form.get("priority", "normal") if form.get("priority") in TASK_PRIORITY else "normal",
            status if status in TASK_STATUS else "todo", form.get("deadline") or None)
    done_at = datetime.now().strftime("%Y-%m-%d %H:%M") if vals[6] == "done" else None
    if task_id:
        execute("""UPDATE tasks SET title=?, description=?, assignee_id=?, department_id=?, event_id=?, priority=?,
                   status=?, deadline=?, completed_at=COALESCE(completed_at, ?) WHERE id=?""",
                vals + (done_at, task_id))
        if vals[6] != "done":
            execute("UPDATE tasks SET completed_at=NULL WHERE id=?", (task_id,))
        return task_id
    return execute("""INSERT INTO tasks(title,description,assignee_id,department_id,event_id,priority,status,deadline,
                      assigner_id,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""", vals + (g.user["id"], done_at))


def _form_ctx(t=None):
    return dict(t=t, members=_assignable_members(), departments=query("SELECT * FROM departments ORDER BY name"),
                events=query("SELECT id, title FROM events ORDER BY start_time DESC"))


@bp.route("/new", methods=["GET", "POST"])
@permission_required("task.manage")
def create():
    if request.method == "POST":
        if _save(request.form):
            flash("Đã giao việc.", "success")
            return redirect(url_for("tasks.board"))
    prefill = {"title": request.args.get("title", ""), "description": request.args.get("description", ""),
               "assignee_id": request.args.get("assignee_id", type=int), "priority": "normal", "status": "todo"}
    return render_template("tasks/form.html", **_form_ctx(prefill))


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit(task_id):
    t = _get_task(task_id)
    if not _can_manage_task(t):
        abort(403)
    if request.method == "POST" and _save(request.form, task_id):
        flash("Đã cập nhật công việc.", "success")
        return redirect(url_for("tasks.board"))
    return render_template("tasks/form.html", **_form_ctx(t))


@bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
def set_status(task_id):
    """Người được giao hoặc người quản lý đổi trạng thái (kéo thả trên Kanban gọi route này)."""
    t = _get_task(task_id)
    if t["assignee_id"] != g.user["id"] and not _can_manage_task(t):
        abort(403)
    status = request.form.get("status") or (request.get_json(silent=True) or {}).get("status")
    if status not in TASK_STATUS:
        abort(400)
    done_at = datetime.now().strftime("%Y-%m-%d %H:%M") if status == "done" else None
    execute("UPDATE tasks SET status=?, completed_at=? WHERE id=?", (status, done_at, task_id))
    if request.is_json:
        return {"ok": True}
    from ..models import TASK_STATUS as _S
    flash(f"“{t['title']}” → {_S[status]}", "success")
    nxt = request.form.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("tasks.board"))


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete(task_id):
    if not _can_manage_task(_get_task(task_id)):
        abort(403)
    execute("DELETE FROM tasks WHERE id=?", (task_id,))
    flash("Đã xóa công việc.", "info")
    return redirect(url_for("tasks.board"))
