# rvc-invoices-bot — Design Specification
**Date:** 2026-04-28  
**Project:** Vietnamese E-Invoice (Hóa đơn điện tử) Automated Processing Bot  
**Status:** Approved

---

## 1. Overview

An automated bot that watches a dedicated mailbox (`invoices_bot@rvctel.vn`) for Vietnamese e-invoice emails, extracts invoice data from multiple source formats (XML, ZIP, PDF, web portal), stores it in a unified CSV, and sends a daily Telegram summary report. The system runs as a single Docker container with a 15-minute IMAP polling loop.

---

## 2. Project Structure

```
/home/ai/rvc-invoices-bot/
├── docker-compose.yml
├── Dockerfile
├── .env                          # secrets/config — gitignored
├── .env.example                  # safe template to commit
├── requirements.txt
├── README.md
│
├── main.py                       # entry point: schedule loop
├── config.py                     # loads .env, exposes typed constants
├── email_handler.py              # Module 1: IMAP watcher
├── router.py                     # Module 2: attachment routing logic
├── web_scraper.py                # Module 2 Branch 4: Playwright + provider registry
├── data_extractor.py             # Module 3: XML/PDF parsing → unified schema
├── storage.py                    # Module 3: CSV append logic
├── reporter.py                   # Module 4: daily Telegram summary + error alerts
│
├── data/
│   ├── Tong_hop_hoa_don.csv     # persistent invoice store (Docker named volume)
│   └── errors.csv               # error log: sender, time, subject, branch, message
├── temp/                         # ephemeral ZIP extraction dir (cleaned after each email)
└── logs/
    └── bot.log                   # rotating log file (Docker named volume)
```

---

## 3. Architecture & Data Flow

### Main Loop (`main.py`)

- `schedule` runs two jobs:
  - Every **15 minutes**: `email_handler.fetch_unseen_emails()` → `router.process_email(email)` for each result
  - Daily at **08:00**: `reporter.send_daily_report()`
- Docker `restart: always` ensures recovery from crashes.

### Routing Logic (`router.py`)

Branch priority (top-to-bottom, first match wins):

| Priority | Condition | Branch | Parser |
|----------|-----------|--------|--------|
| 1 | `.xml` attachment present | XML | `data_extractor.parse_xml()` |
| 2 | `.zip` attachment present | ZIP | Extract → find `.xml` → `data_extractor.parse_xml()` → cleanup `temp/` |
| 3 | `.pdf` attachment, no `.xml` | PDF | `data_extractor.parse_pdf_via_gemini()` |
| 4 | No attachment, body has URL + code | WEB | `web_scraper.download_xml()` → `data_extractor.parse_xml()` |

All branches call `storage.append_to_csv(invoice_dict)` on success.

### Error Handling

- Every branch wrapped in `try/except`.
- On error: log structured entry + send immediate Telegram alert + append to `data/errors.csv`.
- Email is marked as **SEEN** after error to prevent infinite reprocessing.
- Branch 4 (Playwright): retry once after 3-second wait before alerting.

**`data/errors.csv` schema:** `error_date`, `email_sender`, `email_time`, `email_subject`, `branch`, `error_message`

---

## 4. Module 1 — Email Watcher (`email_handler.py`)

- Connect to `mail.rvctel.vn:993` via IMAPS (SSL/TLS) using `imap_tools`.
- Fetch `UNSEEN` emails where subject contains any of (case-insensitive):
  - `"hóa đơn điện tử"`, `"hóa đơn"`, `"hddt"`
- Return list of email objects with: uid, subject, body text, attachments.

---

## 5. Module 2 — Router & Processor (`router.py`, `web_scraper.py`)

### Branch 1 — XML
- Extract `.xml` bytes from attachment → pass to `data_extractor.parse_xml()`.

### Branch 2 — ZIP
- Save ZIP to `temp/<uid>/`, extract all, find first `.xml` file.
- Parse XML → delete entire `temp/<uid>/` directory.

### Branch 3 — PDF via Gemini
- Send PDF bytes to `gemini-2.0-flash` Vision API.
- Strict prompt: return **only valid JSON** matching the unified schema; use `null` for missing fields.

### Branch 4 — Web Portal (Playwright)

Two-stage lookup (Stage 1 attempted first; Stage 2 only if Stage 1 yields nothing):

**Stage 1 — Direct token link (fetch without form filling):**
- Scan email body (HTML + plain text) for URLs that look like direct invoice download links.
- Pattern: URLs containing keywords such as `token=`, `download`, `file`, `xml`, `pdf`, `invoice`, or common Vietnamese portal paths.
- If found: fetch the URL directly via `requests.get()` (with a browser-like User-Agent).
  - If response content is XML → parse directly.
  - If response content is PDF → pass to Gemini (same as Branch 3).
  - If response is an HTML page (not a direct file) → fall through to Stage 2 using this URL.

**Stage 2 — Lookup code + Playwright form filling:**

Regex patterns for lookup code (first match wins, case-insensitive):
```python
REGEX_PATTERNS = [
    r"mã số[\s:]*([A-Z0-9_]+)",                # MISA
    r"mã tra cứu[\s:]*([A-Z0-9_]+)",           # Phổ biến chung
    r"mã nhận hóa đơn[\s:]*([A-Z0-9_]+)",      # VNPT
    r"Mã bí mật[\s:]*([A-Z0-9_]+)",            # Viettel
]
```

