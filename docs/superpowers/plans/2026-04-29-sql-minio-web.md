# SQL + MinIO + Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace CSV storage with SQLite, add MinIO file storage for raw PDF/XML files, extend the invoice schema with 4 new fields, and add a Flask web UI with Traefik SSL.

**Architecture:** Two app containers (`rvc-invoices-bot`, `rvc-invoices-web`) share an `invoices_data` Docker volume containing `invoices.db` (SQLite WAL mode). The bot writes invoices and uploads raw files to MinIO (`rvc-minio`). The web container mounts the same volume and serves a read-only table + CSV export. Traefik terminates SSL and routes traffic to both the web UI and MinIO.

**Tech Stack:** Python 3.11, SQLite (stdlib `sqlite3`), `minio>=7.2.0`, Flask 3.0, Tailwind CSS CDN, Traefik v3, Docker Compose.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `config.py` | Modify | Add DB_PATH, MinIO, Web constants; remove CSV paths |
| `storage.py` | Rewrite | SQLite read/write; same public API + `update_file_link` |
| `file_storage.py` | Create | MinIO upload wrapper |
| `data_extractor.py` | Modify | Add `contract_number`, `customer_code` extraction |
| `router.py` | Rewrite | Multi-pair attachment processing + MinIO uploads |
| `reporter.py` | Modify | Read from SQLite instead of CSV |
| `web_app.py` | Create | Flask web UI (table + CSV export + secret auth) |
| `templates/index.html` | Create | Tailwind CSS invoice table |
| `Dockerfile.web` | Create | Web container image |
| `requirements.web.txt` | Create | Web container deps |
| `requirements.txt` | Modify | Add `minio>=7.2.0` |
| `docker-compose.yml` | Rewrite | Add traefik, rvc-invoices-web, rvc-minio services |
| `.env.example` | Modify | Add MinIO, Web, Traefik vars |
| `tests/test_config.py` | Modify | Update assertions for new/removed constants |
| `tests/test_storage.py` | Rewrite | SQLite-based tests |
| `tests/test_file_storage.py` | Create | MinIO upload tests |
| `tests/test_data_extractor.py` | Modify | Fix pre-existing failure; add new field tests |
| `tests/test_router.py` | Rewrite | Multi-pair + MinIO upload tests |
| `tests/test_reporter.py` | Modify | Update to mock `_query_df` instead of `pd.read_csv` |
| `tests/test_web_app.py` | Create | Flask test client tests |
| `data/Tong_hop_hoa_don.csv` | Delete | Replaced by SQLite |
| `data/errors.csv` | Delete | Replaced by SQLite |

---

## Task 1: Update `config.py` and `tests/test_config.py`

**Files:**
- Modify: `config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test for new config constants**

```python
# tests/test_config.py — replace entire file
import os
import importlib
from unittest.mock import patch


def test_config_constants():
    with patch.dict(os.environ, {
        "IMAP_SERVER": "mail.example.com",
        "IMAP_PORT": "993",
        "EMAIL_POLL_INTERVAL_MINUTES": "15",
        "DAILY_REPORT_TIME": "08:00",
        "RVC_TAX_CODE": "0313028740",
        "IMAP_USER": "",
        "IMAP_PASSWORD": "",
        "GEMINI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "MINIO_ENDPOINT": "rvc-minio:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
        "MINIO_BUCKET": "rvc-invoices",
        "MINIO_PUBLIC_URL": "https://rvc-s3.rvctel.vn",
        "WEB_PORT": "8080",
        "WEB_SECRET": "testsecret",
    }, clear=True):
        import config
        importlib.reload(config)
        assert config.IMAP_SERVER == "mail.example.com"
        assert config.IMAP_PORT == 993
        assert config.DB_PATH.endswith("invoices.db")
        assert config.MINIO_ENDPOINT == "rvc-minio:9000"
        assert config.MINIO_BUCKET == "rvc-invoices"
        assert config.MINIO_PUBLIC_URL == "https://rvc-s3.rvctel.vn"
        assert config.WEB_PORT == 8080
        assert config.WEB_SECRET == "testsecret"
        assert config.LOG_FILE.endswith("bot.log")
        assert not hasattr(config, "INVOICE_CSV")
        assert not hasattr(config, "ERROR_CSV")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_config.py -v
```
Expected: FAIL — `config` has no `DB_PATH`, still has `INVOICE_CSV`.

- [ ] **Step 3: Rewrite `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER: str = os.getenv("IMAP_SERVER", "mail.rvctel.vn")
IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER: str = os.getenv("IMAP_USER", "")
IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_POLL_INTERVAL_MINUTES: int = int(os.getenv("EMAIL_POLL_INTERVAL_MINUTES", "15"))
DAILY_REPORT_TIME: str = os.getenv("DAILY_REPORT_TIME", "08:00")

RVC_TAX_CODE: str = os.getenv("RVC_TAX_CODE", "0313028740")

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
LOG_DIR: str = os.path.join(BASE_DIR, "logs")

DB_PATH: str = os.path.join(DATA_DIR, "invoices.db")
LOG_FILE: str = os.path.join(LOG_DIR, "bot.log")

MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "rvc-minio:9000")
MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "rvc-invoices")
MINIO_PUBLIC_URL: str = os.getenv("MINIO_PUBLIC_URL", "")

