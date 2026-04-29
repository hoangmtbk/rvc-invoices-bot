import logging
import sqlite3

from config import DB_PATH

logger = logging.getLogger(__name__)

INVOICE_COLUMNS = [
    "invoice_type", "invoice_symbol", "invoice_number",
    "issue_date", "seller_name", "seller_tax_code",
    "buyer_name", "buyer_tax_code",
    "contract_number", "customer_code",
    "description", "total_before_tax",
    "vat_rate", "total_vat_amount", "total_after_tax",
    "lookup_code", "lookup_website",
    "pdf_file_link", "xml_file_link",
    "source_branch", "source_email_subject", "processed_date",
]

ERROR_COLUMNS = [
    "error_date", "email_sender", "email_time", "email_subject",
    "branch", "error_message",
]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables() -> None:
    col_defs = ", ".join(f'"{c}" TEXT' for c in INVOICE_COLUMNS)
    err_defs = ", ".join(f'"{c}" TEXT' for c in ERROR_COLUMNS)
    with _get_conn() as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS invoices (
                {col_defs},
                PRIMARY KEY (invoice_number, seller_tax_code)
            )"""
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS errors ({err_defs})"
        )


def append_invoice(data: dict) -> None:
    _ensure_tables()
    row = {col: str(data.get(col, "") or "") for col in INVOICE_COLUMNS}
    placeholders = ", ".join("?" * len(INVOICE_COLUMNS))
    cols = ", ".join(f'"{c}"' for c in INVOICE_COLUMNS)
    inserted = False
    with _get_conn() as conn:
        cursor = conn.execute(
            f"INSERT OR IGNORE INTO invoices ({cols}) VALUES ({placeholders})",
            [row[c] for c in INVOICE_COLUMNS],
        )
        if cursor.rowcount == 0:
            logger.warning(
                f"Duplicate invoice skipped: {data.get('invoice_number')} | "
                f"seller_tax={data.get('seller_tax_code')}"
            )
        else:
            inserted = True
    if inserted:
        logger.info(f"Invoice saved: {data.get('invoice_number')} | {data.get('invoice_type')}")


def append_error(data: dict) -> None:
    _ensure_tables()
    row = {col: str(data.get(col, "") or "") for col in ERROR_COLUMNS}
    placeholders = ", ".join("?" * len(ERROR_COLUMNS))
    cols = ", ".join(f'"{c}"' for c in ERROR_COLUMNS)
    with _get_conn() as conn:
        conn.execute(
            f"INSERT INTO errors ({cols}) VALUES ({placeholders})",
            [row[c] for c in ERROR_COLUMNS],
        )
    logger.info(f"Error logged: {data.get('email_subject')}")


def update_file_link(
    invoice_number: str,
    seller_tax_code: str,
    pdf_link: str | None = None,
    xml_link: str | None = None,
) -> None:
    _ensure_tables()
    updates = []
    values = []
    if pdf_link is not None:
        updates.append('"pdf_file_link" = ?')
        values.append(pdf_link)
    if xml_link is not None:
        updates.append('"xml_file_link" = ?')
        values.append(xml_link)
    if not updates:
        return
    values.extend([invoice_number, seller_tax_code])
    with _get_conn() as conn:
        conn.execute(
            f"UPDATE invoices SET {', '.join(updates)} "
            "WHERE invoice_number = ? AND seller_tax_code = ?",
            values,
        )
