"""Tiện ích giao diện: báo lỗi theo từng ô nhập (tô đỏ ô sai) + phân trang."""
import math

from flask import flash, g, request, url_for
from markupsafe import Markup, escape


def field_error(field, message):
    """Ghi lỗi cho 1 ô nhập; template hiển thị bằng invalid()/feedback()."""
    if "field_errors" not in g:
        g.field_errors = {}
    g.field_errors.setdefault(field, message)


def form_failed(summary="Chưa lưu được – vui lòng sửa các ô tô đỏ."):
    if g.get("field_errors"):
        flash(summary, "danger")
        return True
    return False


def invalid(field):
    return " is-invalid" if field in g.get("field_errors", {}) else ""


def feedback(field):
    msg = g.get("field_errors", {}).get(field)
    return Markup(f'<div class="invalid-feedback d-block">{escape(msg)}</div>') if msg else ""


class Pagination:
    def __init__(self, total, page, per_page=20):
        self.total, self.per_page = total, per_page
        self.pages = max(1, math.ceil(total / per_page))
        self.page = min(max(1, page), self.pages)
        self.offset = (self.page - 1) * per_page

    def url(self, page):
        args = request.args.to_dict()
        args["page"] = page
        return url_for(request.endpoint, **request.view_args, **args)

    def window(self):
        """Các số trang hiển thị, None = dấu ..."""
        out, last = [], 0
        for p in range(1, self.pages + 1):
            if p in (1, self.pages) or abs(p - self.page) <= 2:
                if p - last > 1:
                    out.append(None)
                out.append(p)
                last = p
        return out
