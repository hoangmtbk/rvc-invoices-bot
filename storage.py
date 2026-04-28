import csv
import logging
import os

from config import ERROR_CSV, INVOICE_CSV

logger = logging.getLogger(__name__)

INVOICE_COLUMNS = [
    "invoice_type", "invoice_symbol", "invoice_number",
    "issue_date", "seller_name",
    "seller_tax_code", "buyer_name", "buyer_tax_code",
    "description", "total_before_tax",
    "vat_rate", "total_vat_amount", "total_after_tax","lookup_code", "lookup_website", 
    "source_branch", "source_email_subject", "processed_date", 
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


def _is_duplicate_invoice(invoice_number: str, seller_tax_code: str) -> bool:
    """Return True if an invoice with the same number and seller already exists."""
    if not os.path.exists(INVOICE_CSV):
        return False
    with open(INVOICE_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row.get("invoice_number") == invoice_number
                and row.get("seller_tax_code") == seller_tax_code
            ):
                return True
    return False


def append_invoice(data: dict) -> None:
    _ensure_csv(INVOICE_CSV, INVOICE_COLUMNS)
    invoice_number = str(data.get("invoice_number", ""))
    seller_tax_code = str(data.get("seller_tax_code", ""))
    if _is_duplicate_invoice(invoice_number, seller_tax_code):
        logger.warning(
            f"Duplicate invoice skipped: {invoice_number} | seller_tax={seller_tax_code}"
        )
        return
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