WEB_PORT: int = int(os.getenv("WEB_PORT", "8080"))
WEB_SECRET: str = os.getenv("WEB_SECRET", "")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add config.py tests/test_config.py
git commit -m "feat: update config.py — add DB_PATH, MinIO, Web constants; remove CSV paths"
```

---

## Task 2: Rewrite `storage.py` with SQLite

**Files:**
- Modify: `storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py — replace entire file
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_storage.py -v
```
Expected: FAIL — `storage` still uses CSV.

- [ ] **Step 3: Rewrite `storage.py`**

```python
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
        return
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_storage.py -v
```
Expected: 7 PASS

- [ ] **Step 5: Delete old CSV files**

```bash
cd /home/ai/rvc-invoices-bot
rm -f data/Tong_hop_hoa_don.csv data/errors.csv
```

- [ ] **Step 6: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add storage.py tests/test_storage.py data/
git commit -m "feat: replace CSV storage with SQLite — append_invoice, append_error, update_file_link"
```

---

## Task 3: Create `file_storage.py`

**Files:**
- Create: `file_storage.py`
- Create: `tests/test_file_storage.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add `minio` to requirements.txt**

In `requirements.txt`, add after the `requests` line:
```
minio>=7.2.0
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_file_storage.py
from unittest.mock import MagicMock, patch


def test_build_filename_pdf():
    from file_storage import build_filename
    assert build_filename("0310674520", "000123", "20260429", "pdf") == \
        "0310674520_000123_20260429.pdf"


def test_build_filename_xml():
    from file_storage import build_filename
    assert build_filename("0310674520", "000456", "20260429", "xml") == \
        "0310674520_000456_20260429.xml"


def test_build_filename_empty_fields():
    from file_storage import build_filename
    assert build_filename("", "", "", "pdf") == "unknown_unknown_00000000.pdf"


def test_upload_file_returns_url():
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True

    with patch("file_storage._get_client", return_value=mock_client), \
         patch("file_storage.MINIO_BUCKET", "rvc-invoices"), \
         patch("file_storage.MINIO_PUBLIC_URL", "https://rvc-s3.rvctel.vn"):
        import importlib
        import file_storage
        importlib.reload(file_storage)
        url = file_storage.upload_file(
            b"data", "0310674520_000123_20260429.pdf", "application/pdf"
        )

    assert url == "https://rvc-s3.rvctel.vn/rvc-invoices/0310674520_000123_20260429.pdf"
    mock_client.put_object.assert_called_once()


def test_upload_file_creates_bucket_when_missing():
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False

    with patch("file_storage._get_client", return_value=mock_client), \
         patch("file_storage.MINIO_BUCKET", "rvc-invoices"), \
         patch("file_storage.MINIO_PUBLIC_URL", "https://rvc-s3.rvctel.vn"):
        import importlib
        import file_storage
        importlib.reload(file_storage)
        file_storage.upload_file(b"data", "test.pdf", "application/pdf")

    mock_client.make_bucket.assert_called_once_with("rvc-invoices")
    mock_client.set_bucket_policy.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_file_storage.py -v
```
Expected: FAIL — `file_storage` module not found.

- [ ] **Step 4: Create `file_storage.py`**

```python
import json
import logging
from io import BytesIO

from minio import Minio

from config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_URL,
    MINIO_SECRET_KEY,
)

logger = logging.getLogger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return _client


def _ensure_bucket() -> None:
    client = _get_client()
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"],
            }],
        })
        client.set_bucket_policy(MINIO_BUCKET, policy)
        logger.info(f"MinIO bucket '{MINIO_BUCKET}' created with public-read policy")


def build_filename(
    seller_tax_code: str, invoice_number: str, date_str: str, ext: str
) -> str:
    """Construct canonical MinIO filename."""
    tax = seller_tax_code or "unknown"
    num = invoice_number or "unknown"
    date = date_str or "00000000"
    return f"{tax}_{num}_{date}.{ext}"


def upload_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Upload bytes to MinIO, return public HTTPS URL."""
    _ensure_bucket()
    client = _get_client()
    client.put_object(
        MINIO_BUCKET,
        filename,
        BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=content_type,
    )
    url = f"{MINIO_PUBLIC_URL.rstrip('/')}/{MINIO_BUCKET}/{filename}"
    logger.info(f"Uploaded to MinIO: {filename}")
    return url
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_file_storage.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add file_storage.py tests/test_file_storage.py requirements.txt
git commit -m "feat: add file_storage.py — MinIO upload wrapper with public-read bucket"
```

---

## Task 4: Update `data_extractor.py` — new fields + fix pre-existing test failure

**Files:**
- Modify: `data_extractor.py`
- Modify: `tests/test_data_extractor.py`

**Context:** `test_parse_xml_all_fields` in `test_data_extractor.py` currently fails with `KeyError: 'payment_method'` — those fields were removed from the schema. Fix this test while adding the new field assertions.

- [ ] **Step 1: Write new tests (and fix the broken one)**

Add these tests to `tests/test_data_extractor.py`. First, replace `test_parse_xml_all_fields` (lines 43–58) with the version below, then append the two new tests at the end of the file.

Replace the broken `test_parse_xml_all_fields`:
```python
def test_parse_xml_all_fields():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)

    assert result["invoice_symbol"] == "1C24TKQ"
    assert result["invoice_number"] == "000123"
    assert result["issue_date"] == "2024-01-15"
    assert result["lookup_code"] == "MKKUXJMAG"
    assert result["seller_tax_code"] == "0100109106"
    assert result["buyer_tax_code"] == "0313028740"
    assert result["total_before_tax"] == 10000000.0
    assert result["vat_rate"] == "10%"
    assert result["total_vat_amount"] == 1000000.0
    assert result["total_after_tax"] == 11000000.0
```

Append new tests at end of file:
```python
SAMPLE_XML_WITH_CONTRACT = b"""<?xml version="1.0" encoding="UTF-8"?>
<HDon xmlns="http://laphoadon.gdt.gov.vn/2014/09/xmlInvoiceDataFmt/v1">
  <DLHDon>
    <TTChung>
      <SHDon>000999</SHDon>
      <NLap>2026-04-29</NLap>
      <SoHopDong>HD-2026-001</SoHopDong>
    </TTChung>
    <NDHDon>
      <NBan><MST>0100109106</MST></NBan>
      <NMua>
        <MST>0313028740</MST>
        <MaThueBao>VT-00123456</MaThueBao>
      </NMua>
      <TToan>
        <TgTCThue>0</TgTCThue>
        <TgTThue>0</TgTThue>
        <TgTTTBSo>0</TgTTTBSo>
      </TToan>
    </NDHDon>
  </DLHDon>
