import importlib
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_invoices.db")


def test_append_invoice_creates_table_and_writes_row(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage.append_invoice({
            "invoice_number": "000123",
            "seller_tax_code": "0100109106",
            "invoice_type": "PURCHASE",
            "seller_name": "Công ty ABC",
            "total_after_tax": 11000000.0,
        })

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT invoice_number, invoice_type FROM invoices").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "000123"
    assert rows[0][1] == "PURCHASE"


def test_append_invoice_duplicate_ignored(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        data = {"invoice_number": "001", "seller_tax_code": "TAX001"}
        storage.append_invoice(data)
        storage.append_invoice(data)

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    conn.close()
    assert count == 1


def test_append_invoice_multiple_rows(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage.append_invoice({"invoice_number": "001", "seller_tax_code": "AAA"})
        storage.append_invoice({"invoice_number": "002", "seller_tax_code": "AAA"})

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT invoice_number FROM invoices ORDER BY invoice_number"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0][0] == "001"
    assert rows[1][0] == "002"


def test_append_error_writes_row(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage.append_error({
            "email_subject": "Hóa đơn test",
            "branch": "XML",
            "error_message": "Parse failed",
            "email_sender": "test@example.com",
        })

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT branch, email_subject FROM errors").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "XML"
    assert rows[0][1] == "Hóa đơn test"


def test_update_file_link_pdf(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage.append_invoice({"invoice_number": "001", "seller_tax_code": "TAX001"})
        storage.update_file_link("001", "TAX001", pdf_link="https://rvc-s3.rvctel.vn/file.pdf")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT pdf_file_link FROM invoices WHERE invoice_number='001'"
    ).fetchone()
    conn.close()
    assert row[0] == "https://rvc-s3.rvctel.vn/file.pdf"


def test_update_file_link_xml(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage.append_invoice({"invoice_number": "002", "seller_tax_code": "TAX001"})
        storage.update_file_link("002", "TAX001", xml_link="https://rvc-s3.rvctel.vn/file.xml")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT xml_file_link FROM invoices WHERE invoice_number='002'"
    ).fetchone()
    conn.close()
    assert row[0] == "https://rvc-s3.rvctel.vn/file.xml"


def test_wal_mode_enabled(db_path):
    with patch("config.DB_PATH", db_path):
        import storage
        importlib.reload(storage)
        storage._ensure_tables()

    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"
