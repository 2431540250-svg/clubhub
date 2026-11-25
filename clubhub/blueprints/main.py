"""Trang tổng quan (dashboard), ma trận quyền, ERD."""
from datetime import datetime, timedelta

from flask import Blueprint, g, redirect, render_template, url_for

from ..auth import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, can, login_required
from ..db import query, scalar

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard") if g.user else url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    now = datetime.now()
    now_s = now.strftime("%Y-%m-%d %H:%M")
    stats = {
        "members": scalar("SELECT COUNT(*) FROM members WHERE is_active=1"),
        "departments": scalar("SELECT COUNT(*) FROM departments"),
        "upcoming": scalar("SELECT COUNT(*) FROM events WHERE start_time >= ?", (now_s,)),
        "my_tasks": scalar("SELECT COUNT(*) FROM tasks WHERE assignee_id=? AND status!='done'", (g.user["id"],)),
    }
    if can("fund.view"):
        stats["balance"] = scalar(
            "SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END),0) FROM funds")

    upcoming = query("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS reg_count,
                        EXISTS(SELECT 1 FROM registrations r WHERE r.event_id=e.id AND r.member_id=?) AS registered
                        FROM events e WHERE end_time >= ? ORDER BY start_time LIMIT 4""",
                     (g.user["id"], now_s))
    my_tasks = query("""SELECT * FROM tasks WHERE assignee_id=? AND status!='done'
                        ORDER BY deadline IS NULL, deadline LIMIT 5""", (g.user["id"],))
    news = query("""SELECT a.*, m.full_name AS author FROM announcements a LEFT JOIN members m ON m.id=a.author_id
                    WHERE a.department_id IS NULL OR a.department_id=?
                    ORDER BY a.is_pinned DESC, a.created_at DESC LIMIT 4""", (g.user["department_id"],))

    # Biểu đồ: tỷ lệ điểm danh các sự kiện đã diễn ra
    att = query("""SELECT e.title, COUNT(r.id) AS reg, COUNT(r.checked_in_at) AS att
                   FROM events e LEFT JOIN registrations r ON r.event_id=e.id
                   WHERE e.start_time < ? GROUP BY e.id ORDER BY e.start_time DESC LIMIT 6""", (now_s,))
    att = list(reversed(att))
    chart_att = {"labels": [a["title"] for a in att], "reg": [a["reg"] for a in att],
                 "att": [a["att"] for a in att]}

    # Biểu đồ: thu chi 6 tháng
    chart_fund = None
    if can("fund.view"):
        months = []
        d = now.replace(day=1)
        for _ in range(6):
            months.append(d.strftime("%Y-%m"))
            d = (d - timedelta(days=1)).replace(day=1)
        months.reverse()
        rows = {r["ym"]: r for r in query(
            """SELECT substr(txn_date,1,7) AS ym,
                      SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS inc,
                      SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS exp
               FROM funds GROUP BY ym""")}
        chart_fund = {"labels": [m[5:] + "/" + m[:4] for m in months],
                      "inc": [rows[m]["inc"] if m in rows else 0 for m in months],
                      "exp": [rows[m]["exp"] if m in rows else 0 for m in months]}

    dept_chart = query("""SELECT d.name, COUNT(m.id) AS n FROM departments d
                          LEFT JOIN members m ON m.department_id=d.id AND m.is_active=1
                          GROUP BY d.id ORDER BY d.id""")
    return render_template("dashboard.html", stats=stats, upcoming=upcoming, my_tasks=my_tasks, news=news,
                           chart_att=chart_att, chart_fund=chart_fund,
                           chart_dept={"labels": [r["name"] for r in dept_chart], "data": [r["n"] for r in dept_chart]})


@bp.route("/permissions")
@login_required
def permissions():
    return render_template("permissions.html", PERMISSIONS=PERMISSIONS, ROLE_PERMISSIONS=ROLE_PERMISSIONS,
                           roles=list(ROLE_LABELS))


@bp.route("/erd")
@login_required
def erd():
    return render_template("erd.html")