</HDon>"""


def test_parse_xml_contract_number():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_WITH_CONTRACT)
    assert result["contract_number"] == "HD-2026-001"


def test_parse_xml_customer_code_mathuebao():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_WITH_CONTRACT)
    assert result["customer_code"] == "VT-00123456"


def test_parse_xml_contract_number_missing_returns_none():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result.get("contract_number") is None


def test_parse_pdf_via_gemini_includes_new_fields(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    mock_response = MagicMock()
    mock_response.text = (
        '{"invoice_number": "001", "seller_tax_code": "0100109106",'
        ' "total_after_tax": 5500000,'
        ' "contract_number": "HD-001", "customer_code": "KH-999"}'
    )
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):
        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["contract_number"] == "HD-001"
    assert result["customer_code"] == "KH-999"
```

- [ ] **Step 2: Run tests to see current state**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_data_extractor.py -v
```
Expected: `test_parse_xml_all_fields` FAIL (payment_method), new tests FAIL (fields not in parse_xml yet).

- [ ] **Step 3: Update `data_extractor.py`**

In `parse_xml`, add the two new fields to the returned dict (after `lookup_code`):
```python
    return {
        "invoice_type": _determine_invoice_type(seller_tax_code),
        "invoice_symbol": (symbol_part1 + symbol_part2).strip() or None,
        "invoice_number": _find_text(root, "SHDon", "SoHoaDon"),
        "issue_date": _find_text(root, "NLap", "NgayLap"),
        "seller_name": _find_text(nban, "Ten"),
        "seller_tax_code": seller_tax_code,
        "buyer_name": _find_text(nmua, "Ten"),
        "buyer_tax_code": _find_text(nmua, "MST", "MaSoThue"),
        "contract_number": _find_text(root, "SoHopDong", "SHD", "Số hợp đồng", "contractNumber"),
        "customer_code": _find_text(root, "MaKhachHang", "MaKH", "MaThueBao", "subscriberNumber"),
        "description": _find_text(root, "THHDVu", "TenHangHoaDichVu"),
        "total_before_tax": _to_float(_find_text(root, "TgTCThue", "TongTienChuaThue")),
        "vat_rate": _find_text(hhdvu, "TSuat", "ThueSuat") if hhdvu is not None else None,
        "total_vat_amount": _to_float(_find_text(root, "TgTThue", "TongTienThue")),
        "total_after_tax": _to_float(_find_text(root, "TgTTTBSo", "TongTienThanhToan")),
        "lookup_code": _find_text(
            root, "MaQRCode", "MTra", "MCCQT", "MaTraCuu", "MaKiemTra"
        ),
        "lookup_website": None,
    }
```

Replace `GEMINI_PROMPT` in `data_extractor.py` with:
```python
GEMINI_PROMPT = """Bạn là trợ lý trích xuất dữ liệu hóa đơn điện tử Việt Nam.
Trích xuất thông tin từ file PDF hóa đơn và trả về JSON với định dạng chính xác sau.
QUAN TRỌNG: Chỉ trả về JSON thuần túy, KHÔNG có văn bản hay markdown khác.

{
  "invoice_symbol": "ký hiệu hóa đơn hoặc null",
  "invoice_number": "số hóa đơn hoặc null",
  "issue_date": "ngày lập YYYY-MM-DD hoặc null",
  "seller_name": "tên người bán hoặc null",
  "seller_tax_code": "mã số thuế người bán hoặc null",
  "buyer_name": "tên người mua hoặc null",
  "buyer_tax_code": "mã số thuế người mua hoặc null",
  "contract_number": "Số hợp đồng / contract number, null nếu không có",
  "customer_code": "Mã khách hàng / mã thuê bao (Viettel subscriber number), null nếu không có",
  "description": "mô tả hàng hóa/dịch vụ hoặc null",
  "total_before_tax": số_thực_hoặc_null,
  "vat_rate": "thuế suất ví dụ '10%' hoặc null",
  "total_vat_amount": số_thực_hoặc_null,
  "total_after_tax": số_thực_hoặc_null,
  "lookup_code": "mã tra cứu hoặc null",
  "lookup_website": "website tra cứu hoặc null"
}"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_data_extractor.py -v
```
Expected: All PASS (including the previously failing `test_parse_xml_all_fields`).

- [ ] **Step 5: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add data_extractor.py tests/test_data_extractor.py
git commit -m "feat: add contract_number/customer_code to XML parser and Gemini prompt; fix stale test"
```

