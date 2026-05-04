import sqlite3
from datetime import datetime
from urllib.parse import urlencode as _urlencode

import pandas as pd
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, url_for

import data_extractor
import file_storage
import storage as _storage
from config import DB_PATH, MANUAL_SECRET, WEB_PORT, WEB_SECRET
from storage import INVOICE_COLUMNS

app = Flask(__name__)
app.secret_key = WEB_SECRET or "dev"

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


# ── Manual Upload ──────────────────────────────────────────────────────────

_ALLOWED_XML_MAGIC = (b"<?xml", b"\xef\xbb\xbf<?xml")  # UTF-8 BOM variant
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB hard cap


def _validate_xml_bytes(data: bytes) -> bool:
    """True only if the content starts with an XML declaration or root element."""
    stripped = data.lstrip()  # skip BOM / whitespace
    return stripped.startswith(b"<?xml") or stripped.startswith(b"<")


def _validate_pdf_bytes(data: bytes) -> bool:
    """True only if the content has the %PDF magic header."""
    return data[:4] == b"%PDF"


def _process_manual_invoice(xml_bytes: bytes | None, pdf_bytes: bytes | None) -> dict:
    """Validate, parse, check DB, upload to MinIO, save or update invoice. Returns result dict."""
    try:
        # ── Server-side content validation (magic bytes) ─────────────────
        if xml_bytes is not None and not _validate_xml_bytes(xml_bytes):
            return {"inv": "?", "status": "error", "detail": "File XML không hợp lệ (sai định dạng)"}
        if pdf_bytes is not None and not _validate_pdf_bytes(pdf_bytes):
            return {"inv": "?", "status": "error", "detail": "File PDF không hợp lệ (sai định dạng)"}

        if xml_bytes:
            data = data_extractor.parse_xml(xml_bytes)
            branch = "MANUAL_XML"
        elif pdf_bytes:
            data = data_extractor.parse_pdf_via_gemini(pdf_bytes)
            branch = "MANUAL_PDF"
        else:
            return {"inv": "—", "status": "skipped", "detail": "Không có file nào được chọn"}

        inv_num = str(data.get("invoice_number") or "unknown")
        tax_code = str(data.get("seller_tax_code") or "unknown")
        date_str = datetime.now().strftime("%Y%m%d")

        db = _get_db()
        existing = db.execute(
            "SELECT invoice_number, pdf_file_link, xml_file_link FROM invoices "
            "WHERE invoice_number = ? AND seller_tax_code = ?",
            [inv_num, tax_code],
        ).fetchone()

        if existing:
            # Invoice exists — only upload files that are currently missing
            updates: dict[str, str] = {}
            if xml_bytes and not existing["xml_file_link"]:
                updates["xml_link"] = file_storage.upload_file(
                    xml_bytes,
                    file_storage.build_filename(tax_code, inv_num, date_str, "xml"),
                    "application/xml",
                )
            if pdf_bytes and not existing["pdf_file_link"]:
                updates["pdf_link"] = file_storage.upload_file(
                    pdf_bytes,
                    file_storage.build_filename(tax_code, inv_num, date_str, "pdf"),
                    "application/pdf",
                )
            if updates:
                _storage.update_file_link(
                    inv_num, tax_code,
                    pdf_link=updates.get("pdf_link"),
                    xml_link=updates.get("xml_link"),
                )
                return {
                    "inv": inv_num,
                    "status": "updated",
                    "detail": f"Bổ sung: {', '.join(updates.keys())}",
                }
            return {"inv": inv_num, "status": "skipped", "detail": "Hóa đơn đã tồn tại và đủ file"}

        # New invoice — upload all available files then save
        xml_link = ""
        pdf_link = ""
        if xml_bytes:
            xml_link = file_storage.upload_file(
                xml_bytes,
                file_storage.build_filename(tax_code, inv_num, date_str, "xml"),
                "application/xml",
            )
        if pdf_bytes:
            pdf_link = file_storage.upload_file(
                pdf_bytes,
                file_storage.build_filename(tax_code, inv_num, date_str, "pdf"),
                "application/pdf",
            )

        data["xml_file_link"] = xml_link
        data["pdf_file_link"] = pdf_link
        data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["source_branch"] = branch
        data["source_email_subject"] = "MANUAL UPLOAD"
        _storage.append_invoice(data)
        return {"inv": inv_num, "status": "created", "detail": "Đã thêm mới"}

    except Exception as exc:
        return {"inv": "?", "status": "error", "detail": str(exc)}


@app.route("/manual", methods=["GET"])
def manual_get():
    return render_template("manual.html", secret=WEB_SECRET)


@app.route("/manual", methods=["POST"])
def manual_post():
    # Secondary confirmation: user must type the manual secret code in the form
    if request.form.get("input_secret") != MANUAL_SECRET:
        return render_template(
            "manual.html",
            secret=WEB_SECRET,
            error="Sai mã bí mật. Vui lòng thử lại.",
        )

    results = []
    i = 1
    while True:
        xml_file = request.files.get(f"xml_{i}")
        pdf_file = request.files.get(f"pdf_{i}")
        # Stop when neither field name exists in the submitted form
        if f"xml_{i}" not in request.files and f"pdf_{i}" not in request.files:
            break

        # ── Extension check (server-side, browser accept is advisory only) ──
        def _safe_read(f, allowed_ext: str) -> bytes | None:
            if not f or not f.filename:
                return None
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext != allowed_ext:
                return None  # wrong extension — treat as not provided
            data = f.read(_MAX_FILE_BYTES + 1)
            if len(data) > _MAX_FILE_BYTES:
                return b""  # sentinel: too large (handled below)
            return data or None

        xml_bytes = _safe_read(xml_file, "xml")
        pdf_bytes = _safe_read(pdf_file, "pdf")

        # Reject oversized files
        if xml_bytes == b"" or pdf_bytes == b"":
            results.append({"inv": "?", "status": "error",
                            "detail": f"File vượt quá giới hạn {_MAX_FILE_BYTES // (1024*1024)} MB"})
            i += 1
            continue

        if xml_bytes or pdf_bytes:
            results.append(_process_manual_invoice(xml_bytes, pdf_bytes))
        i += 1

    return render_template("manual.html", secret=WEB_SECRET, results=results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False)
