# rvc-invoices-bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated Vietnamese e-invoice email processing bot that extracts structured data from 4 source formats (XML, ZIP, PDF, web portal) and stores it in a unified CSV with daily Telegram reports and real-time error alerts.

**Architecture:** Single Python process in Docker (`rvc-invoices-bot` service), `schedule`-driven loop polling IMAP every 15 minutes and firing a daily 08:00 Telegram report. Four routing branches handle different email attachment types; all funnel into a unified 18-column CSV. Errors are appended to a separate `errors.csv` and immediately alerted via Telegram. `restart: always` ensures crash recovery.

**Tech Stack:** Python 3.11-slim, imap-tools, google-generativeai (gemini-2.0-flash), playwright (Chromium headless), schedule, requests (Telegram Bot API), pandas, python-dotenv, pytest, Docker Compose

---

## File Map

| File | Responsibility |
|------|---------------|
| `config.py` | Load `.env`, expose typed constants for all modules |
| `logger.py` | Configure rotating file + stdout logging, expose `setup_logging()` |
| `email_handler.py` | IMAP connection, fetch UNSEEN emails, mark as seen |
| `data_extractor.py` | Parse XML bytes → dict; parse PDF via Gemini → dict |
| `web_scraper.py` | Stage 1 direct download + Stage 2 Playwright provider registry |
| `router.py` | Detect branch, orchestrate extraction, write CSV, send alerts |
| `storage.py` | Append rows to `Tong_hop_hoa_don.csv` and `errors.csv` |
| `reporter.py` | Format + send daily Telegram report and real-time error alerts |
| `main.py` | Entry point: setup logging, schedule jobs, run loop |
| `Dockerfile` | Build image with Playwright Chromium |
| `docker-compose.yml` | Single service with named volumes |
| `tests/test_config.py` | Config loading tests |
| `tests/test_storage.py` | CSV create/append tests |
| `tests/test_email_handler.py` | IMAP fetch/filter tests (mocked) |
| `tests/test_data_extractor.py` | XML parse tests + Gemini mock tests |
| `tests/test_web_scraper.py` | Stage 1 direct download tests (mocked requests) |
| `tests/test_router.py` | Branch routing tests (all dependencies mocked) |
| `tests/test_reporter.py` | Telegram message format tests (mocked requests) |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.env`
- Create: `.gitignore`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `conftest.py` (project root, empty)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1.1: Create directory structure**

```bash
cd /home/ai/rvc-invoices-bot
mkdir -p data logs temp tests
git init
```

- [ ] **Step 1.2: Write `requirements.txt`**

```
imap-tools>=1.6.0
google-generativeai>=0.8.3
playwright>=1.44.0
schedule>=1.2.2
requests>=2.31.0
pandas>=2.1.0
python-dotenv>=1.0.1
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 1.3: Write `.env.example`**

```env
IMAP_SERVER=mail.<TARGET_DOMAIN>
IMAP_PORT=993
IMAP_USER=invoices_bot@<TARGET_DOMAIN>
IMAP_PASSWORD=your_imap_password_here

GEMINI_API_KEY=your_gemini_api_key_here

TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

EMAIL_POLL_INTERVAL_MINUTES=15
DAILY_REPORT_TIME=08:00

RVC_TAX_CODE=0313028740
```

- [ ] **Step 1.4: Write `.env`** (real credentials, never committed)

```env
IMAP_SERVER=mail.<TARGET_DOMAIN>
IMAP_PORT=993
IMAP_USER=invoices_bot@<TARGET_DOMAIN>
IMAP_PASSWORD=your_imap_password_here

GEMINI_API_KEY=your_gemini_api_key_here

TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

EMAIL_POLL_INTERVAL_MINUTES=15
DAILY_REPORT_TIME=08:00

RVC_TAX_CODE=0313028740
```

- [ ] **Step 1.5: Write `.gitignore`**

```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
data/
logs/
temp/
*.egg-info/
```

- [ ] **Step 1.6: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p data logs temp

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
```

- [ ] **Step 1.7: Write `docker-compose.yml`**

```yaml
version: '3.8'

services:
  rvc-invoices-bot:
    build: .
    container_name: rvc-invoices-bot
    restart: always
    env_file:
      - .env
    volumes:
      - invoices_data:/app/data
      - invoices_logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1

volumes:
  invoices_data:
  invoices_logs:
```

- [ ] **Step 1.8: Write `conftest.py` (project root)**

```python
```
(Empty file — marks project root as pytest root so all imports resolve correctly.)

- [ ] **Step 1.9: Write `tests/__init__.py`**

```python
```
(Empty file.)

- [ ] **Step 1.10: Write `tests/conftest.py`**

```python
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

- [ ] **Step 1.11: Commit scaffolding**

```bash
git add requirements.txt .env.example .gitignore Dockerfile docker-compose.yml conftest.py tests/
git commit -m "chore: initial project scaffolding"
```

---

### Task 2: `config.py` + `logger.py`

**Files:**
- Create: `config.py`
- Create: `logger.py`
- Create: `tests/test_config.py`

- [ ] **Step 2.1: Write failing test**

Create `tests/test_config.py`:

```python
import os
import importlib
from unittest.mock import patch


def test_config_default_values():
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
    }, clear=True):
        import config
        importlib.reload(config)
        assert config.IMAP_SERVER == "mail.example.com"
        assert config.IMAP_PORT == 993
        assert config.EMAIL_POLL_INTERVAL_MINUTES == 15
        assert config.DAILY_REPORT_TIME == "08:00"
        assert config.RVC_TAX_CODE == "0313028740"
        assert config.INVOICE_CSV.endswith("Tong_hop_hoa_don.csv")
        assert config.ERROR_CSV.endswith("errors.csv")
        assert config.LOG_FILE.endswith("bot.log")
```