---

## Task 5: Rewrite `router.py` — multi-pair processing + MinIO uploads

**Files:**
- Modify: `router.py`
- Modify: `tests/test_router.py`

**Context:** The new router dumps ALL attachments to `temp/<uid>/`, extracts ZIPs recursively, groups files by filename stem into pairs, and processes each pair independently. `source_branch` is determined per-pair: XML from ZIP → "ZIP", direct XML → "XML", PDF only → "PDF", HTML with embedded XML → "HTML". WEB branch (no attachments) is unchanged except it now uploads to MinIO.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_router.py — replace entire file
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest


def _make_email(uid="1", subject="Hóa đơn test", attachments=None, text="", html=""):
    email = MagicMock()
    email.uid = uid
    email.subject = subject
    email.attachments = attachments or []
    email.text = text
    email.html = html
    email.from_ = "sender@example.com"
    email.date = MagicMock()
    email.date.strftime.return_value = "09:00"
    return email


def _make_attachment(filename: str, payload: bytes = b"data"):
    att = MagicMock()
    att.filename = filename
    att.payload = payload
    return att


def test_single_xml_attachment_xml_branch(tmp_path):
    att = _make_attachment("HD001.xml", b"<HDon/>")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "XML"
    assert stored["xml_file_link"] == "https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"
    assert stored["pdf_file_link"] == ""


