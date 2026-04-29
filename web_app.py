import sqlite3
from datetime import datetime
from urllib.parse import urlencode as _urlencode

import pandas as pd
from flask import Flask, Response, abort, g, render_template, request

from config import DB_PATH, WEB_PORT, WEB_SECRET
from storage import INVOICE_COLUMNS

app = Flask(__name__)

if not WEB_SECRET:
    raise RuntimeError("WEB_SECRET is not set — refusing to start")


@app.template_filter("urlencode")
def urlencode_filter(mapping):
    return _urlencode(
        {k: v for k, v in mapping.items() if k not in ("page", "secret")}
    )


@app.before_request
def check_secret():
    if request.args.get("secret") != WEB_SECRET:
        abort(403)


def _get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _build_where(args):
    conditions, params = [], []
    if args.get("from_date"):
        conditions.append("issue_date >= ?")
        params.append(args["from_date"])
    if args.get("to_date"):
        conditions.append("issue_date <= ?")
        params.append(args["to_date"])
    if args.get("invoice_type") and args["invoice_type"] != "ALL":
        conditions.append("invoice_type = ?")
        params.append(args["invoice_type"])
    if args.get("search"):
        conditions.append(
            "(seller_name LIKE ? OR buyer_name LIKE ? OR invoice_number LIKE ?)"
        )
        term = f"%{args['search']}%"
        params.extend([term, term, term])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


@app.route("/")
def index():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    where, params = _build_where(request.args)

    db = _get_db()
    total = db.execute(f"SELECT COUNT(*) FROM invoices {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM invoices {where} ORDER BY processed_date DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "index.html",
        rows=rows,
        columns=INVOICE_COLUMNS,
        page=page,
        total_pages=total_pages,
        total=total,
        args=request.args,
        secret=WEB_SECRET,
    )


@app.route("/export")
def export():
    where, params = _build_where(request.args)
    requested = request.args.get("columns", "")
    cols = (
        [c for c in requested.split(",") if c in INVOICE_COLUMNS]
        if requested
        else INVOICE_COLUMNS
    )

    db = _get_db()
    col_sql = ", ".join(f'"{c}"' for c in cols)
    rows = db.execute(
        f"SELECT {col_sql} FROM invoices {where}", params
    ).fetchall()

    lines = [",".join(cols)]
    for row in rows:
        lines.append(",".join(f'"{str(v or "").replace(chr(34), chr(34)*2)}"' for v in row))

    date_str = datetime.now().strftime("%Y%m%d")
    return Response(
        "\n".join(lines),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=hoa_don_{date_str}.csv"
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False)