- [ ] **Step 2.2: Run test — expect FAIL**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_config.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 2.3: Write `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "mail.<TARGET_DOMAIN>")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_POLL_INTERVAL_MINUTES = int(os.getenv("EMAIL_POLL_INTERVAL_MINUTES", "15"))
DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "08:00")

RVC_TAX_CODE = os.getenv("RVC_TAX_CODE", "0313028740")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
LOG_DIR = os.path.join(BASE_DIR, "logs")

INVOICE_CSV = os.path.join(DATA_DIR, "Tong_hop_hoa_don.csv")
ERROR_CSV = os.path.join(DATA_DIR, "errors.csv")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
```

- [ ] **Step 2.4: Write `logger.py`**

```python
import logging
import logging.handlers
import os


def setup_logging(log_file: str, log_dir: str) -> None:
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
```

- [ ] **Step 2.5: Install dependencies**

```bash
cd /home/ai/rvc-invoices-bot
pip install -r requirements.txt
```

Expected: all packages install successfully.

- [ ] **Step 2.6: Run test — expect PASS**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `1 passed`

- [ ] **Step 2.7: Commit**

```bash
git add config.py logger.py tests/test_config.py
git commit -m "feat: add config and logging setup"
```

---

### Task 3: `storage.py`

**Files:**
- Create: `storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_storage.py`:

```python
import csv
import os
from unittest.mock import patch


def test_ensure_csv_creates_file_with_headers(tmp_path):
    with patch("storage.INVOICE_CSV", str(tmp_path / "invoices.csv")), \
         patch("storage.ERROR_CSV", str(tmp_path / "errors.csv")):
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
    with patch("storage.INVOICE_CSV", str(tmp_path / "invoices.csv")):
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
    with patch("storage.INVOICE_CSV", str(tmp_path / "invoices.csv")):
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
    with patch("storage.ERROR_CSV", str(tmp_path / "errors.csv")):
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
```

- [ ] **Step 3.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_storage.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'storage'`

- [ ] **Step 3.3: Write `storage.py`**

```python
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
    "vat_rate", "total_vat_amount", "total_after_tax", "lookup_code", "lookup_website",
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
```

- [ ] **Step 3.4: Run tests — expect PASS**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: `4 passed`

- [ ] **Step 3.5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: add CSV storage module"
```

---

### Task 4: `email_handler.py`

**Files:**
- Create: `email_handler.py`
- Create: `tests/test_email_handler.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_email_handler.py`:

```python
from unittest.mock import MagicMock, patch
import pytest


def _make_mock_msg(uid, subject):
    msg = MagicMock()
    msg.uid = uid
    msg.subject = subject
    return msg


def test_fetch_filters_by_invoice_keywords():
    msgs = [
        _make_mock_msg("1", "Hóa đơn điện tử tháng 1"),
        _make_mock_msg("2", "Meeting reminder"),
        _make_mock_msg("3", "HDDT - Q1 invoice"),
        _make_mock_msg("4", "Gửi hóa đơn tháng 2"),
        _make_mock_msg("5", "Weekly report"),
    ]

    mock_mailbox = MagicMock()
    mock_mailbox.__enter__ = MagicMock(return_value=mock_mailbox)
    mock_mailbox.__exit__ = MagicMock(return_value=False)
    mock_mailbox.fetch.return_value = msgs

    with patch("email_handler.MailBox", return_value=mock_mailbox):
        from email_handler import fetch_unseen_emails
        result = fetch_unseen_emails()

    assert len(result) == 3
    uids = [m.uid for m in result]
    assert "1" in uids
    assert "3" in uids
    assert "4" in uids
    assert "2" not in uids
    assert "5" not in uids


def test_fetch_raises_on_imap_failure():
    with patch("email_handler.MailBox", side_effect=ConnectionError("Connection refused")):
        from email_handler import fetch_unseen_emails
        with pytest.raises(ConnectionError):
            fetch_unseen_emails()


def test_mark_as_seen_calls_flag():
    mock_mailbox = MagicMock()
    mock_mailbox.__enter__ = MagicMock(return_value=mock_mailbox)
    mock_mailbox.__exit__ = MagicMock(return_value=False)

    with patch("email_handler.MailBox", return_value=mock_mailbox):
        from email_handler import mark_as_seen
        mark_as_seen("42")

    mock_mailbox.flag.assert_called_once_with("42", ["\\Seen"], True)
```

- [ ] **Step 4.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_email_handler.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'email_handler'`

- [ ] **Step 4.3: Write `email_handler.py`**

```python
import logging

from imap_tools import AND, MailBox

from config import IMAP_PASSWORD, IMAP_PORT, IMAP_SERVER, IMAP_USER

logger = logging.getLogger(__name__)

SUBJECT_KEYWORDS = ["hóa đơn điện tử", "hóa đơn", "hddt"]


def fetch_unseen_emails() -> list:
    emails = []
    try:
        with MailBox(IMAP_SERVER, port=IMAP_PORT).login(
            IMAP_USER, IMAP_PASSWORD, initial_folder="INBOX"
        ) as mailbox:
            for msg in mailbox.fetch(AND(seen=False), mark_seen=False):
                subject_lower = (msg.subject or "").lower()
                if any(kw in subject_lower for kw in SUBJECT_KEYWORDS):
                    emails.append(msg)
                    logger.info(f"Matched email: uid={msg.uid} subject='{msg.subject}'")
    except Exception as e:
        logger.error(f"IMAP fetch failed: {e}")
        raise
    return emails


