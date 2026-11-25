"""Task 4d – Báo cáo tháng & xuất file."""
import re
from datetime import datetime

from flask import Blueprint, abort, current_app, render_template, request, send_file

from ..auth import permission_required
from ..reports import build_monthly_report, export_excel, export_pdf

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _month():
    ym = request.args.get("month") or datetime.now().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", ym):
        abort(400)
    return ym


@bp.route("/")
@permission_required("report.view")
def monthly():
    ym = _month()
    return render_template("reports/monthly.html", r=build_monthly_report(ym))


@bp.route("/export.xlsx")
@permission_required("report.view")
def export_xlsx():
    ym = _month()
    buf = export_excel(build_monthly_report(ym), current_app.config["CLUB_NAME"])
    return send_file(buf, as_attachment=True, download_name=f"bao_cao_{ym}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/export.pdf")
@permission_required("report.view")
def export_pdf_view():
    ym = _month()
    buf = export_pdf(build_monthly_report(ym), current_app.config["CLUB_NAME"])
    return send_file(buf, as_attachment=True, download_name=f"bao_cao_{ym}.pdf", mimetype="application/pdf")