def test_zip_with_xml_sets_zip_branch(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("HD002.xml", b"<?xml version='1.0'?><HDon/>")
    zip_bytes = buf.getvalue()

    att = _make_attachment("HD002.zip", zip_bytes)
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "002", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "ZIP"


def test_pdf_only_attachment_pdf_branch(tmp_path):
    att = _make_attachment("HD003.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "003", "seller_tax_code": "TAX"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.pdf"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF-1.4")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "PDF"
    assert stored["pdf_file_link"] == "https://rvc-s3.rvctel.vn/rvc-invoices/file.pdf"
    assert stored["xml_file_link"] == ""


def test_paired_xml_and_pdf_both_uploaded(tmp_path):
    xml_att = _make_attachment("HD004.xml", b"<HDon/>")
    pdf_att = _make_attachment("HD004.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[xml_att, pdf_att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "004", "seller_tax_code": "TAX"}), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", side_effect=["https://xml.url", "https://pdf.url"]), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    stored = mock_store.call_args[0][0]
    assert stored["xml_file_link"] == "https://xml.url"
    assert stored["pdf_file_link"] == "https://pdf.url"


def test_multiple_pairs_multiple_invoice_calls(tmp_path):
    xml1 = _make_attachment("HD001.xml", b"<HDon/>")
    xml2 = _make_attachment("HD002.xml", b"<HDon/>")
    email = _make_email(attachments=[xml1, xml2])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001", "seller_tax_code": "TAX"}), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    assert mock_store.call_count == 2


def test_web_branch_xml_path(tmp_path):
    email = _make_email(text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu")

    with patch("router.web_extraction_router.process_branch_4", return_value=(b"<HDon/>", "xml")), \
         patch("router.data_extractor.parse_xml", return_value={"invoice_number": "005", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once_with(b"<HDon/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_web_branch_pdf_path(tmp_path):
    email = _make_email(text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu")

    with patch("router.web_extraction_router.process_branch_4", return_value=(b"%PDF", "pdf")), \
         patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "006", "seller_tax_code": "TAX"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_error_sends_alert_and_logs_error(tmp_path):
    att = _make_attachment("HD007.xml", b"bad xml")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=ValueError("XML parse error")), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.storage.append_error") as mock_err, \
         patch("router.reporter.send_error_alert") as mock_alert, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.file_storage.upload_file"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_store.assert_not_called()
    mock_err.assert_called_once()
    err_data = mock_err.call_args[0][0]
    assert "XML parse error" in err_data["error_message"]
    mock_alert.assert_called_once()


def test_mark_as_seen_always_called_even_on_error(tmp_path):
    att = _make_attachment("HD008.xml", b"bad")
    email = _make_email(uid="99", attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=Exception("Boom")), \
         patch("router.storage.append_error"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.email_handler.mark_as_seen") as mock_seen, \
         patch("router.file_storage.upload_file"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_seen.assert_called_once_with("99")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_router.py -v
```
Expected: Most FAIL — old router architecture.

- [ ] **Step 3: Rewrite `router.py`**

```python
import logging
import os
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime

import data_extractor
import email_handler
import file_storage
import reporter
import storage
import web_extraction_router
from config import TEMP_DIR

logger = logging.getLogger(__name__)


def _dump_and_extract(email, uid_temp: str) -> bool:
    """Save all attachments to uid_temp, extract ZIPs recursively.
    Returns True if any ZIP attachment was present."""
    had_zip = False
    os.makedirs(uid_temp, exist_ok=True)
    for att in email.attachments:
        fname = att.filename or f"attachment_{id(att)}"
        if fname.lower().endswith(".zip"):
            had_zip = True
        fpath = os.path.join(uid_temp, fname)
        with open(fpath, "wb") as f:
            f.write(att.payload)
    changed = True
    while changed:
        changed = False
        for root, _, files in os.walk(uid_temp):
            for fn in list(files):
                if fn.lower().endswith(".zip"):
                    zip_path = os.path.join(root, fn)
                    try:
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            zf.extractall(root)
                        os.remove(zip_path)
                        changed = True
                    except zipfile.BadZipFile:
                        os.remove(zip_path)
                        changed = True
    return had_zip


def _collect_pairs(uid_temp: str) -> list[dict]:
    """Group .xml, .pdf, .html files by filename stem."""
    by_stem: dict[str, dict] = defaultdict(dict)
    for root, _, files in os.walk(uid_temp):
        for fn in files:
            lower = fn.lower()
            if lower.endswith((".xml", ".pdf", ".html")):
                stem = os.path.splitext(fn)[0]
                ext = os.path.splitext(fn)[1].lstrip(".").lower()
                by_stem[stem][ext] = os.path.join(root, fn)
    return [{"stem": stem, **exts} for stem, exts in by_stem.items()]


def _process_pair(pair: dict, email, had_zip: bool) -> None:
    """Parse one file pair, upload to MinIO, append invoice to DB."""
    subject = email.subject or ""
    xml_bytes = pdf_bytes = None

    if "xml" in pair:
        with open(pair["xml"], "rb") as f:
            xml_bytes = f.read()
    if "pdf" in pair:
        with open(pair["pdf"], "rb") as f:
            pdf_bytes = f.read()
    if "html" in pair and xml_bytes is None:
        with open(pair["html"], encoding="utf-8", errors="replace") as f:
            html_content = f.read()
        extracted = web_extraction_router.extract_xml_from_html_attachment(html_content)
        if extracted:
            xml_bytes = extracted

    if xml_bytes is not None:
        data = data_extractor.parse_xml(xml_bytes)
        if "html" in pair and "xml" not in pair:
            branch = "HTML"
        elif had_zip:
            branch = "ZIP"
        else:
            branch = "XML"
    elif pdf_bytes is not None:
        data = data_extractor.parse_pdf_via_gemini(pdf_bytes)
        branch = "PDF"
    else:
        raise ValueError(f"No parseable file in pair: {pair.get('stem')}")

    date_str = datetime.now().strftime("%Y%m%d")
    inv_num = str(data.get("invoice_number") or "unknown")
    tax_code = str(data.get("seller_tax_code") or "unknown")
    xml_link = ""
    pdf_link = ""

    if xml_bytes is not None:
        xml_link = file_storage.upload_file(
            xml_bytes,
            file_storage.build_filename(tax_code, inv_num, date_str, "xml"),
            "application/xml",
        )
    if pdf_bytes is not None:
        pdf_link = file_storage.upload_file(
            pdf_bytes,
            file_storage.build_filename(tax_code, inv_num, date_str, "pdf"),
            "application/pdf",
        )

    data["xml_file_link"] = xml_link
    data["pdf_file_link"] = pdf_link
    data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["source_branch"] = branch
    data["source_email_subject"] = subject
    storage.append_invoice(data)
    logger.info(f"Invoice saved | branch={branch} | number={data.get('invoice_number')}")


def process_email(email) -> None:
    subject = email.subject or ""
    sender = str(email.from_)
    email_time = email.date.strftime("%H:%M") if email.date else ""
    uid_temp = os.path.join(TEMP_DIR, str(email.uid))
    branch = "UNKNOWN"

    try:
        if email.attachments:
            branch = "ATTACH"
            had_zip = _dump_and_extract(email, uid_temp)
            pairs = _collect_pairs(uid_temp)
            if not pairs:
                raise ValueError("No XML/PDF/HTML files found in attachments or ZIPs")
            for pair in pairs:
                _process_pair(pair, email, had_zip)

        else:
            branch = "WEB"
            logger.info(f"Branch WEB | uid={email.uid} | subject='{subject}'")
            result = web_extraction_router.process_branch_4(email)
            if result is None:
                raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
            file_bytes, content_type = result
            date_str = datetime.now().strftime("%Y%m%d")

            if content_type == "xml":
                data = data_extractor.parse_xml(file_bytes)
                inv_num = str(data.get("invoice_number") or "unknown")
                tax_code = str(data.get("seller_tax_code") or "unknown")
                xml_link = file_storage.upload_file(
                    file_bytes,
                    file_storage.build_filename(tax_code, inv_num, date_str, "xml"),
                    "application/xml",
                )
                pdf_link = ""
            else:
                data = data_extractor.parse_pdf_via_gemini(file_bytes)
                inv_num = str(data.get("invoice_number") or "unknown")
                tax_code = str(data.get("seller_tax_code") or "unknown")
                pdf_link = file_storage.upload_file(
                    file_bytes,
                    file_storage.build_filename(tax_code, inv_num, date_str, "pdf"),
                    "application/pdf",
                )
                xml_link = ""

            data["xml_file_link"] = xml_link
            data["pdf_file_link"] = pdf_link
            data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data["source_branch"] = "WEB"
            data["source_email_subject"] = subject
            storage.append_invoice(data)
            logger.info(f"Invoice saved | branch=WEB | number={data.get('invoice_number')}")

    except Exception as e:
        logger.error(
            f"Error processing email uid={email.uid} branch={branch}: {e}",
            exc_info=True,
        )
        reporter.send_error_alert(subject, branch, str(e))
        storage.append_error({
            "error_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "email_sender": sender,
            "email_time": email_time,
            "email_subject": subject,
            "branch": branch,
            "error_message": str(e),
        })
    finally:
        shutil.rmtree(uid_temp, ignore_errors=True)
        email_handler.mark_as_seen(email.uid)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_router.py -v
```
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add router.py tests/test_router.py
git commit -m "feat: rewrite router — multi-pair attachment processing with MinIO uploads"
```

---

## Task 6: Update `reporter.py` to read from SQLite

**Files:**
- Modify: `reporter.py`
- Modify: `tests/test_reporter.py`

- [ ] **Step 1: Write the updated tests**

Replace `tests/test_reporter.py` with:

```python
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_send_error_alert_formats_message_correctly():
    with patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_error_alert
        send_error_alert("Hóa đơn Petrolimex tháng 1", "ZIP", "No XML in archive")

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["text"]
    assert "Hóa đơn Petrolimex tháng 1" in body
    assert "ZIP" in body
    assert "No XML in archive" in body
    assert "⚠️" in body


def test_send_error_alert_does_not_raise_on_telegram_failure():
    with patch("reporter.requests.post", side_effect=Exception("Network error")):
        from reporter import send_error_alert
        send_error_alert("subject", "XML", "error")


def test_send_daily_report_invoice_summary():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 09:00:00", "invoice_type": "PURCHASE", "total_after_tax": 5000000.0},
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 3000000.0},
        {"processed_date": f"{yesterday} 11:00:00", "invoice_type": "SALE",     "total_after_tax": 8000000.0},
    ])
    err_df = pd.DataFrame(columns=["error_date", "email_sender", "email_time",
                                    "email_subject", "branch", "error_message"])

    with patch("reporter._query_df", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Tổng số hóa đơn: 3" in body
    assert "PURCHASE" in body
    assert "SALE" in body
    assert "8,000,000" in body or "8000000" in body
    assert "Lỗi" not in body


def test_send_daily_report_includes_errors_when_present():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 5000000.0},
    ])
    err_df = pd.DataFrame([{
        "error_date": f"{yesterday} 09:05:00",
        "email_sender": "supplier@abc.com",
        "email_time": "09:05",
        "email_subject": "Hóa đơn XYZ",
        "branch": "ZIP",
        "error_message": "Corrupt ZIP file",
    }])

    with patch("reporter._query_df", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Lỗi xử lý: 1 email" in body
    assert "supplier@abc.com" in body
    assert "Hóa đơn XYZ" in body
    assert "Corrupt ZIP file" in body


def test_send_daily_report_omits_error_section_when_no_errors():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 1000000.0},
    ])
    err_df = pd.DataFrame(columns=["error_date", "email_sender", "email_time",
                                    "email_subject", "branch", "error_message"])

    with patch("reporter._query_df", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Lỗi" not in body


def test_send_daily_report_handles_db_error():
    with patch("reporter._query_df", side_effect=Exception("DB not found")), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["text"]
    assert "Tổng số hóa đơn: 0" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_reporter.py -v
```
Expected: `test_send_daily_report_*` tests FAIL — `reporter` has no `_query_df`.

- [ ] **Step 3: Update `reporter.py`**

```python
import logging
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _telegram_url() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def _send_telegram(message: str) -> None:
    try:
        resp = requests.post(
            _telegram_url(),
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def _query_df(sql: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def send_error_alert(subject: str, branch: str, error: str) -> None:
    message = (
        "⚠️ Lỗi xử lý hóa đơn\n"
        f"📧 Email: {subject}\n"
        f"🔀 Nhánh: {branch}\n"
        f"❌ Lỗi: {error}"
    )
    _send_telegram(message)


def send_daily_report() -> None:
    yesterday_dt = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday_dt.strftime("%Y-%m-%d")
    report_date = yesterday_dt.strftime("%d/%m/%Y")

    try:
        inv_df = _query_df(
            "SELECT invoice_type, total_after_tax, processed_date FROM invoices"
        )
        inv_df["processed_date"] = pd.to_datetime(inv_df["processed_date"])
        inv_df["total_after_tax"] = pd.to_numeric(inv_df["total_after_tax"], errors="coerce").fillna(0)
        inv_yday = inv_df[inv_df["processed_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
    except Exception:
        inv_yday = pd.DataFrame(columns=["invoice_type", "total_after_tax"])

    total = len(inv_yday)
    purchase = inv_yday[inv_yday["invoice_type"] == "PURCHASE"]
    sale = inv_yday[inv_yday["invoice_type"] == "SALE"]

    def fmt(n: float) -> str:
        return f"{n:,.0f}"

    lines = [
        f"📊 Báo cáo hóa đơn ngày {report_date}",
        "",
        f"✅ Tổng số hóa đơn: {total}",
        f"📥 Đầu vào (PURCHASE): {len(purchase)} hóa đơn | Tổng tiền: {fmt(purchase['total_after_tax'].sum())} VND",
        f"📤 Đầu ra (SALE): {len(sale)} hóa đơn | Tổng tiền: {fmt(sale['total_after_tax'].sum())} VND",
    ]

    try:
        err_df = _query_df("SELECT * FROM errors")
        err_df["error_date"] = pd.to_datetime(err_df["error_date"])
        err_yday = err_df[err_df["error_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
        if len(err_yday) > 0:
            lines.append("")
            lines.append(f"⚠️ Lỗi xử lý: {len(err_yday)} email")
            for _, row in err_yday.iterrows():
                t = pd.to_datetime(row["error_date"]).strftime("%H:%M")
                lines.append(
                    f"- [{t}] Từ: {row['email_sender']} | "
                    f"Tiêu đề: {row['email_subject']} | "
                    f"Lỗi: {row['error_message']}"
                )
    except Exception:
        pass

    _send_telegram("\n".join(lines))
    logger.info(f"Daily report sent for {report_date}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_reporter.py -v
```
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add reporter.py tests/test_reporter.py
git commit -m "feat: update reporter to read from SQLite via _query_df helper"
```

---

## Task 7: Create Flask web UI

**Files:**
- Create: `web_app.py`
- Create: `templates/index.html`
- Create: `Dockerfile.web`
- Create: `requirements.web.txt`
- Create: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_app.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/test_web_app.py -v
```
Expected: FAIL — `web_app` module not found.

- [ ] **Step 3: Create `web_app.py`**

```python
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
        lines.append(",".join(f'"{str(v or "")}"' for v in row))

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
```

- [ ] **Step 4: Create `templates/index.html`**

First create the directory:
```bash
mkdir -p /home/ai/rvc-invoices-bot/templates
```

Then create `templates/index.html`:
```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hóa đơn điện tử — RVC</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 text-sm">
<div class="mx-auto p-4">
  <h1 class="text-xl font-bold text-gray-800 mb-4">📄 Tổng hợp hóa đơn điện tử</h1>

  <!-- Filter form -->
  <form method="get" class="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-3 items-end">
    <input type="hidden" name="secret" value="{{ secret }}">
    <div>
      <label class="block text-xs text-gray-500 mb-1">Từ ngày</label>
      <input type="date" name="from_date" value="{{ args.get('from_date','') }}"
             class="border rounded px-2 py-1 text-sm">
    </div>
    <div>
      <label class="block text-xs text-gray-500 mb-1">Đến ngày</label>
      <input type="date" name="to_date" value="{{ args.get('to_date','') }}"
             class="border rounded px-2 py-1 text-sm">
    </div>
    <div>
      <label class="block text-xs text-gray-500 mb-1">Loại</label>
      <select name="invoice_type" class="border rounded px-2 py-1 text-sm">
        <option value="ALL" {% if args.get('invoice_type','ALL')=='ALL' %}selected{% endif %}>Tất cả</option>
        <option value="PURCHASE" {% if args.get('invoice_type')=='PURCHASE' %}selected{% endif %}>Đầu vào</option>
        <option value="SALE" {% if args.get('invoice_type')=='SALE' %}selected{% endif %}>Đầu ra</option>
      </select>
    </div>
    <div>
      <label class="block text-xs text-gray-500 mb-1">Tìm kiếm</label>
      <input type="text" name="search" value="{{ args.get('search','') }}"
             placeholder="Số HĐ / người bán / người mua"
             class="border rounded px-2 py-1 text-sm w-64">
    </div>
    <button type="submit"
            class="bg-blue-600 text-white px-4 py-1.5 rounded hover:bg-blue-700">Lọc</button>
    <a href="/?secret={{ secret }}"
       class="text-sm text-gray-500 underline py-1.5">Xóa lọc</a>
    <a href="/export?secret={{ secret }}&{{ args | urlencode }}"
       class="ml-auto bg-green-600 text-white px-4 py-1.5 rounded hover:bg-green-700">⬇ Xuất CSV</a>
  </form>

  <!-- Column toggles -->
  <details class="bg-white rounded-lg shadow p-4 mb-4">
    <summary class="cursor-pointer text-sm font-medium text-gray-700">
      Cột hiển thị ({{ columns | length }})
    </summary>
    <div class="mt-3 flex flex-wrap gap-2">
      {% for col in columns %}
      <label class="flex items-center gap-1 text-xs cursor-pointer">
        <input type="checkbox" checked onchange="toggleCol({{ loop.index0 }}, this.checked)">
        {{ col }}
      </label>
      {% endfor %}
    </div>
  </details>

  <!-- Info -->
  <p class="text-xs text-gray-500 mb-2">
    Tổng: <strong>{{ total }}</strong> hóa đơn | Trang {{ page }}/{{ total_pages }}
  </p>

  <!-- Table -->
  <div class="overflow-x-auto rounded-lg shadow">
    <table class="min-w-full bg-white text-xs border-collapse" id="tbl">
      <thead>
        <tr class="bg-gray-100">
          {% for col in columns %}
          <th class="px-3 py-2 text-left font-semibold text-gray-600 border-b whitespace-nowrap c{{ loop.index0 }}">
            {{ col }}
          </th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
        <tr class="{{ 'bg-gray-50' if loop.index % 2 == 0 else 'bg-white' }} hover:bg-blue-50">
          {% for col in columns %}
          <td class="px-3 py-1.5 border-b text-gray-700 whitespace-nowrap c{{ loop.index0 }}">
            {% set val = row[col] %}
            {% if col == 'pdf_file_link' and val %}
              <a href="{{ val }}" target="_blank" class="text-blue-600 underline hover:text-blue-800">PDF</a>
            {% elif col == 'xml_file_link' and val %}
              <a href="{{ val }}" target="_blank" class="text-blue-600 underline hover:text-blue-800">XML</a>
            {% else %}
              {{ val or '' }}
            {% endif %}
          </td>
          {% endfor %}
        </tr>
        {% else %}
        <tr>
          <td colspan="{{ columns | length }}"
              class="px-3 py-6 text-center text-gray-400">Không có dữ liệu</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Pagination -->
  {% if total_pages > 1 %}
  <div class="flex gap-2 mt-4 items-center justify-center">
    {% if page > 1 %}
    <a href="?secret={{ secret }}&page={{ page - 1 }}&{{ args | urlencode }}"
       class="px-3 py-1 border rounded hover:bg-gray-100">← Trước</a>
    {% endif %}
    <span class="text-gray-600">{{ page }} / {{ total_pages }}</span>
    {% if page < total_pages %}
    <a href="?secret={{ secret }}&page={{ page + 1 }}&{{ args | urlencode }}"
       class="px-3 py-1 border rounded hover:bg-gray-100">Sau →</a>
    {% endif %}
  </div>
  {% endif %}
</div>

<script>
function toggleCol(idx, show) {
  document.querySelectorAll('.c' + idx).forEach(el => {
    el.style.display = show ? '' : 'none';
  });
}
</script>
</body>
</html>
```

- [ ] **Step 5: Create `requirements.web.txt`**

```
flask>=3.0.0
pandas>=2.1.0
python-dotenv>=1.0.1
```

- [ ] **Step 6: Create `Dockerfile.web`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.web.txt .
RUN pip install --no-cache-dir -r requirements.web.txt
COPY config.py storage.py web_app.py ./
COPY templates/ templates/
CMD ["python", "web_app.py"]
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && pip install flask --quiet && python -m pytest tests/test_web_app.py -v
```
Expected: 9 PASS

- [ ] **Step 8: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add web_app.py templates/ Dockerfile.web requirements.web.txt tests/test_web_app.py
git commit -m "feat: add Flask web UI — invoice table, CSV export, secret token auth, Tailwind CSS"
```

---

## Task 8: Docker infrastructure

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Replace `docker-compose.yml`**

```yaml
services:
  traefik:
    image: traefik:v3.0
    container_name: rvc-traefik
    restart: always
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.httpchallenge=true
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
      - --certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    networks:
      - proxy

  rvc-invoices-bot:
    build: .
    container_name: rvc-invoices-bot
    restart: always
    env_file: .env
    volumes:
      - invoices_data:/app/data
      - invoices_logs:/app/logs
    depends_on:
      - rvc-minio
    networks:
      - proxy

  rvc-invoices-web:
    build:
      context: .
      dockerfile: Dockerfile.web
    container_name: rvc-invoices-web
    restart: always
    env_file: .env
    volumes:
      - invoices_data:/app/data
    depends_on:
      - rvc-invoices-bot
    networks:
      - proxy
    labels:
      - traefik.enable=true
      - traefik.http.routers.web.rule=Host(`${DOMAIN_WEB}`)
      - traefik.http.routers.web.entrypoints=websecure
      - traefik.http.routers.web.tls.certresolver=letsencrypt
      - traefik.http.routers.web-redirect.rule=Host(`${DOMAIN_WEB}`)
      - traefik.http.routers.web-redirect.entrypoints=web
      - traefik.http.routers.web-redirect.middlewares=redirect-to-https
      - traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https
      - traefik.http.services.web.loadbalancer.server.port=8080

  rvc-minio:
    image: minio/minio
    container_name: rvc-minio
    restart: always
    command: server /data --console-address ":9001"
    env_file: .env
    volumes:
      - minio_data:/data
    networks:
      - proxy
    labels:
      - traefik.enable=true
      - traefik.http.routers.minio.rule=Host(`${DOMAIN_MINIO}`)
      - traefik.http.routers.minio.entrypoints=websecure
      - traefik.http.routers.minio.tls.certresolver=letsencrypt
      - traefik.http.services.minio.loadbalancer.server.port=9000
      - traefik.http.routers.minio-console.rule=Host(`${DOMAIN_MINIO_CONSOLE}`)
      - traefik.http.routers.minio-console.entrypoints=websecure
      - traefik.http.routers.minio-console.tls.certresolver=letsencrypt
      - traefik.http.services.minio-console.loadbalancer.server.port=9001

volumes:
  invoices_data:
  invoices_logs:
  minio_data:
  letsencrypt:

networks:
  proxy:
    external: false
```

- [ ] **Step 2: Update `.env.example`**

Replace the entire `.env.example` with:
```env
IMAP_SERVER=mail.rvctel.vn
IMAP_PORT=993
IMAP_USER=invoices_bot@rvctel.vn
IMAP_PASSWORD=your_imap_password_here

GEMINI_API_KEY=your_gemini_api_key_here

TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

EMAIL_POLL_INTERVAL_MINUTES=15
DAILY_REPORT_TIME=08:00

RVC_TAX_CODE=0313028740

# MinIO
MINIO_ENDPOINT=rvc-minio:9000
MINIO_ACCESS_KEY=your_minio_access_key
MINIO_SECRET_KEY=your_minio_secret_key
MINIO_ROOT_USER=your_minio_access_key
MINIO_ROOT_PASSWORD=your_minio_secret_key
MINIO_BUCKET=rvc-invoices
MINIO_PUBLIC_URL=https://rvc-s3.rvctel.vn

# Web UI
WEB_PORT=8080
WEB_SECRET=your_web_secret_token

# Traefik / Domains
ACME_EMAIL=admin@rvctel.vn
DOMAIN_WEB=hddt.rvctel.vn
DOMAIN_MINIO=rvc-s3.rvctel.vn
DOMAIN_MINIO_CONSOLE=rvc-s3-console.rvctel.vn
```

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```bash
cd /home/ai/rvc-invoices-bot && python -m pytest tests/ -v --ignore=tests/test_email_handler.py
```
Expected: All tests PASS (ignore `test_email_handler.py` if it requires live IMAP).

- [ ] **Step 4: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add docker-compose.yml .env.example
git commit -m "feat: update docker-compose — add traefik, rvc-invoices-web, rvc-minio services"
```
