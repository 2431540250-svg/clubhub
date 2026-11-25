"""Lớp truy cập dữ liệu SQLite (dùng thư viện chuẩn sqlite3).

Mỗi request mở 1 kết nối lưu trong flask.g, tự đóng khi request kết thúc.
"""
import os
import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        path = current_app.config["DATABASE"]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        g.db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """SELECT -> list[Row] (hoặc 1 Row nếu one=True)."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def scalar(sql, args=()):
    row = query(sql, args, one=True)
    return row[0] if row else None


def execute(sql, args=(), commit=True):
    """INSERT/UPDATE/DELETE -> lastrowid."""
    db = get_db()
    cur = db.execute(sql, args)
    if commit:
        db.commit()
    return cur.lastrowid


def init_db():
    from .models import SCHEMA
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def migrate_db():
    """Thêm cột/bảng mới vào CSDL đã có (không xóa dữ liệu)."""
    from .models import EXTRA_TABLES, MIGRATIONS
    db = get_db()
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'").fetchone():
        return
    for table, column, sql in MIGRATIONS:
        cols = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            db.execute(sql)
    db.executescript(EXTRA_TABLES)
    db.commit()


@click.command("init-db")
def init_db_command():
    """Tạo bảng (xóa dữ liệu cũ)."""
    init_db()
    click.echo("Đã khởi tạo CSDL.")


@click.command("seed")
def seed_command():
    """Tạo bảng + dữ liệu mẫu."""
    from .seed import seed
    init_db()
    seed()
    click.echo("Đã tạo dữ liệu mẫu. Đăng nhập: admin@club.vn / 123456")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)