def mark_as_seen(uid: str) -> None:
    try:
        with MailBox(IMAP_SERVER, port=IMAP_PORT).login(
            IMAP_USER, IMAP_PASSWORD, initial_folder="INBOX"
        ) as mailbox:
            mailbox.flag(uid, ["\\Seen"], True)
            logger.info(f"Marked as seen: uid={uid}")
    except Exception as e:
        logger.error(f"Failed to mark seen uid={uid}: {e}")
```

- [ ] **Step 4.4: Run tests — expect PASS**

```bash
python -m pytest tests/test_email_handler.py -v
```

Expected: `3 passed`

- [ ] **Step 4.5: Commit**

```bash
git add email_handler.py tests/test_email_handler.py
git commit -m "feat: add IMAP email handler"
```

---

### Task 5: `data_extractor.py` — XML parsing

**Files:**
- Create: `data_extractor.py`
- Create: `tests/test_data_extractor.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_data_extractor.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

# Realistic Vietnamese e-invoice XML with namespaces
SAMPLE_XML_PURCHASE = b"""<?xml version="1.0" encoding="UTF-8"?>
<HDon xmlns="http://laphoadon.gdt.gov.vn/2014/09/xmlInvoiceDataFmt/v1">
  <DLHDon>
    <TTChung>
      <KHMSHDon>1</KHMSHDon>
      <KHHDon>C24TKQ</KHHDon>
      <SHDon>000123</SHDon>
      <NLap>2024-01-15</NLap>
      <HTToan>Chuyển khoản</HTToan>
      <MaQRCode>MKKUXJMAG</MaQRCode>
    </TTChung>
    <NDHDon>
      <NBan>
        <Ten>C\xf4ng ty CP Petrolimex</Ten>
        <MST>0100109106</MST>
        <DChi>22 H\xe0ng Dầu, H\xe0 Nội</DChi>
        <STKNHang>102010000123456</STKNHang>
      </NBan>
      <NMua>
        <Ten>C\xf4ng ty TNHH RVC</Ten>
        <MST>0313028740</MST>
        <DChi>123 Nguyễn Văn Linh, Q7, TP.HCM</DChi>
      </NMua>
      <TToan>
        <TgTCThue>10000000</TgTCThue>
        <DSHHTDVu>
          <HHDVu>
            <TSuat>10%</TSuat>
          </HHDVu>
        </DSHHTDVu>
        <TgTThue>1000000</TgTThue>
        <TgTTTBSo>11000000</TgTTTBSo>
      </TToan>
    </NDHDon>
  </DLHDon>
</HDon>"""

# Same XML but seller_tax_code == RVC's tax code → SALE
SAMPLE_XML_SALE = SAMPLE_XML_PURCHASE.replace(
    b"<MST>0100109106</MST>", b"<MST>0313028740</MST>", 1
).replace(
    b"<MST>0313028740</MST>", b"<MST>9999999999</MST>", 1
)


def test_parse_xml_all_fields():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)

    assert result["invoice_symbol"] == "1C24TKQ"
    assert result["invoice_number"] == "000123"
    assert result["issue_date"] == "2024-01-15"
    assert result["lookup_code"] == "MKKUXJMAG"
    assert result["seller_tax_code"] == "0100109106"
    assert result["buyer_tax_code"] == "0313028740"
    assert result["payment_method"] == "Chuyển khoản"
    assert result["bank_account"] == "102010000123456"
    assert result["total_before_tax"] == 10000000.0
    assert result["vat_rate"] == "10%"
    assert result["total_vat_amount"] == 1000000.0
    assert result["total_after_tax"] == 11000000.0


def test_parse_xml_invoice_type_purchase():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result["invoice_type"] == "PURCHASE"


def test_parse_xml_invoice_type_sale():
    from data_extractor import parse_xml
    # SALE_XML has seller_tax_code == "0313028740"
    sale_xml = SAMPLE_XML_PURCHASE.replace(
        b"<MST>0100109106</MST>", b"<MST>0313028740</MST>", 1
    )
    result = parse_xml(sale_xml)
    assert result["invoice_type"] == "SALE"


def test_parse_xml_strips_namespaces():
    from data_extractor import parse_xml
    # Should not raise even though XML has namespace declarations
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result["invoice_number"] is not None


def test_parse_xml_raises_on_invalid_xml():
    from data_extractor import parse_xml
    with pytest.raises(ValueError, match="XML parse error"):
        parse_xml(b"this is not < valid xml >>>")


def test_to_float_handles_none():
    from data_extractor import _to_float
    assert _to_float(None) is None


def test_to_float_parses_numeric_string():
    from data_extractor import _to_float
    assert _to_float("10000000") == 10000000.0
    assert _to_float("1,000,000") == 1000000.0


def test_determine_invoice_type_sale():
    from data_extractor import _determine_invoice_type
    with patch("data_extractor.RVC_TAX_CODE", "0313028740"):
        assert _determine_invoice_type("0313028740") == "SALE"


def test_determine_invoice_type_purchase():
    from data_extractor import _determine_invoice_type
    with patch("data_extractor.RVC_TAX_CODE", "0313028740"):
        assert _determine_invoice_type("9999999999") == "PURCHASE"
        assert _determine_invoice_type(None) == "PURCHASE"
```

- [ ] **Step 5.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_data_extractor.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'data_extractor'`

- [ ] **Step 5.3: Write `data_extractor.py` (XML portion + helpers)**

