"""Task 5 – Giao diện trợ lý AI + quy trình "AI soạn nháp -> người duyệt -> công bố"."""
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .. import ai_service
from ..auth import has_permission, is_dept_scoped, permission_required
from ..db import execute, query

bp = Blueprint("ai", __name__, url_prefix="/ai")

KIND_LABEL = {"announcement": "Thông báo", "minutes": "Tóm tắt biên bản"}


@bp.route("/")
@permission_required("ai.use")
def hub():
    drafts = query("""SELECT a.*, m.full_name AS creator, r.full_name AS reviewer FROM ai_drafts a
                      LEFT JOIN members m ON m.id=a.created_by LEFT JOIN members r ON r.id=a.reviewed_by
                      ORDER BY a.status='draft' DESC, a.created_at DESC LIMIT 20""")
    meetings = query("SELECT * FROM meetings ORDER BY meeting_date DESC LIMIT 10")
    return render_template("ai/hub.html", drafts=drafts, meetings=meetings, provider=ai_service.provider_name(),
                           KIND_LABEL=KIND_LABEL, departments=query("SELECT * FROM departments ORDER BY name"))


# ------------------------------------------------------------------ 1. Nháp thông báo
@bp.route("/announcement", methods=["POST"])
@permission_required("ai.use")
def gen_announcement():
    topic = request.form.get("topic", "").strip()
    if not topic:
        flash("Nhập chủ đề thông báo.", "danger")
        return redirect(url_for("ai.hub"))
    details = request.form.get("details", "")
    text, provider = ai_service.draft_announcement(
        topic, details, request.form.get("audience") or "toàn thể thành viên",
        request.form.get("tone", "friendly"), current_app.config["CLUB_NAME"])
    did = execute("INSERT INTO ai_drafts(kind,title,input_text,output_text,provider,created_by) VALUES (?,?,?,?,?,?)",
                  ("announcement", topic, f"Chủ đề: {topic}\n{details}", text, provider, g.user["id"]))
    return redirect(url_for("ai.review", draft_id=did))


# ------------------------------------------------------------------ 2. Tóm tắt biên bản
@bp.route("/minutes", methods=["POST"])
@permission_required("ai.use")
def gen_minutes():
    notes = request.form.get("notes", "").strip()
    if len(notes) < 20:
        flash("Biên bản quá ngắn để tóm tắt.", "danger")
        return redirect(url_for("ai.hub"))
    title = request.form.get("title") or f"Họp ngày {datetime.now():%d/%m/%Y}"
    text, provider = ai_service.summarize_minutes(notes)
    did = execute("INSERT INTO ai_drafts(kind,title,input_text,output_text,provider,created_by) VALUES (?,?,?,?,?,?)",
                  ("minutes", title, notes, text, provider, g.user["id"]))
    return redirect(url_for("ai.review", draft_id=did))


# ------------------------------------------------------------------ Duyệt bản nháp
def _get_draft(draft_id):
    d = query("""SELECT a.*, m.full_name AS creator FROM ai_drafts a LEFT JOIN members m ON m.id=a.created_by
                 WHERE a.id=?""", (draft_id,), one=True)
    if d is None:
        abort(404)
    return d


