import csv
import logging
import os

from config import ERROR_CSV, INVOICE_CSV

logger = logging.getLogger(__name__)

INVOICE_COLUMNS = [
    "processed_date", "invoice_type", "invoice_symbol", "invoice_number",
    "issue_date", "lookup_code", "lookup_website", "seller_name",
    "seller_tax_code", "seller_address", "buyer_name", "buyer_tax_code",
    "buyer_address", "payment_method", "bank_account", "total_before_tax",
    "vat_rate", "total_vat_amount", "total_after_tax", "source_branch",
    "source_email_subject",
]

ERROR_COLUMNS = [
    "error_date", "email_sender", "email_time", "email_subject",
    "branch", "error_message",
]


def _ensure_csv(filepath: str, columns: list) -> None:
    if not os.path.exists(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()


def append_invoice(data: dict) -> None:
    _ensure_csv(INVOICE_CSV, INVOICE_COLUMNS)
    row = {col: data.get(col, "") for col in INVOICE_COLUMNS}
    with open(INVOICE_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INVOICE_COLUMNS)
        writer.writerow(row)
    logger.info(f"Invoice saved: {data.get('invoice_number')} | {data.get('invoice_type')}")


def append_error(data: dict) -> None:
    _ensure_csv(ERROR_CSV, ERROR_COLUMNS)
    row = {col: data.get(col, "") for col in ERROR_COLUMNS}
    with open(ERROR_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ERROR_COLUMNS)
        writer.writerow(row)
    logger.info(f"Error logged: {data.get('email_subject')}")
