"""Tổng hợp báo cáo tháng + xuất Excel (openpyxl) / PDF (reportlab)."""
import io
import os
from calendar import monthrange
from datetime import datetime

from .db import query, scalar


def build_monthly_report(ym):
    """ym = 'YYYY-MM' -> dict dữ liệu báo cáo."""
    y, m = map(int, ym.split("-"))
    first = f"{ym}-01"
    last = f"{ym}-{monthrange(y, m)[1]:02d}"
    today = datetime.now().strftime("%Y-%m-%d")

    members_total = scalar("SELECT COUNT(*) FROM members WHERE is_active=1")
    members_new = scalar("SELECT COUNT(*) FROM members WHERE joined_at BETWEEN ? AND ?", (first, last))
    by_dept = query("""SELECT d.name, COUNT(m.id) AS n FROM departments d
                       LEFT JOIN members m ON m.department_id=d.id AND m.is_active=1 GROUP BY d.id ORDER BY d.name""")

    events = query("""SELECT e.title, e.start_time, e.location, COUNT(r.id) AS reg, COUNT(r.checked_in_at) AS att
                      FROM events e LEFT JOIN registrations r ON r.event_id=e.id
                      WHERE substr(e.start_time,1,7)=? GROUP BY e.id ORDER BY e.start_time""", (ym,))
    events = [dict(e, rate=round(e["att"] * 100 / e["reg"]) if e["reg"] else 0) for e in events]

    opening = scalar("SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END),0) FROM funds "
                     "WHERE txn_date < ?", (first,))
    txns = query("""SELECT f.txn_date, f.type, f.category, f.description, f.amount FROM funds f
                    WHERE substr(f.txn_date,1,7)=? ORDER BY f.txn_date""", (ym,))
    income = sum(t["amount"] for t in txns if t["type"] == "income")
    expense = sum(t["amount"] for t in txns if t["type"] == "expense")
    by_cat = query("""SELECT type, category, SUM(amount) AS total FROM funds WHERE substr(txn_date,1,7)=?
                      GROUP BY type, category ORDER BY type DESC, total DESC""", (ym,))

    tasks_created = scalar("SELECT COUNT(*) FROM tasks WHERE substr(created_at,1,7)=?", (ym,))
    tasks_done = scalar("SELECT COUNT(*) FROM tasks WHERE substr(completed_at,1,7)=?", (ym,))
    tasks_overdue = scalar("SELECT COUNT(*) FROM tasks WHERE status!='done' AND deadline < ?", (today,))
    task_dept = query("""SELECT d.name, COUNT(t.id) AS total, SUM(t.status='done') AS done
                         FROM departments d LEFT JOIN tasks t ON t.department_id=d.id
                         GROUP BY d.id ORDER BY d.name""")
    top = query("""SELECT m.full_name, COUNT(r.checked_in_at) AS att FROM registrations r
                   JOIN members m ON m.id=r.member_id JOIN events e ON e.id=r.event_id
                   WHERE substr(e.start_time,1,7)=? GROUP BY m.id HAVING att>0 ORDER BY att DESC LIMIT 5""", (ym,))
    return {
        "ym": ym, "label": f"{m:02d}/{y}", "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "members_total": members_total, "members_new": members_new, "by_dept": by_dept,
        "events": events, "event_reg": sum(e["reg"] for e in events), "event_att": sum(e["att"] for e in events),
        "opening": opening, "income": income, "expense": expense, "closing": opening + income - expense,
        "txns": txns, "by_cat": by_cat,
        "tasks_created": tasks_created, "tasks_done": tasks_done, "tasks_overdue": tasks_overdue,
        "task_dept": task_dept, "top": top,
    }


def _vnd(v):
    return f"{int(v or 0):,}".replace(",", ".")


