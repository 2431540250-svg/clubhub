"""Task 3 – Lịch sự kiện, đăng ký, sinh QR, điểm danh, thống kê.

Hai cách điểm danh:
 1) Vé QR cá nhân: thành viên đăng ký -> nhận vé QR (mã ticket_code).
    Ban tổ chức mở trang "Quét QR" bằng camera điện thoại/laptop -> quét vé -> điểm danh.
 2) QR chung của sự kiện: BTC chiếu QR lên màn hình, thành viên tự quét bằng điện thoại
    -> mở link /checkin/<token> -> hệ thống điểm danh tài khoản đang đăng nhập.
"""
import csv
import io
import secrets
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from ..auth import has_permission, login_required, permission_required
from ..db import execute, query, scalar
from ..ui import field_error, form_failed

bp = Blueprint("events", __name__)
TICKET_PREFIX = "CLUBHUB:"
CHECKIN_AUTO, CHECKIN_OPEN, CHECKIN_CLOSED = 0, 1, 2
CHECKIN_EARLY_MIN = 30  # tự mở check-in trước giờ bắt đầu 30 phút


def checkin_state(e, now=None):
    """Trạng thái tự check-in thực tế: (đang_mở: bool, mô_tả: str).
    Mặc định (0) tự mở từ 30 phút trước giờ bắt đầu đến khi kết thúc – BTC không cần nhớ bấm."""
    now = now or datetime.now()
    mode = e["checkin_open"]
    if mode == CHECKIN_OPEN:
        return True, "Đang mở (BTC mở thủ công)"
    if mode == CHECKIN_CLOSED:
        return False, "Đã đóng (BTC đóng thủ công)"
    start = datetime.strptime(e["start_time"], "%Y-%m-%d %H:%M")
    end = datetime.strptime(e["end_time"], "%Y-%m-%d %H:%M")
    opens = start - timedelta(minutes=CHECKIN_EARLY_MIN)
    if now < opens:
        return False, f"Tự động mở lúc {opens:%H:%M %d/%m}"
    if now > end:
        return False, "Sự kiện đã kết thúc"
    return True, "Đang mở tự động theo giờ sự kiện"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _get_event(event_id):
    e = query("""SELECT e.*, d.name AS department_name, m.full_name AS creator_name,
                 (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS reg_count,
                 (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id AND r.checked_in_at IS NOT NULL)
                    AS att_count
                 FROM events e LEFT JOIN departments d ON d.id=e.department_id
                 LEFT JOIN members m ON m.id=e.created_by WHERE e.id=?""", (event_id,), one=True)
    if e is None:
        abort(404)
    return e


def _can_manage(event):
    """Admin/chủ nhiệm quản lý mọi sự kiện; trưởng ban chỉ sự kiện của ban mình hoặc do mình tạo."""
    if not has_permission(g.user, "event.manage"):
        return False
    if g.user["role_code"] == "head":
        return event["department_id"] == g.user["department_id"] or event["created_by"] == g.user["id"]
    return True


def _parse_dt(value):
    """input datetime-local '2026-11-25T19:30' -> '2026-11-25 19:30'"""
    return (value or "").replace("T", " ")[:16]


def do_checkin(event_id, member_id, method):
    """Điểm danh 1 thành viên. Trả về (status, message). status: ok | already | error"""
    reg = query("SELECT * FROM registrations WHERE event_id=? AND member_id=?", (event_id, member_id), one=True)
    if reg is None:  # chưa đăng ký -> đăng ký luôn (khách vãng lai)
        execute("INSERT INTO registrations(event_id, member_id, ticket_code) VALUES (?,?,?)",
                (event_id, member_id, secrets.token_hex(6).upper()))
        reg = query("SELECT * FROM registrations WHERE event_id=? AND member_id=?", (event_id, member_id), one=True)
    if reg["checked_in_at"]:
        return "already", f"Đã điểm danh trước đó lúc {reg['checked_in_at'][11:16]}"
    execute("UPDATE registrations SET checked_in_at=?, checkin_method=? WHERE id=?", (_now(), method, reg["id"]))
    return "ok", "Điểm danh thành công"