```python
import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET

import google.generativeai as genai

from config import GEMINI_API_KEY, RVC_TAX_CODE

logger = logging.getLogger(__name__)

GEMINI_PROMPT = """Bạn là trợ lý trích xuất dữ liệu hóa đơn điện tử Việt Nam.
Trích xuất thông tin từ file PDF hóa đơn và trả về JSON với định dạng chính xác sau.
QUAN TRỌNG: Chỉ trả về JSON thuần túy, KHÔNG có văn bản hay markdown khác.

{
  "invoice_symbol": "ký hiệu hóa đơn hoặc null",
  "invoice_number": "số hóa đơn hoặc null",
  "issue_date": "ngày lập YYYY-MM-DD hoặc null",
  "lookup_code": "mã tra cứu hoặc null",
  "lookup_website": "website tra cứu hoặc null",
  "seller_name": "tên người bán hoặc null",
  "seller_tax_code": "mã số thuế người bán hoặc null",
  "seller_address": "địa chỉ người bán hoặc null",
  "buyer_name": "tên người mua hoặc null",
  "buyer_tax_code": "mã số thuế người mua hoặc null",
  "buyer_address": "địa chỉ người mua hoặc null",
  "payment_method": "hình thức thanh toán hoặc null",
  "bank_account": "số tài khoản ngân hàng hoặc null",
  "total_before_tax": số_thực_hoặc_null,
  "vat_rate": "thuế suất ví dụ '10%' hoặc null",
  "total_vat_amount": số_thực_hoặc_null,
  "total_after_tax": số_thực_hoặc_null
}"""


def _strip_namespaces(xml_str: str) -> str:
    return re.sub(r"\{[^}]+\}", "", xml_str)


def _find_text(root: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            return el.text.strip()
    return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _determine_invoice_type(seller_tax_code: str | None) -> str:
    return "SALE" if seller_tax_code == RVC_TAX_CODE else "PURCHASE"


def parse_xml(xml_bytes: bytes) -> dict:
    try:
        xml_str = xml_bytes.decode("utf-8", errors="replace")
        xml_str = _strip_namespaces(xml_str)
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    nban = root.find(".//NBan") or root
    nmua = root.find(".//NMua") or root
    hhdvu = root.find(".//HHDVu")

    seller_tax_code = _find_text(nban, "MST", "MaSoThue")
    symbol_part1 = _find_text(root, "KHMSHDon") or ""
    symbol_part2 = _find_text(root, "KHHDon") or ""

    return {
        "invoice_type": _determine_invoice_type(seller_tax_code),
        "invoice_symbol": (symbol_part1 + symbol_part2).strip() or None,
        "invoice_number": _find_text(root, "SHDon", "SoHoaDon"),
        "issue_date": _find_text(root, "NLap", "NgayLap"),
        "lookup_code": _find_text(
            root, "MaQRCode", "MTra", "MCCQT", "MaTraCuu", "MaKiemTra"
        ),
        "lookup_website": None,
        "seller_name": _find_text(nban, "Ten"),
        "seller_tax_code": seller_tax_code,
        "seller_address": _find_text(nban, "DChi", "DiaChiNBan"),
        "buyer_name": _find_text(nmua, "Ten"),
        "buyer_tax_code": _find_text(nmua, "MST", "MaSoThue"),
        "buyer_address": _find_text(nmua, "DChi"),
        "payment_method": _find_text(root, "HTToan", "HinhThucThanhToan"),
        "bank_account": _find_text(nban, "STKNHang", "SoTK", "TaiKhoanNH"),
        "total_before_tax": _to_float(_find_text(root, "TgTCThue", "TongTienChuaThue")),
        "vat_rate": _find_text(hhdvu, "TSuat", "ThueSuat") if hhdvu is not None else None,
        "total_vat_amount": _to_float(_find_text(root, "TgTThue", "TongTienThue")),
        "total_after_tax": _to_float(_find_text(root, "TgTTTBSo", "TongTienThanhToan")),
    }


def parse_pdf_via_gemini(pdf_bytes: bytes) -> dict:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        uploaded = genai.upload_file(tmp_path, mime_type="application/pdf")
        response = model.generate_content([GEMINI_PROMPT, uploaded])
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}")
    finally:
        os.unlink(tmp_path)

    data["invoice_type"] = _determine_invoice_type(data.get("seller_tax_code"))
    return data
```

- [ ] **Step 5.4: Run XML tests — expect PASS**

```bash
python -m pytest tests/test_data_extractor.py -v -k "not gemini"
```

Expected: `9 passed`

- [ ] **Step 5.5: Commit XML parser**

```bash
git add data_extractor.py tests/test_data_extractor.py
git commit -m "feat: add XML data extractor with namespace stripping"
```

---

### Task 6: `data_extractor.py` — Gemini PDF parsing

**Files:**
- Modify: `tests/test_data_extractor.py` (add Gemini tests)

- [ ] **Step 6.1: Add Gemini tests to `tests/test_data_extractor.py`**

Append to the existing file:

```python
def test_parse_pdf_via_gemini_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    mock_response = MagicMock()
    mock_response.text = (
        '{"invoice_number": "001", "seller_tax_code": "0100109106",'
        ' "total_after_tax": 5500000, "seller_name": "Cty ABC"}'
    )
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("data_extractor.genai.configure"), \
         patch("data_extractor.genai.GenerativeModel", return_value=mock_model), \
         patch("data_extractor.genai.upload_file", return_value=MagicMock()), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_number"] == "001"
    assert result["invoice_type"] == "PURCHASE"
    assert result["total_after_tax"] == 5500000
    assert result["seller_name"] == "Cty ABC"


def test_parse_pdf_via_gemini_strips_markdown_fences(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = '```json\n{"invoice_number": "002", "seller_tax_code": null}\n```'
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("data_extractor.genai.configure"), \
         patch("data_extractor.genai.GenerativeModel", return_value=mock_model), \
         patch("data_extractor.genai.upload_file", return_value=MagicMock()), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_number"] == "002"


def test_parse_pdf_via_gemini_raises_on_invalid_json(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = "Không thể trích xuất dữ liệu từ file này."
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("data_extractor.genai.configure"), \
         patch("data_extractor.genai.GenerativeModel", return_value=mock_model), \
         patch("data_extractor.genai.upload_file", return_value=MagicMock()), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_pdf_via_gemini(b"%PDF-1.4")


def test_parse_pdf_via_gemini_sets_sale_type(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = '{"invoice_number": "003", "seller_tax_code": "0313028740"}'
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("data_extractor.genai.configure"), \
         patch("data_extractor.genai.GenerativeModel", return_value=mock_model), \
         patch("data_extractor.genai.upload_file", return_value=MagicMock()), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        with patch("data_extractor.RVC_TAX_CODE", "0313028740"):
            from data_extractor import parse_pdf_via_gemini
            result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_type"] == "SALE"
```

