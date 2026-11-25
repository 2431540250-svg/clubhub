"""Task 4a – Sổ quỹ thu chi."""
import csv
import io
from datetime import datetime

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template,
                   request, url_for)

from ..auth import permission_required
from ..db import execute, query
from ..ui import field_error, form_failed
from ..models import EXPENSE_CATEGORIES, FUND_TYPE, INCOME_CATEGORIES

bp = Blueprint("finance", __name__, url_prefix="/finance")


def _filters():
    return dict(month=request.args.get("month", ""), type=request.args.get("type", ""),
                category=request.args.get("category", ""))


def _where(f):
    sql, args = " WHERE 1=1", []
    if f["month"]:
        sql += " AND substr(f.txn_date,1,7)=?"
        args.append(f["month"])
    if f["type"] in FUND_TYPE:
        sql += " AND f.type=?"
        args.append(f["type"])
    if f["category"]:
        sql += " AND f.category=?"
        args.append(f["category"])
    return sql, args


@bp.route("/")
@permission_required("fund.view")
def ledger():
    f = _filters()
    where, args = _where(f)
    rows = query("""SELECT f.*, e.title AS event_title, m.full_name AS creator FROM funds f
                    LEFT JOIN events e ON e.id=f.event_id LEFT JOIN members m ON m.id=f.created_by""" + where +
                 " ORDER BY f.txn_date DESC, f.id DESC", args)
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    balance = query("SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END),0) AS b FROM funds",
                    one=True)["b"]
    by_cat = query("SELECT f.category, SUM(f.amount) AS total FROM funds f" + where +
                   " AND f.type='expense' GROUP BY f.category ORDER BY total DESC", args)
    months = [r["m"] for r in query("SELECT DISTINCT substr(txn_date,1,7) AS m FROM funds ORDER BY m DESC")]
    return render_template("finance/ledger.html", rows=rows, income=income, expense=expense, balance=balance,
                           filters=f, months=months, by_cat=by_cat,
                           categories=sorted(set(INCOME_CATEGORIES + EXPENSE_CATEGORIES)))


def _form_ctx(t=None):
    return dict(t=t, income_cats=INCOME_CATEGORIES, expense_cats=EXPENSE_CATEGORIES,
                events=query("SELECT id, title FROM events ORDER BY start_time DESC"))


def _save(form, txn_id=None):
    try:
        amount = int(str(form.get("amount", "0")).replace(".", "").replace(",", ""))
    except ValueError:
        amount = 0
    ftype = form.get("type")
    date = form.get("txn_date") or datetime.now().strftime("%Y-%m-%d")
    if ftype not in FUND_TYPE:
        field_error("type", "Chọn khoản thu hoặc khoản chi.")
    if amount <= 0:
        field_error("amount", "Số tiền phải lớn hơn 0 (nhập số, vd: 150000).")
    if not form.get("category"):
        field_error("category", "Chọn danh mục.")
    if form_failed():
        return False
    vals = (ftype, amount, form["category"], form.get("description"), date, form.get("event_id") or None)
    if txn_id:
        execute("UPDATE funds SET type=?, amount=?, category=?, description=?, txn_date=?, event_id=? WHERE id=?",
                vals + (txn_id,))
    else:
        execute("INSERT INTO funds(type,amount,category,description,txn_date,event_id,created_by) "
                "VALUES (?,?,?,?,?,?,?)", vals + (g.user["id"],))
    flash("Đã lưu giao dịch.", "success")
    return True


@bp.route("/new", methods=["GET", "POST"])
@permission_required("fund.manage")
def create():
    if request.method == "POST" and _save(request.form):
        return redirect(url_for("finance.ledger"))
    return render_template("finance/form.html", **_form_ctx())


@bp.route("/<int:txn_id>/edit", methods=["GET", "POST"])
@permission_required("fund.manage")
def edit(txn_id):
    t = query("SELECT * FROM funds WHERE id=?", (txn_id,), one=True)
    if t is None:
        abort(404)
    if request.method == "POST" and _save(request.form, txn_id):
        return redirect(url_for("finance.ledger"))
    return render_template("finance/form.html", **_form_ctx(t))


@bp.route("/<int:txn_id>/delete", methods=["POST"])
@permission_required("fund.manage")
def delete(txn_id):
    execute("DELETE FROM funds WHERE id=?", (txn_id,))
    flash("Đã xóa giao dịch.", "info")
    return redirect(url_for("finance.ledger"))


@bp.route("/export.csv")
@permission_required("fund.view")
def export_csv():
    f = _filters()
    where, args = _where(f)
    rows = query("SELECT f.txn_date, f.type, f.category, f.description, f.amount, e.title FROM funds f "
                 "LEFT JOIN events e ON e.id=f.event_id" + where + " ORDER BY f.txn_date", args)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ngày", "Loại", "Danh mục", "Diễn giải", "Số tiền", "Sự kiện"])
    for r in rows:
        w.writerow([r[0], FUND_TYPE[r[1]], r[2], r[3], r[4], r[5] or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=so_thu_chi.csv"})