def _validate_event(f, start, end):
    if not f.get("title", "").strip():
        field_error("title", "Nhập tên sự kiện.")
    if not start:
        field_error("start_time", "Chọn thời gian bắt đầu.")
    if not end:
        field_error("end_time", "Chọn thời gian kết thúc.")
    elif start and end <= start:
        field_error("end_time", "Thời gian kết thúc phải sau thời gian bắt đầu.")
    if (f.get("capacity") or "0").strip().lstrip("-").isdigit() and int(f.get("capacity") or 0) < 0:
        field_error("capacity", "Số lượng không được âm.")
    return not form_failed()


# ------------------------------------------------------------------ Danh sách / CRUD
@bp.route("/events")
@login_required
def list_events():
    now = _now()
    sql = """SELECT e.*, d.name AS department_name,
             (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS reg_count,
             (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id AND r.checked_in_at IS NOT NULL) AS att_count,
             EXISTS(SELECT 1 FROM registrations r WHERE r.event_id=e.id AND r.member_id=?) AS registered
             FROM events e LEFT JOIN departments d ON d.id=e.department_id"""
    q = request.args.get("q", "").strip()
    dept = request.args.get("department", type=int)
    cond, extra = "", []
    if q:
        cond += " AND (e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)"
        extra += [f"%{q}%"] * 3
    if dept:
        cond += " AND e.department_id=?"
        extra.append(dept)
    if request.args.get("mine"):
        cond += " AND EXISTS(SELECT 1 FROM registrations r WHERE r.event_id=e.id AND r.member_id=?)"
        extra.append(g.user["id"])
    upcoming = query(sql + " WHERE e.end_time >= ?" + cond + " ORDER BY e.start_time", [g.user["id"], now] + extra)
    past = query(sql + " WHERE e.end_time < ?" + cond + " ORDER BY e.start_time DESC", [g.user["id"], now] + extra)
    return render_template("events/list.html", upcoming=upcoming, past=past, q=q, dept=dept,
                           mine=bool(request.args.get("mine")),
                           departments=query("SELECT * FROM departments ORDER BY name"))


@bp.route("/events/calendar.json")
@login_required
def calendar_json():
    rows = query("SELECT id, title, start_time, end_time FROM events")
    return jsonify([{"id": r["id"], "title": r["title"], "start": r["start_time"].replace(" ", "T"),
                     "end": r["end_time"].replace(" ", "T"),
                     "url": url_for("events.detail", event_id=r["id"])} for r in rows])