- [ ] **Step 6.2: Run all data_extractor tests — expect PASS**

```bash
python -m pytest tests/test_data_extractor.py -v
```

Expected: `13 passed`

- [ ] **Step 6.3: Commit**

```bash
git add tests/test_data_extractor.py
git commit -m "feat: add Gemini PDF extraction tests"
```

---

### Task 7: `web_scraper.py` — Stage 1 direct download

**Files:**
- Create: `web_scraper.py`
- Create: `tests/test_web_scraper.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_web_scraper.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def test_try_direct_download_xml_by_content_type():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml; charset=utf-8"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_scraper.requests.get", return_value=mock_resp):
        from web_scraper import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC123"]
        )

    assert result is not None
    content, ctype = result
    assert ctype == "xml"
    assert b"<?xml" in content


def test_try_direct_download_xml_by_magic_bytes():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/octet-stream"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_scraper.requests.get", return_value=mock_resp):
        from web_scraper import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/invoice/file?token=XYZ"]
        )

    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_try_direct_download_pdf_by_magic_bytes():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/octet-stream"}
    mock_resp.content = b"%PDF-1.4 fake pdf content"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_scraper.requests.get", return_value=mock_resp):
        from web_scraper import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC"]
        )

    assert result is not None
    _, ctype = result
    assert ctype == "pdf"


def test_try_direct_download_skips_non_matching_urls():
    from web_scraper import _try_direct_download
    result = _try_direct_download(
        ["https://example.com/about-us", "https://www.google.com"]
    )
    assert result is None


def test_try_direct_download_returns_none_on_request_failure():
    with patch("web_scraper.requests.get", side_effect=Exception("timeout")):
        from web_scraper import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC"]
        )
    assert result is None


def test_extract_lookup_code_misa_pattern():
    from web_scraper import _extract_lookup_code
    assert _extract_lookup_code("mã số: ABC123XYZ") == "ABC123XYZ"


def test_extract_lookup_code_common_pattern():
    from web_scraper import _extract_lookup_code
    assert _extract_lookup_code("mã tra cứu: MKKUXJMAG") == "MKKUXJMAG"


def test_extract_lookup_code_vnpt_pattern():
    from web_scraper import _extract_lookup_code
    assert _extract_lookup_code("Mã nhận hóa đơn: VNPT2024ABC") == "VNPT2024ABC"


def test_extract_lookup_code_viettel_pattern():
    from web_scraper import _extract_lookup_code
    assert _extract_lookup_code("Mã bí mật: VT_SECRET_123") == "VT_SECRET_123"


def test_extract_lookup_code_returns_none_when_not_found():
    from web_scraper import _extract_lookup_code
    assert _extract_lookup_code("no code here at all") is None


def test_extract_urls_finds_https_urls():
    from web_scraper import _extract_urls
    text = "Click https://www.meinvoice.vn/tra-cuu to view your invoice"
    urls = _extract_urls(text)
    assert "https://www.meinvoice.vn/tra-cuu" in urls


def test_download_invoice_file_stage1_xml_success():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    body = "Download: https://hoadon.petrolimex.com.vn/download?token=XYZ123"
    with patch("web_scraper.requests.get", return_value=mock_resp):
        from web_scraper import download_invoice_file
        content, ctype = download_invoice_file(body, "")

    assert ctype == "xml"
    assert b"<?xml" in content


def test_download_invoice_file_raises_when_no_url_no_code():
    from web_scraper import download_invoice_file
    with pytest.raises(ValueError):
        download_invoice_file("Nothing useful here.", "")


def test_download_invoice_file_raises_unsupported_domain():
    from web_scraper import download_invoice_file
    body = "mã tra cứu: ABC123\nhttps://unknown-portal.vn/invoice"
    with pytest.raises(ValueError, match="Unsupported"):
        download_invoice_file(body, "")
```

- [ ] **Step 7.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_web_scraper.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'web_scraper'`

- [ ] **Step 7.3: Write `web_scraper.py`**

```python
import logging
import re
import time
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

