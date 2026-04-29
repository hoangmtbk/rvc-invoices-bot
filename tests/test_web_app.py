import importlib
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture
def db_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE invoices (
        invoice_type TEXT, invoice_symbol TEXT, invoice_number TEXT,
        issue_date TEXT, seller_name TEXT, seller_tax_code TEXT,
        buyer_name TEXT, buyer_tax_code TEXT, contract_number TEXT,
        customer_code TEXT, description TEXT, total_before_tax TEXT,
        vat_rate TEXT, total_vat_amount TEXT, total_after_tax TEXT,
        lookup_code TEXT, lookup_website TEXT, pdf_file_link TEXT,
        xml_file_link TEXT, source_branch TEXT, source_email_subject TEXT,
        processed_date TEXT, PRIMARY KEY (invoice_number, seller_tax_code)
    )""")
    conn.execute(
        "INSERT INTO invoices (invoice_number, seller_tax_code, invoice_type, "
        "seller_name, issue_date, total_after_tax, pdf_file_link, xml_file_link, "
        "processed_date) VALUES (?,?,?,?,?,?,?,?,?)",
        ("001", "TAX001", "PURCHASE", "Công ty A", "2026-04-28", "11000000",
         "https://rvc-s3.rvctel.vn/rvc-invoices/file.pdf",
         "https://rvc-s3.rvctel.vn/rvc-invoices/file.xml",
         "2026-04-28 10:00:00"),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(db_with_data):
    with patch("config.DB_PATH", db_with_data), \
         patch("config.WEB_SECRET", "testsecret"), \
         patch("config.WEB_PORT", 8080):
        import web_app
        importlib.reload(web_app)
        web_app.app.config["TESTING"] = True
        with web_app.app.test_client() as c:
            yield c


def test_index_no_secret_returns_403(client):
    resp = client.get("/")
    assert resp.status_code == 403


def test_index_wrong_secret_returns_403(client):
    resp = client.get("/?secret=wrong")
    assert resp.status_code == 403


def test_index_correct_secret_returns_200(client):
    resp = client.get("/?secret=testsecret")
    assert resp.status_code == 200


def test_index_shows_invoice_data(client):
    resp = client.get("/?secret=testsecret")
    assert "Công ty A".encode("utf-8") in resp.data


def test_index_file_links_rendered_as_anchor(client):
    resp = client.get("/?secret=testsecret")
    assert b"rvc-s3.rvctel.vn" in resp.data
    assert b"<a href=" in resp.data


def test_export_no_secret_returns_403(client):
    resp = client.get("/export")
    assert resp.status_code == 403


def test_export_returns_csv(client):
    resp = client.get("/export?secret=testsecret")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert b"invoice_number" in resp.data
    assert b"001" in resp.data


def test_export_column_filter(client):
    resp = client.get("/export?secret=testsecret&columns=invoice_number,seller_name")
    assert resp.status_code == 200
    data = resp.data.decode("utf-8")
    assert "invoice_number" in data
    assert "seller_name" in data
    assert "buyer_name" not in data


def test_export_filename_contains_date(client):
    resp = client.get("/export?secret=testsecret")
    cd = resp.headers.get("Content-Disposition", "")
    assert "hoa_don_" in cd
    assert ".csv" in cd