@bp.route("/drafts/<int:draft_id>", methods=["GET", "POST"])
@permission_required("ai.use")
def review(draft_id):
    d = _get_draft(draft_id)
    if request.method == "POST":
        action = request.form.get("action")
        output = request.form.get("output_text", d["output_text"]).strip()
        title = request.form.get("title", d["title"]).strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if d["status"] != "draft":
            flash("Bản nháp này đã được xử lý.", "warning")
        elif action == "save":
            execute("UPDATE ai_drafts SET output_text=?, title=? WHERE id=?", (output, title, draft_id))
            flash("Đã lưu chỉnh sửa. Chờ Chủ nhiệm duyệt.", "success")
        elif action in ("approve", "reject"):
            if not has_permission(g.user, "ai.approve"):
                abort(403)
            if action == "reject":
                execute("UPDATE ai_drafts SET status='rejected', reviewed_by=?, reviewed_at=? WHERE id=?",
                        (g.user["id"], now, draft_id))
                flash("Đã từ chối bản nháp.", "info")
                return redirect(url_for("ai.hub"))
            execute("UPDATE ai_drafts SET status='approved', output_text=?, title=?, reviewed_by=?, reviewed_at=? "
                    "WHERE id=?", (output, title, g.user["id"], now, draft_id))
            if d["kind"] == "announcement":
                # Dòng đầu của bản nháp là tiêu đề (nếu ngắn), phần còn lại là nội dung
                lines = output.splitlines()
                if len(lines) > 1 and 0 < len(lines[0].strip()) < 150:
                    ann_title, content = lines[0].strip(), "\n".join(lines[1:]).strip()
                else:
                    ann_title, content = title, output
                dept = request.form.get("department_id", type=int) or None
                execute("INSERT INTO announcements(title,content,department_id,author_id,is_ai_generated) "
                        "VALUES (?,?,?,?,1)", (ann_title, content or output, dept, g.user["id"]))
                flash("Đã duyệt và đăng thông báo.", "success")
                return redirect(url_for("announcements.list_all"))
            mid = execute("INSERT INTO meetings(title,meeting_date,raw_notes,summary,created_by) VALUES (?,?,?,?,?)",
                          (title, request.form.get("meeting_date") or now[:10], d["input_text"], output, g.user["id"]))
            flash("Đã duyệt và lưu biên bản.", "success")
            return redirect(url_for("ai.meeting", meeting_id=mid))
        return redirect(url_for("ai.review", draft_id=draft_id))
    return render_template("ai/review.html", d=d, KIND_LABEL=KIND_LABEL,
                           departments=query("SELECT * FROM departments ORDER BY name"))


@bp.route("/meetings/<int:meeting_id>")
@permission_required("ai.use")
def meeting(meeting_id):
    m = query("SELECT * FROM meetings WHERE id=?", (meeting_id,), one=True)
    if m is None:
        abort(404)
    return render_template("ai/meeting.html", m=m)


# ------------------------------------------------------------------ 3. Đề xuất phân công
@bp.route("/assign", methods=["GET", "POST"])
@permission_required("ai.use")
def assign():
    cands = explanation = provider = None
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        dept = request.form.get("department_id", type=int)
        if is_dept_scoped(g.user):
            dept = g.user["department_id"]
        cands, explanation, provider = ai_service.suggest_assignment(
            request.form.get("title", ""), request.form.get("description", ""), dept)
    return render_template("ai/assign.html", cands=cands, explanation=explanation, provider=provider, form=form,
                           departments=query("SELECT * FROM departments ORDER BY name"))


# ------------------------------------------------------------------ 4. Thành viên ít tương tác
@bp.route("/engagement")
@permission_required("ai.use")
def engagement():
    days = request.args.get("days", 90, type=int)
    rows = ai_service.engagement_report(days)
    if is_dept_scoped(g.user):
        rows = [r for r in rows if r["department_id"] == g.user["department_id"]]
    show = request.args.get("show", "flagged")
    summary = {lv: sum(1 for r in rows if r["level"] == lv) for lv in ("low", "watch", "ok")}
    if show == "flagged":
        rows = [r for r in rows if r["level"] != "ok"]
    return render_template("ai/engagement.html", rows=rows, summary=summary, days=days, show=show)


@bp.route("/engagement/<int:member_id>/message", methods=["POST"])
@permission_required("ai.use")
def engagement_message(member_id):
    m = query("SELECT full_name FROM members WHERE id=?", (member_id,), one=True)
    if m is None:
        abort(404)
    reasons = request.get_json(silent=True, force=True) or {}
    text, provider = ai_service.checkin_message(m["full_name"], reasons.get("reasons", []),
                                                current_app.config["CLUB_NAME"])
    return jsonify(text=text, provider=provider)