DIRECT_LINK_RE = re.compile(
    r"(token=|/download|/file|\.xml|\.pdf|/invoice|hoadon|tra-cuu)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)
REGEX_PATTERNS = [
    re.compile(r"mã số[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"mã tra cứu[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"mã nhận hóa đơn[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"Mã bí mật[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def _extract_lookup_code(text: str) -> str | None:
    for pattern in REGEX_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _try_direct_download(urls: list[str]) -> tuple[bytes, str] | None:
    for url in urls:
        if not DIRECT_LINK_RE.search(url):
            continue
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "xml" in ct or resp.content.strip().startswith(b"<?xml"):
                logger.info(f"Direct XML download: {url}")
                return resp.content, "xml"
            if "pdf" in ct or resp.content[:4] == b"%PDF":
                logger.info(f"Direct PDF download: {url}")
                return resp.content, "pdf"
        except Exception as e:
            logger.debug(f"Direct download failed {url}: {e}")
    return None


def _playwright_download(page, xml_selectors: list[str]) -> bytes:
    with page.expect_download(timeout=30000) as dl:
        for sel in xml_selectors:
            try:
                page.click(sel, timeout=5000)
                break
            except Exception:
                continue
    download = dl.value
    path = download.path()
    with open(path, "rb") as f:
        return f.read()


def scrape_misa(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto("https://www.meinvoice.vn/tra-cuu", wait_until="networkidle", timeout=30000)
        page.fill(
            'input[placeholder*="mã"], input[id*="code"], input[name*="code"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button[type="submit"], button:has-text("Tra cứu"), button:has-text("Tìm kiếm")')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'button:has-text("Tải XML")', 'a[href*=".xml"]'],
        )
        browser.close()
        return data


def scrape_petrolimex(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.fill(
            'input[id*="lookup"], input[name*="lookup"], input[placeholder*="mã"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button[type="submit"], button:has-text("Tra cứu"), input[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*="xml"]', 'button:has-text("XML")'],
        )
        browser.close()
        return data


def scrape_viettel(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(
            "https://vietteltelecom.vn/hoadondientu",
            wait_until="networkidle",
            timeout=30000,
        )
        page.fill(
            'input[placeholder*="bí mật"], input[name*="secret"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button:has-text("Tra cứu"), button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("Tải XML")'],
        )
        browser.close()
        return data


def scrape_vnpt(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(
            "https://vnpt-invoice.com.vn/invoice",
            wait_until="networkidle",
            timeout=30000,
        )
        page.fill(
            'input[placeholder*="mã"], input[id*="invoice"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button:has-text("Tra cứu"), button:has-text("Tìm"), button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("XML")'],
        )
        browser.close()
        return data


def scrape_generic(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        inputs = page.query_selector_all("input[type='text']")
        if inputs:
            inputs[0].fill(code)
        page.click('button[type="submit"], button:has-text("Tra cứu")')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a[href*="xml"]', 'a:has-text("XML")', 'button:has-text("XML")'],
        )
        browser.close()
        return data


SCRAPERS: dict = {
    "hoadon.petrolimex.com.vn": scrape_petrolimex,
    "vietteltelecom.vn": scrape_viettel,
    "vnpt-invoice.com.vn": scrape_vnpt,
    "www.meinvoice.vn": scrape_misa,
}


def download_invoice_file(body_text: str, body_html: str) -> tuple[bytes, str]:
    combined = (body_text or "") + " " + (body_html or "")
    all_urls = _extract_urls(combined)

    # Stage 1: Try direct token/download link
    result = _try_direct_download(all_urls)
    if result is not None:
        return result

    # Stage 2: Playwright lookup form
    code = _extract_lookup_code(combined)
    portal_url = None
    for url in all_urls:
        domain = urlparse(url).netloc
        if domain in SCRAPERS:
            portal_url = url
            break

    if not code:
        raise ValueError("No lookup code found in email body")

    if not portal_url:
        found_domains = {urlparse(u).netloc for u in all_urls if urlparse(u).netloc}
        unsupported = found_domains - set(SCRAPERS.keys())
        if unsupported:
            raise ValueError(f"Unsupported provider domain(s): {', '.join(unsupported)}")
        raise ValueError("No known portal URL found in email body")

    domain = urlparse(portal_url).netloc
    scraper_fn = SCRAPERS.get(domain, scrape_generic)

    for attempt in range(2):
        try:
            xml_bytes = scraper_fn(portal_url, code)
            logger.info(f"Playwright download success: domain={domain} code={code}")
            return xml_bytes, "xml"
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Playwright attempt 1 failed ({domain}): {e}, retrying in 3s")
                time.sleep(3)
            else:
                raise
```

- [ ] **Step 7.4: Run tests — expect PASS**

```bash
python -m pytest tests/test_web_scraper.py -v
```

Expected: `13 passed`

- [ ] **Step 7.5: Commit**

```bash
git add web_scraper.py tests/test_web_scraper.py
git commit -m "feat: add web scraper with Stage 1 direct download and Stage 2 Playwright registry"
```

---

### Task 8: `router.py`

**Files:**
- Create: `router.py`
- Create: `tests/test_router.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_router.py`:

```python
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


def test_branch_xml_calls_parse_xml():
    att = _make_attachment("invoice.xml", b"<xml/>")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_parse.assert_called_once_with(b"<xml/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "XML"
    assert stored["source_email_subject"] == "Hóa đơn test"
    assert "processed_date" in stored


def test_branch_zip_extracts_and_parses_xml(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("invoice.xml", b"<?xml version='1.0'?><HDon/>")
    zip_bytes = buf.getvalue()

    att = _make_attachment("invoice.zip", zip_bytes)
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "002"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.TEMP_DIR", str(tmp_path)):

        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "ZIP"


def test_branch_pdf_calls_gemini():
    att = _make_attachment("invoice.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "003"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF-1.4")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "PDF"


def test_branch_web_xml_path():
    email = _make_email(
        text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu"
    )

    with patch("router.web_scraper.download_invoice_file", return_value=(b"<HDon/>", "xml")) as mock_web, \
         patch("router.data_extractor.parse_xml", return_value={"invoice_number": "004"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_web.assert_called_once()
    mock_parse.assert_called_once_with(b"<HDon/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_branch_web_pdf_path():
    email = _make_email(
        text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu"
    )

    with patch("router.web_scraper.download_invoice_file", return_value=(b"%PDF", "pdf")), \
         patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "005"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_error_sends_alert_and_logs_error():
    att = _make_attachment("invoice.xml", b"bad xml")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=ValueError("XML parse error")), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.storage.append_error") as mock_err, \
         patch("router.reporter.send_error_alert") as mock_alert, \
         patch("router.email_handler.mark_as_seen"):

        from router import process_email
        process_email(email)

    mock_store.assert_not_called()
    mock_err.assert_called_once()
    err_data = mock_err.call_args[0][0]
    assert err_data["branch"] == "XML"
    assert err_data["email_subject"] == "Hóa đơn test"
    mock_alert.assert_called_once()


def test_mark_as_seen_always_called_even_on_error():
    att = _make_attachment("invoice.xml", b"bad")
    email = _make_email(uid="99", attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=Exception("Boom")), \
         patch("router.storage.append_error"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.email_handler.mark_as_seen") as mock_seen:

        from router import process_email
        process_email(email)

    mock_seen.assert_called_once_with("99")


def test_xml_takes_priority_over_zip_and_pdf():
    xml_att = _make_attachment("invoice.xml", b"<xml/>")
    pdf_att = _make_attachment("invoice.pdf", b"%PDF")
    zip_att = _make_attachment("archive.zip", b"PK")
    email = _make_email(attachments=[xml_att, pdf_att, zip_att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001"}) as mock_xml, \
         patch("router.data_extractor.parse_pdf_via_gemini") as mock_pdf, \
         patch("router.storage.append_invoice"), \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_xml.assert_called_once()
    mock_pdf.assert_not_called()
```

- [ ] **Step 8.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_router.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'router'`

- [ ] **Step 8.3: Write `router.py`**

```python
import logging
import os
import shutil
import zipfile
from datetime import datetime

import data_extractor
import email_handler
import reporter
import storage
import web_scraper
from config import TEMP_DIR

logger = logging.getLogger(__name__)


def _find_attachment(email, extension: str):
    for att in email.attachments:
        if (att.filename or "").lower().endswith(extension):
            return att
    return None


def process_email(email) -> None:
    subject = email.subject or ""
    sender = str(email.from_)
    email_time = email.date.strftime("%H:%M") if email.date else ""
    branch = "UNKNOWN"

    try:
        xml_att = _find_attachment(email, ".xml")
        zip_att = _find_attachment(email, ".zip")
        pdf_att = _find_attachment(email, ".pdf")

        if xml_att:
            branch = "XML"
            logger.info(f"Branch XML | uid={email.uid} | subject='{subject}'")
            data = data_extractor.parse_xml(xml_att.payload)

        elif zip_att:
            branch = "ZIP"
            logger.info(f"Branch ZIP | uid={email.uid} | subject='{subject}'")
            uid_temp = os.path.join(TEMP_DIR, str(email.uid))
            os.makedirs(uid_temp, exist_ok=True)
            try:
                zip_path = os.path.join(uid_temp, "invoice.zip")
                with open(zip_path, "wb") as f:
                    f.write(zip_att.payload)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(uid_temp)
                xml_file = next(
                    (
                        os.path.join(root, fn)
                        for root, _, files in os.walk(uid_temp)
                        for fn in files
                        if fn.lower().endswith(".xml")
                    ),
                    None,
                )
                if not xml_file:
                    raise FileNotFoundError("No XML file found inside ZIP")
                with open(xml_file, "rb") as f:
                    data = data_extractor.parse_xml(f.read())
            finally:
                shutil.rmtree(uid_temp, ignore_errors=True)

        elif pdf_att:
            branch = "PDF"
            logger.info(f"Branch PDF | uid={email.uid} | subject='{subject}'")
            data = data_extractor.parse_pdf_via_gemini(pdf_att.payload)

        else:
            branch = "WEB"
            logger.info(f"Branch WEB | uid={email.uid} | subject='{subject}'")
            file_bytes, content_type = web_scraper.download_invoice_file(
                email.text or "", email.html or ""
            )
            if content_type == "xml":
                data = data_extractor.parse_xml(file_bytes)
            else:
                data = data_extractor.parse_pdf_via_gemini(file_bytes)

        data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["source_branch"] = branch
        data["source_email_subject"] = subject
        storage.append_invoice(data)
        logger.info(f"Invoice saved | branch={branch} | number={data.get('invoice_number')}")

    except Exception as e:
        logger.error(
            f"Error processing email uid={email.uid} branch={branch}: {e}",
            exc_info=True,
        )
        reporter.send_error_alert(subject, branch, str(e))
        storage.append_error(
            {
                "error_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email_sender": sender,
                "email_time": email_time,
                "email_subject": subject,
                "branch": branch,
                "error_message": str(e),
            }
        )
    finally:
        email_handler.mark_as_seen(email.uid)
```

- [ ] **Step 8.4: Run tests — expect PASS**

```bash
python -m pytest tests/test_router.py -v
```

Expected: `8 passed`

- [ ] **Step 8.5: Commit**

```bash
git add router.py tests/test_router.py
git commit -m "feat: add email router with 4-branch processing"
```

---

### Task 9: `reporter.py`

**Files:**
- Create: `reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 9.1: Write failing tests**

Create `tests/test_reporter.py`:

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
        send_error_alert("subject", "XML", "error")  # must not raise


def test_send_daily_report_invoice_summary():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 09:00:00", "invoice_type": "PURCHASE", "total_after_tax": 5000000.0},
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 3000000.0},
        {"processed_date": f"{yesterday} 11:00:00", "invoice_type": "SALE",     "total_after_tax": 8000000.0},
    ])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, FileNotFoundError()]), \
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
    err_df = pd.DataFrame([
        {
            "error_date": f"{yesterday} 09:05:00",
            "email_sender": "supplier@abc.com",
            "email_time": "09:05",
            "email_subject": "Hóa đơn XYZ",
            "branch": "ZIP",
            "error_message": "Corrupt ZIP file",
        }
    ])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, err_df]), \
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
    err_df = pd.DataFrame(columns=["error_date", "email_sender", "email_time", "email_subject", "branch", "error_message"])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Lỗi" not in body


def test_send_daily_report_handles_missing_invoice_csv():
    with patch("reporter.pd.read_csv", side_effect=FileNotFoundError()), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["text"]
    assert "Tổng số hóa đơn: 0" in body
```

- [ ] **Step 9.2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_reporter.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'reporter'`

- [ ] **Step 9.3: Write `reporter.py`**

```python
import logging
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import ERROR_CSV, INVOICE_CSV, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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
        inv_df = pd.read_csv(INVOICE_CSV, encoding="utf-8")
        inv_df["processed_date"] = pd.to_datetime(inv_df["processed_date"])
        inv_yday = inv_df[inv_df["processed_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
    except FileNotFoundError:
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
        err_df = pd.read_csv(ERROR_CSV, encoding="utf-8")
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
    except FileNotFoundError:
        pass

    _send_telegram("\n".join(lines))
    logger.info(f"Daily report sent for {report_date}")
```

- [ ] **Step 9.4: Run tests — expect PASS**

```bash
python -m pytest tests/test_reporter.py -v
```

Expected: `6 passed`

- [ ] **Step 9.5: Commit**

```bash
git add reporter.py tests/test_reporter.py
git commit -m "feat: add Telegram reporter with daily summary and error alerts"
```

---

### Task 10: `main.py` + Full Test Suite

**Files:**
- Create: `main.py`

- [ ] **Step 10.1: Write `main.py`**

```python
import logging
import time

import schedule

import email_handler
import reporter
import router
from config import DAILY_REPORT_TIME, EMAIL_POLL_INTERVAL_MINUTES, LOG_DIR, LOG_FILE
from logger import setup_logging

setup_logging(LOG_FILE, LOG_DIR)
logger = logging.getLogger(__name__)


def poll_emails() -> None:
    logger.info("Polling for new invoice emails...")
    try:
        emails = email_handler.fetch_unseen_emails()
        logger.info(f"Found {len(emails)} invoice email(s) to process")
        for email in emails:
            router.process_email(email)
    except Exception as e:
        logger.error(f"Poll cycle failed: {e}", exc_info=True)


def main() -> None:
    logger.info("rvc-invoices-bot starting up")
    logger.info(f"Poll interval: {EMAIL_POLL_INTERVAL_MINUTES} minutes")
    logger.info(f"Daily report time: {DAILY_REPORT_TIME}")

    schedule.every(EMAIL_POLL_INTERVAL_MINUTES).minutes.do(poll_emails)
    schedule.every().day.at(DAILY_REPORT_TIME).do(reporter.send_daily_report)

    poll_emails()  # Immediate first run on startup

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10.2: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass. Fix any failures before continuing.

- [ ] **Step 10.3: Commit**

```bash
git add main.py
git commit -m "feat: add main entry point with schedule loop"
```

---

### Task 11: Docker Build & Verification

**Files:** No new files — verify existing Dockerfile and docker-compose.yml work.

- [ ] **Step 11.1: Verify `.env` has real credentials filled in**

Check that `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are set in `.env` before building.

- [ ] **Step 11.2: Build Docker image**

```bash
cd /home/ai/rvc-invoices-bot
docker compose build
```

Expected: image builds successfully. Playwright Chromium is installed inside the image. Build takes 3–8 minutes on first run.

- [ ] **Step 11.3: Start container and verify startup logs**

```bash
docker compose up -d
sleep 5
docker logs rvc-invoices-bot --tail 30
```

Expected output (lines similar to):
```
2026-04-28 08:00:00 | INFO     | __main__ | rvc-invoices-bot starting up
2026-04-28 08:00:00 | INFO     | __main__ | Poll interval: 15 minutes
2026-04-28 08:00:00 | INFO     | __main__ | Daily report time: 08:00
2026-04-28 08:00:00 | INFO     | __main__ | Polling for new invoice emails...
2026-04-28 08:00:01 | INFO     | __main__ | Found 0 invoice email(s) to process
```

If you see `IMAP fetch failed`, check IMAP credentials in `.env`.

- [ ] **Step 11.4: Verify named volumes are created**

```bash
docker volume ls | grep rvc
```

Expected:
```
local     rvc-invoices-bot_invoices_data
local     rvc-invoices-bot_invoices_logs
```

- [ ] **Step 11.5: Stop container**

```bash
docker compose down
```

- [ ] **Step 11.6: Final commit**

```bash
git add .
git commit -m "chore: verify docker build and container startup"
```

---

## Self-Review Checklist

After completing all tasks, verify:

- [ ] `storage.INVOICE_COLUMNS` has exactly 18 columns matching the spec schema
- [ ] `_determine_invoice_type` compares against `RVC_TAX_CODE` from config (not hardcoded)
- [ ] Branch 4 Stage 1 is attempted before Stage 2 in `web_scraper.download_invoice_file()`
- [ ] Playwright retry fires exactly once (2 total attempts) with 3s sleep between
- [ ] `email_handler.mark_as_seen()` is called in the `finally` block of `router.process_email()` — always executes
- [ ] ZIP temp directory is always cleaned up in `finally` block
- [ ] Daily report error section is omitted when 0 errors
- [ ] `data/` and `logs/` are mounted as named Docker volumes (data survives container restart)
- [ ] CSV encoding is `utf-8` (not `utf-8-sig`)
- [ ] Gemini model is `gemini-2.0-flash` (not flash-lite or pro)
