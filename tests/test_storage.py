import csv
import os
from unittest.mock import patch


def test_ensure_csv_creates_file_with_headers(tmp_path):
    with patch("config.INVOICE_CSV", str(tmp_path / "invoices.csv")), \
         patch("config.ERROR_CSV", str(tmp_path / "errors.csv")):
        import importlib
        import storage
        importlib.reload(storage)
        storage._ensure_csv(str(tmp_path / "invoices.csv"), storage.INVOICE_COLUMNS)

    filepath = str(tmp_path / "invoices.csv")
    assert os.path.exists(filepath)
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == storage.INVOICE_COLUMNS


def test_append_invoice_writes_row(tmp_path):
    with patch("config.INVOICE_CSV", str(tmp_path / "invoices.csv")):
        import importlib
        import storage
        importlib.reload(storage)

        data = {
            "invoice_number": "000123",
            "invoice_type": "PURCHASE",
            "seller_name": "Công ty ABC",
            "total_after_tax": 11000000.0,
        }
        storage.append_invoice(data)

    with open(str(tmp_path / "invoices.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["invoice_number"] == "000123"
    assert rows[0]["invoice_type"] == "PURCHASE"
    assert rows[0]["total_after_tax"] == "11000000.0"


def test_append_invoice_appends_not_overwrites(tmp_path):
    with patch("config.INVOICE_CSV", str(tmp_path / "invoices.csv")):
        import importlib
        import storage
        importlib.reload(storage)

        storage.append_invoice({"invoice_number": "001"})
        storage.append_invoice({"invoice_number": "002"})

    with open(str(tmp_path / "invoices.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["invoice_number"] == "001"
    assert rows[1]["invoice_number"] == "002"


def test_append_error_writes_row(tmp_path):
    with patch("config.ERROR_CSV", str(tmp_path / "errors.csv")):
        import importlib
        import storage
        importlib.reload(storage)

        data = {
            "email_subject": "Hóa đơn test",
            "branch": "XML",
            "error_message": "Parse failed",
            "email_sender": "test@example.com",
        }
        storage.append_error(data)

    with open(str(tmp_path / "errors.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["branch"] == "XML"
    assert rows[0]["email_subject"] == "Hóa đơn test"
