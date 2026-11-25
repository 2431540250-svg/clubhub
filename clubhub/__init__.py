"""ClubHub – Ứng dụng quản lý câu lạc bộ sinh viên có AI hỗ trợ vận hành."""
import os
from datetime import datetime

from flask import Flask, render_template

from .config import Config


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    from . import db
    db.init_app(app)

    # ---- Blueprints ----
    from .auth import bp as auth_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.members import bp as members_bp
    from .blueprints.events import bp as events_bp
    from .blueprints.finance import bp as finance_bp
    from .blueprints.tasks import bp as tasks_bp
    from .blueprints.announcements import bp as ann_bp
    from .blueprints.reports import bp as reports_bp
    from .blueprints.ai import bp as ai_bp
    for bp in (auth_bp, main_bp, members_bp, events_bp, finance_bp, tasks_bp, ann_bp, reports_bp, ai_bp):
        app.register_blueprint(bp)

    # ---- Biến/hàm dùng chung trong template ----
    from .auth import ROLE_LABELS, can
    from .ui import feedback, invalid
    from .models import TASK_PRIORITY, TASK_STATUS

    def unread_count():
        """Số thông báo chưa đọc của người đang đăng nhập (hiện ở menu)."""
        from flask import g
        from .db import scalar
        u = g.get("user")
        if not u:
            return 0
        return scalar("""SELECT COUNT(*) FROM announcements WHERE (department_id IS NULL OR department_id=?)
                         AND id > ? AND COALESCE(author_id, 0) != ?""",
                      (u["department_id"], u["announcements_seen_id"], u["id"]))

    @app.context_processor
    def inject_globals():
        logo = os.path.exists(os.path.join(app.static_folder, "img", "logo.png"))
        return dict(can=can, ROLE_LABELS=ROLE_LABELS, CLUB_NAME=app.config["CLUB_NAME"],
                    SCHOOL_NAME=app.config["SCHOOL_NAME"], HAS_LOGO=logo, invalid=invalid, feedback=feedback,
                    UNREAD=unread_count(),
                    TASK_STATUS=TASK_STATUS, TASK_PRIORITY=TASK_PRIORITY,
                    today=datetime.now().strftime("%Y-%m-%d"))

    @app.template_filter("money")
    def money(v):
        return f"{int(v or 0):,}".replace(",", ".") + " ₫"

    @app.template_filter("dt")
    def dt(v):
        """'2026-11-25 19:30' -> '25/11/2026 19:30'"""
        if not v:
            return ""
        s = str(v)
        try:
            if len(s) >= 16:
                return datetime.strptime(s[:16], "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return s

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, message="Bạn không có quyền truy cập chức năng này."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Không tìm thấy trang."), 404

    # ---- Tự tạo CSDL + dữ liệu mẫu lần chạy đầu (tiện khi deploy) ----
    if not test_config:
        with app.app_context():
            if os.environ.get("AUTO_SEED", "1") == "1" and not os.path.exists(app.config["DATABASE"]):
                db.init_db()
                from .seed import seed
                seed()
            elif os.path.exists(app.config["DATABASE"]):
                db.migrate_db()

    return app