@bp.route("/events/new", methods=["GET", "POST"])
@permission_required("event.manage")
def create():
    if request.method == "POST":
        f = request.form
        start, end = _parse_dt(f.get("start_time")), _parse_dt(f.get("end_time"))
        if _validate_event(f, start, end):
            dept = f.get("department_id") or None
            if g.user["role_code"] == "head":
                dept = g.user["department_id"]
            eid = execute("""INSERT INTO events(title,description,location,start_time,end_time,capacity,
                             department_id,checkin_token,created_by) VALUES (?,?,?,?,?,?,?,?,?)""",
                          (f["title"].strip(), f.get("description"), f.get("location"), start, end,
                           f.get("capacity", type=int) or 0, dept, secrets.token_urlsafe(10), g.user["id"]))
            flash("Đã tạo sự kiện.", "success")
            return redirect(url_for("events.detail", event_id=eid))
    return render_template("events/form.html", e=None, departments=query("SELECT * FROM departments"))


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit(event_id):
    e = _get_event(event_id)
    if not _can_manage(e):
        abort(403)
    if request.method == "POST":
        f = request.form
        start, end = _parse_dt(f.get("start_time")), _parse_dt(f.get("end_time"))
        if _validate_event(f, start, end):
            dept = f.get("department_id") or None
            if g.user["role_code"] == "head":
                dept = e["department_id"]
            execute("""UPDATE events SET title=?, description=?, location=?, start_time=?, end_time=?, capacity=?,
                       department_id=? WHERE id=?""",
                    (f["title"].strip(), f.get("description"), f.get("location"), start, end,
                     f.get("capacity", type=int) or 0, dept, event_id))
            flash("Đã cập nhật sự kiện.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
    return render_template("events/form.html", e=e, departments=query("SELECT * FROM departments"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete(event_id):
    if not _can_manage(_get_event(event_id)):
        abort(403)
    execute("DELETE FROM events WHERE id=?", (event_id,))
    flash("Đã xóa sự kiện.", "info")
    return redirect(url_for("events.list_events"))


@bp.route("/events/<int:event_id>")
@login_required
def detail(event_id):
    e = _get_event(event_id)
    my_reg = query("SELECT * FROM registrations WHERE event_id=? AND member_id=?",
                   (event_id, g.user["id"]), one=True)
    manage = _can_manage(e)
    regs = []
    if manage or has_permission(g.user, "event.checkin"):
        regs = query("""SELECT r.*, m.full_name, m.student_id, d.name AS department_name
                        FROM registrations r JOIN members m ON m.id=r.member_id
                        LEFT JOIN departments d ON d.id=m.department_id
                        WHERE r.event_id=? ORDER BY r.checked_in_at IS NULL, r.checked_in_at DESC, m.full_name""",
                     (event_id,))
    is_open, state_label = checkin_state(e)
    return render_template("events/detail.html", e=e, my_reg=my_reg, regs=regs, manage=manage,
                           checkin_is_open=is_open, checkin_label=state_label,
                           ticket_prefix=TICKET_PREFIX, now=_now(),
                           self_checkin_url=url_for("events.self_checkin", token=e["checkin_token"], _external=True))


# ------------------------------------------------------------------ Đăng ký
@bp.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
def register(event_id):
    e = _get_event(event_id)
    if e["end_time"] < _now():
        flash("Sự kiện đã kết thúc.", "warning")
    elif e["capacity"] and e["reg_count"] >= e["capacity"]:
        flash("Sự kiện đã đủ số lượng.", "warning")
    elif query("SELECT 1 FROM registrations WHERE event_id=? AND member_id=?", (event_id, g.user["id"]), one=True):
        flash("Bạn đã đăng ký rồi.", "info")
    else:
        execute("INSERT INTO registrations(event_id, member_id, ticket_code) VALUES (?,?,?)",
                (event_id, g.user["id"], secrets.token_hex(6).upper()))
        flash("Đăng ký thành công! Vé QR của bạn ở bên dưới.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/unregister", methods=["POST"])
@login_required
def unregister(event_id):
    execute("DELETE FROM registrations WHERE event_id=? AND member_id=? AND checked_in_at IS NULL",
            (event_id, g.user["id"]))
    flash("Đã hủy đăng ký.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


# ------------------------------------------------------------------ Điểm danh
@bp.route("/events/<int:event_id>/checkin-mode", methods=["POST"])
@login_required
def set_checkin_mode(event_id):
    e = _get_event(event_id)
    if not _can_manage(e):
        abort(403)
    mode = request.form.get("mode", type=int)
    if mode not in (CHECKIN_AUTO, CHECKIN_OPEN, CHECKIN_CLOSED):
        abort(400)
    execute("UPDATE events SET checkin_open=? WHERE id=?", (mode, event_id))
    flash({CHECKIN_AUTO: f"Tự check-in sẽ tự mở {CHECKIN_EARLY_MIN} phút trước giờ bắt đầu.",
           CHECKIN_OPEN: "Đã mở tự check-in ngay bây giờ.", CHECKIN_CLOSED: "Đã đóng tự check-in."}[mode], "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/scan")
@permission_required("event.checkin")
def scan(event_id):
    return render_template("events/scan.html", e=_get_event(event_id), ticket_prefix=TICKET_PREFIX)


@bp.route("/events/<int:event_id>/checkin", methods=["POST"])
@permission_required("event.checkin")
def checkin_api(event_id):
    """API cho trang quét QR. Nhận {code}: mã vé (có/không tiền tố) hoặc MSSV (nhập tay)."""
    _get_event(event_id)
    data = request.get_json(silent=True) or request.form
    code = (data.get("code") or "").strip()
    if code.upper().startswith(TICKET_PREFIX):
        code = code[len(TICKET_PREFIX):]
    reg = query("""SELECT r.*, m.full_name, m.student_id FROM registrations r JOIN members m ON m.id=r.member_id
                   WHERE r.ticket_code=?""", (code.upper(),), one=True)
    method = "scan"
    if reg is None:
        member = query("SELECT id, full_name, student_id FROM members WHERE lower(student_id)=lower(?) AND is_active=1",
                       (code,), one=True)
        if member is None:
            return jsonify(status="error", message="Mã QR / MSSV không hợp lệ"), 404
        member_id, name, sid, method = member["id"], member["full_name"], member["student_id"], "manual"
    else:
        if reg["event_id"] != event_id:
            return jsonify(status="error", message="Vé này thuộc sự kiện khác"), 400
        member_id, name, sid = reg["member_id"], reg["full_name"], reg["student_id"]
    status, msg = do_checkin(event_id, member_id, method)
    att = scalar("SELECT COUNT(*) FROM registrations WHERE event_id=? AND checked_in_at IS NOT NULL", (event_id,))
    return jsonify(status=status, message=msg, name=name, student_id=sid, attended=att)


@bp.route("/checkin/<token>")
@login_required
def self_checkin(token):
    e = query("SELECT * FROM events WHERE checkin_token=?", (token,), one=True)
    if e is None:
        abort(404)
    is_open, label = checkin_state(e)
    if not is_open:
        status, msg = "error", f"Hiện chưa mở check-in cho sự kiện này ({label.lower()})."
    else:
        status, msg = do_checkin(e["id"], g.user["id"], "self")
    my_reg = query("SELECT * FROM registrations WHERE event_id=? AND member_id=?", (e["id"], g.user["id"]), one=True)
    return render_template("events/checkin_result.html", e=e, status=status, message=msg, my_reg=my_reg,
                           ticket_prefix=TICKET_PREFIX)


@bp.route("/events/<int:event_id>/attendance.csv")
@login_required
def export_attendance(event_id):
    e = _get_event(event_id)
    if not (_can_manage(e) or has_permission(g.user, "event.checkin")):
        abort(403)
    rows = query("""SELECT m.student_id, m.full_name, d.name, r.registered_at, r.checked_in_at, r.checkin_method
                    FROM registrations r JOIN members m ON m.id=r.member_id
                    LEFT JOIN departments d ON d.id=m.department_id WHERE r.event_id=? ORDER BY m.student_id""",
                 (event_id,))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["MSSV", "Họ tên", "Ban", "Đăng ký lúc", "Check-in lúc", "Hình thức"])
    for r in rows:
        w.writerow(list(r))
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=diem_danh_su_kien_{event_id}.csv"})


@bp.route("/events/stats")
@login_required
def stats():
    rows = query("""SELECT e.id, e.title, e.start_time, e.capacity, COUNT(r.id) AS reg, COUNT(r.checked_in_at) AS att
                    FROM events e LEFT JOIN registrations r ON r.event_id=e.id
                    WHERE e.start_time < ? GROUP BY e.id ORDER BY e.start_time""", (_now(),))
    top = query("""SELECT m.full_name, m.student_id, COUNT(r.checked_in_at) AS att
                   FROM members m JOIN registrations r ON r.member_id=m.id
                   GROUP BY m.id HAVING att > 0 ORDER BY att DESC, m.full_name LIMIT 10""")
    total_reg = sum(r["reg"] for r in rows)
    total_att = sum(r["att"] for r in rows)
    return render_template("events/stats.html", rows=rows, top=top, total_reg=total_reg, total_att=total_att)