Portal URL extracted via `https?://[^\s"<>]+` pattern from email body.

**Provider Registry** (`web_scraper.py`):
```python
SCRAPERS = {
    "hoadon.petrolimex.com.vn": scrape_petrolimex,
    "vietteltelecom.vn":        scrape_viettel,   # path: /hoadondientu
    "vnpt-invoice.com.vn":      scrape_vnpt,       # path: /invoice
    "www.meinvoice.vn":         scrape_misa,       # path: /tra-cuu
}
```

- Domain extracted from URL (path stripped) as registry key.
- Unknown domain → Telegram alert "unsupported provider: `<domain>`" + skip.
- Each `scrape_<provider>(url, code) -> bytes` is a self-contained Playwright (headless Chromium) function.
- Retry logic: failure → wait 3s → retry once → on second failure: Telegram alert + mark seen.
- A generic fallback scraper is also available for ad-hoc use.

---

## 6. Module 3 — Data Extraction & Storage

### Unified Invoice Schema

| Field | Type | Notes |
|-------|------|-------|
| `processed_date` | datetime | Bot processing timestamp |
| `invoice_type` | str | `SALE` if `seller_tax_code == "0313028740"`, else `PURCHASE` |
| `invoice_symbol` | str | e.g. `1C24TKQ` |
| `invoice_number` | str | e.g. `000001` |
| `issue_date` | str | From invoice |
| `lookup_code` | str | WEB: from email body regex; XML/ZIP: from XML data; PDF: from Gemini extraction; `null` if not found |
| `lookup_website` | str | WEB: from email body URL; XML/ZIP: from XML data; PDF: from Gemini extraction; `null` if not found |
| `seller_name` | str | |
| `seller_tax_code` | str | Key field for type determination |
| `seller_address` | str | |
| `buyer_name` | str | |
| `buyer_tax_code` | str | |
| `buyer_address` | str | |
| `payment_method` | str | |
| `bank_account` | str | |
| `total_before_tax` | float | |
| `vat_rate` | str | e.g. `10%` |
| `total_vat_amount` | float | |
| `total_after_tax` | float | |
| `source_branch` | str | `XML`, `ZIP`, `PDF`, `WEB` |
| `source_email_subject` | str | Original email subject |

### Storage Rules (`storage.py`)
- File: `data/Tong_hop_hoa_don.csv`, encoding `utf-8`
- Append-only — never overwrite existing rows
- Create file with header row on first run if not exists

### XML Parsing Notes
- Use `xml.etree.ElementTree` with namespace stripping (`re.sub` on `{...}` prefixes)
- Map Vietnamese XML tags to unified schema fields

---

## 7. Module 4 — Reporting (`reporter.py`)

### Daily Report (08:00 via `schedule`)
```
📊 Báo cáo hóa đơn ngày DD/MM/YYYY

✅ Tổng số hóa đơn: N
📥 Đầu vào (PURCHASE): X hóa đơn | Tổng tiền: Y VND
📤 Đầu ra (SALE): X hóa đơn | Tổng tiền: Y VND

⚠️ Lỗi xử lý: K email
- [HH:MM] Từ: sender@domain.com | Tiêu đề: ... | Lỗi: ...
- [HH:MM] Từ: sender@domain.com | Tiêu đề: ... | Lỗi: ...
```
- Reads `Tong_hop_hoa_don.csv`, filters `processed_date == yesterday`, groups by `invoice_type`, sums `total_after_tax`.
- Reads `errors.csv`, filters `error_date == yesterday`, lists each error with sender, time, and subject.
- Error section omitted entirely if K = 0.
- Sent via Telegram Bot API (`requests` library).

### Real-time Error Alert
```
⚠️ Lỗi xử lý hóa đơn
📧 Email: <subject>
🔀 Nhánh: <branch>
❌ Lỗi: <error message>
```

---

## 8. Configuration (`.env`)

```env
IMAP_SERVER=mail.rvctel.vn
IMAP_PORT=993
IMAP_USER=invoices_bot@rvctel.vn
IMAP_PASSWORD=fe1923Kk7

GEMINI_API_KEY=your_gemini_api_key_here

TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

EMAIL_POLL_INTERVAL_MINUTES=15
DAILY_REPORT_TIME=08:00

RVC_TAX_CODE=0313028740
```

---

## 9. Docker Setup

- **Base image:** `python:3.11-slim`
- **Service name:** `rvc-invoices-bot`
- **Volumes:** `invoices_data` → `/app/data`, `invoices_logs` → `/app/logs`
- **Restart policy:** `always`
- **Playwright:** Chromium installed inside image via `playwright install --with-deps chromium`
- **Entrypoint:** `python main.py`

---

## 10. Logging

- `logging.handlers.RotatingFileHandler`: max 5MB, keep 3 backups → `logs/bot.log`
- Also mirrors to stdout (visible via `docker logs rvc-invoices-bot`)
- Structured log fields: `timestamp`, `level`, `module`, `email_uid`, `branch`, `message`