# ------------------------------------------------------------------ Excel
def export_excel(r, club_name):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2563EB")
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def table(ws, start_row, headers, rows, money_cols=()):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=c, value=h)
            cell.font, cell.fill, cell.border = head_font, head_fill, border
            cell.alignment = Alignment(horizontal="center")
        for i, row in enumerate(rows, start_row + 1):
            for c, v in enumerate(row, 1):
                cell = ws.cell(row=i, column=c, value=v)
                cell.border = border
                if c in money_cols:
                    cell.number_format = '#,##0" ₫"'
        for c in range(1, len(headers) + 1):
            letter = ws.cell(row=start_row, column=c).column_letter
            width = max(len(str(ws.cell(row=x, column=c).value or "")) for x in range(start_row, start_row + len(rows) + 1))
            ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 0, min(width + 3, 50))
        return start_row + len(rows) + 2

    ws = wb.active
    ws.title = "Tổng quan"
    ws["A1"] = f"BÁO CÁO HOẠT ĐỘNG THÁNG {r['label']} – {club_name}"
    ws["A1"].font = Font(bold=True, size=14, color="1E3A8A")
    ws["A2"] = f"Ngày lập: {r['generated_at']}"
    summary = [
        ("Tổng thành viên", r["members_total"]), ("Thành viên mới trong tháng", r["members_new"]),
        ("Số sự kiện", len(r["events"])), ("Lượt đăng ký", r["event_reg"]), ("Lượt điểm danh", r["event_att"]),
        ("Tồn quỹ đầu kỳ", r["opening"]), ("Tổng thu", r["income"]), ("Tổng chi", r["expense"]),
        ("Tồn quỹ cuối kỳ", r["closing"]), ("Công việc tạo mới", r["tasks_created"]),
        ("Công việc hoàn thành", r["tasks_done"]), ("Công việc quá hạn (hiện tại)", r["tasks_overdue"]),
    ]
    nxt = table(ws, 4, ["Chỉ tiêu", "Giá trị"], summary)
    for row in ws.iter_rows(min_row=10, max_row=13, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = '#,##0" ₫"'
    table(ws, nxt, ["Ban", "Số thành viên"], [(d["name"], d["n"]) for d in r["by_dept"]])

    ws = wb.create_sheet("Sự kiện")
    table(ws, 1, ["Sự kiện", "Thời gian", "Địa điểm", "Đăng ký", "Điểm danh", "Tỷ lệ (%)"],
          [(e["title"], e["start_time"], e["location"], e["reg"], e["att"], e["rate"]) for e in r["events"]])

    ws = wb.create_sheet("Thu chi")
    nxt = table(ws, 1, ["Ngày", "Loại", "Danh mục", "Diễn giải", "Số tiền"],
                [(t["txn_date"], "Thu" if t["type"] == "income" else "Chi", t["category"], t["description"],
                  t["amount"]) for t in r["txns"]], money_cols=(5,))
    table(ws, nxt, ["Loại", "Danh mục", "Tổng"],
          [("Thu" if c["type"] == "income" else "Chi", c["category"], c["total"]) for c in r["by_cat"]],
          money_cols=(3,))

    ws = wb.create_sheet("Công việc")
    table(ws, 1, ["Ban", "Tổng việc", "Hoàn thành", "Tỷ lệ (%)"],
          [(d["name"], d["total"], d["done"] or 0,
            round((d["done"] or 0) * 100 / d["total"]) if d["total"] else 0) for d in r["task_dept"]])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ------------------------------------------------------------------ PDF
def export_pdf(r, club_name):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Font DejaVu hỗ trợ tiếng Việt có dấu (Helvetica mặc định thì không)
    font_dir = os.path.join(os.path.dirname(__file__), "static", "fonts")
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(font_dir, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(font_dir, "DejaVuSans-Bold.ttf")))

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="DejaVu-Bold", fontSize=16, textColor=colors.HexColor("#1E3A8A"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="DejaVu-Bold", fontSize=12, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="DejaVu", fontSize=9.5, leading=13)

    def tbl(data, widths):
        data = [[Paragraph(str(c), body) for c in row] for row in data]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=f"Báo cáo tháng {r['label']}")
    s = [Paragraph(f"BÁO CÁO HOẠT ĐỘNG THÁNG {r['label']}", h1),
         Paragraph(f"{club_name} — lập lúc {r['generated_at']}", body), Spacer(1, 8)]

    s.append(Paragraph("1. Tổng quan", h2))
    s.append(tbl([["Chỉ tiêu", "Giá trị", "Chỉ tiêu", "Giá trị"],
                  ["Tổng thành viên", r["members_total"], "Thành viên mới", r["members_new"]],
                  ["Số sự kiện", len(r["events"]), "Lượt điểm danh / đăng ký", f"{r['event_att']} / {r['event_reg']}"],
                  ["Việc hoàn thành", r["tasks_done"], "Việc quá hạn", r["tasks_overdue"]]],
                 [4.5 * cm, 3.5 * cm, 5 * cm, 4.4 * cm]))

    s.append(Paragraph("2. Sự kiện trong tháng", h2))
    if r["events"]:
        s.append(tbl([["Sự kiện", "Thời gian", "Đăng ký", "Điểm danh", "Tỷ lệ"]] +
                     [[e["title"], e["start_time"], e["reg"], e["att"], f"{e['rate']}%"] for e in r["events"]],
                     [6.5 * cm, 3.6 * cm, 2.3 * cm, 2.5 * cm, 2.5 * cm]))
    else:
        s.append(Paragraph("Không có sự kiện.", body))

    s.append(Paragraph("3. Tài chính", h2))
    s.append(tbl([["Tồn đầu kỳ", "Tổng thu", "Tổng chi", "Tồn cuối kỳ"],
                  [_vnd(r["opening"]), _vnd(r["income"]), _vnd(r["expense"]), _vnd(r["closing"])]],
                 [4.35 * cm] * 4))
    if r["txns"]:
        s.append(Spacer(1, 6))
        s.append(tbl([["Ngày", "Loại", "Danh mục", "Diễn giải", "Số tiền (₫)"]] +
                     [[t["txn_date"], "Thu" if t["type"] == "income" else "Chi", t["category"],
                       t["description"] or "", _vnd(t["amount"])] for t in r["txns"]],
                     [2.4 * cm, 1.3 * cm, 3.8 * cm, 6.4 * cm, 3.5 * cm]))

    s.append(Paragraph("4. Công việc theo ban", h2))
    s.append(tbl([["Ban", "Tổng việc", "Hoàn thành", "Tỷ lệ"]] +
                 [[d["name"], d["total"], d["done"] or 0,
                   f"{round((d['done'] or 0) * 100 / d['total']) if d['total'] else 0}%"] for d in r["task_dept"]],
                 [7 * cm, 3.4 * cm, 3.4 * cm, 3.6 * cm]))
    if r["top"]:
        s.append(Paragraph("5. Thành viên tích cực", h2))
        s.append(Paragraph(", ".join(f"{t['full_name']} ({t['att']} sự kiện)" for t in r["top"]), body))
    doc.build(s)
    buf.seek(0)
    return buf
