# rvc-invoices-bot

Automated Vietnamese e-invoice processing bot for RVC Telecom. Polls an IMAP mailbox for invoice emails, extracts XML/PDF files from attachments or web portals, parses invoice data, stores it in SQLite + MinIO, and notifies via Telegram.

---

## What it does

1. **Email polling** — fetches unseen emails from an IMAP inbox on a configurable interval (default: every 15 minutes)
2. **ATTACH branch** — extracts XML/PDF/HTML files from email attachments (including nested ZIPs)
3. **WEB branch** — when no usable attachment is found, scrapes the invoice portal linked in the email body using Playwright
4. **Data extraction** — parses invoice XML (Vietnamese e-invoice schema) or falls back to Gemini for PDF
5. **Storage** — uploads files to MinIO and writes invoice metadata to a SQLite database
6. **Notifications** — sends a Telegram message per invoice + daily summary report
7. **Web dashboard** — simple Flask UI to browse and filter stored invoices

---

## Architecture

```
main.py
  └─ router.process_email(email)
       ├─ ATTACH branch
       │    └─ dump attachments → extract ZIPs → collect (xml, pdf, html) pairs
       │         └─ _process_pair → data_extractor → storage → file_storage → reporter
       └─ WEB branch  (fallthrough when ATTACH yields no pairs)
            └─ web_extraction_router.process_branch_web()
                 ├─ Tier 1: direct HTTP download (requests)
                 └─ Tier 2: scrapers.scrape_invoice() via Playwright
                      └─ ScraperFactory → VnptScraper / EasyInvoiceScraper / ...
```

---

## Supported invoice portals

| Domain | Scraper | Captcha strategy |
|--------|---------|-----------------|
| `*.easyinvoice.com.vn` | `EasyInvoiceScraper` | Capsolver |
| `meinvoice.vn`, `*.misa.vn` | `MisaScraper` | Capsolver |
| `hoadon.petrolimex.com.vn` | `PetrolimexScraper` | Capsolver (4-digit, reload retry) |
| `vietteltelecom.vn` | `ViettelScraper` | Capsolver |
| `*.vnpt-invoice.com.vn` | `VnptScraper` | Capsolver + bypass probe (4-digit, 3-attempt retry) |

All scrapers use stealth Playwright (playwright-stealth v2, `headless=True`, `vi-VN` locale) with human-like mouse movement and randomised delays.

---

## Project structure

```
rvc-invoices-bot/
├── main.py                      # Entry point: schedule loop
├── router.py                    # Email branch routing (ATTACH / WEB)
├── web_extraction_router.py     # Tier-1 direct links + Tier-2 Playwright
├── scrapers/                    # OOP scraper package
│   ├── __init__.py              # scrape_invoice() public API
│   ├── base.py                  # BaseInvoiceScraper + capsolver_solve_image()
│   ├── browser.py               # build_stealth_context()
│   ├── factory.py               # ScraperFactory (domain → class)
│   ├── result.py                # ScrapedResult dataclass
│   ├── exceptions.py            # CaptchaRequiredException, etc.
│   ├── easyinvoice.py
│   ├── misa.py
│   ├── petrolimex.py
│   ├── viettel.py
│   └── vnpt.py
├── data_extractor.py            # XML parsing + Gemini PDF fallback
├── storage.py                   # SQLite read/write (invoices, errors)
├── file_storage.py              # MinIO upload
├── email_handler.py             # IMAP fetch + mark-as-seen
├── reporter.py                  # Telegram notifications + daily report
├── web_app.py                   # Flask dashboard
├── config.py                    # Env-var config
├── logger.py                    # Logging setup
├── tests/
│   ├── test_scrapers.py         # 131 unit tests
│   ├── test_web_extraction_router.py
│   ├── test_router.py
│   └── ...
├── scripts/                     # Debug/E2E helper scripts
│   ├── debug_petrolimex.py
│   ├── e2e_petrolimex.py
│   └── fetch_email_uid.py
├── Dockerfile
├── Dockerfile.web
├── docker-compose.yml           # Bot + web + MinIO + Traefik
└── .env.example
```

---

## Quick start

### 1. Clone and configure

```bash
git clone <repo-url> rvc-invoices-bot
cd rvc-invoices-bot
cp .env.example .env
# Edit .env — fill in IMAP credentials, API keys, MinIO, Telegram
```

### 2. Install Python dependencies (local dev)

```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
```

### 3. Run tests

```bash
pytest tests/ -v
# Expected: 131 passed
```

### 4. Run locally

```bash
python main.py
```

### 5. Run with Docker Compose (production)

```bash
docker compose up -d
```

Services started:
- `rvc-invoices-bot` — main bot
- `rvc-invoices-web` — Flask dashboard (behind Traefik)
- `rvc-minio` — object storage
- `traefik` — reverse proxy with Let's Encrypt TLS

---

## Environment variables

| Variable | Description | Example |
|----------|-------------|---------|
| `IMAP_SERVER` | IMAP hostname | `mail.rvctel.vn` |
| `IMAP_PORT` | IMAP port (SSL) | `993` |
| `IMAP_USER` | IMAP login | `invoices_bot@rvctel.vn` |
| `IMAP_PASSWORD` | IMAP password | |
| `GEMINI_API_KEY` | Google Gemini API key (PDF data extraction fallback) | |
| `CAPSOLVER_API_KEY` | Capsolver API key (VNPT + Petrolimex captcha) | |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID | |
| `EMAIL_POLL_INTERVAL_MINUTES` | Poll interval | `15` |
| `DAILY_REPORT_TIME` | Daily summary time (HH:MM) | `08:00` |
| `RVC_TAX_CODE` | Buyer tax code for invoice matching | `0313028740` |
| `MINIO_ENDPOINT` | MinIO host:port | `rvc-minio:9000` |
| `MINIO_ACCESS_KEY` | MinIO access key | |
| `MINIO_SECRET_KEY` | MinIO secret key | |
| `MINIO_BUCKET` | Bucket name | `rvc-invoices` |
| `MINIO_PUBLIC_URL` | Public MinIO URL for file links | `https://rvc-s3.rvctel.vn` |
| `WEB_PORT` | Dashboard port | `8080` |
| `WEB_SECRET` | Dashboard auth token (query param `?secret=`) | |
| `DOMAIN_WEB` | Traefik domain for dashboard | `hddt.rvctel.vn` |
| `DOMAIN_MINIO` | Traefik domain for MinIO API | `rvc-s3.rvctel.vn` |
| `DOMAIN_MINIO_CONSOLE` | Traefik domain for MinIO Console | `rvc-s3-console.rvctel.vn` |
| `ACME_EMAIL` | Let's Encrypt contact email | `admin@rvctel.vn` |

---

## Scrapers package

### Adding a new provider

1. Create `scrapers/newprovider.py` subclassing `BaseInvoiceScraper`:

```python
import logging
import os
import random
import re
import tempfile

from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

_CODE_SEL = "input#code"
_CAPTCHA_IMG_SEL = "img#captcha"
_CAPTCHA_INPUT_SEL = "input#captchaInput"
_SUBMIT_SEL = "button:has-text('Search')"
_MAX_RETRIES = 3


class NewProviderScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            solution = self._screenshot_and_solve_captcha()
            if solution:
                self._enter_captcha(solution)
            self._click(_SUBMIT_SEL)
            self._delay(2.0, 3.5)

            if self._page_says_not_found():
                raise InvoiceNotFoundException(
                    f"NewProvider: invoice not found for '{self.lookup_code}'"
                )
            if self._downloads_visible():
                break
            if attempt < _MAX_RETRIES - 1:
                logger.warning("NewProvider: no downloads after attempt %d, reloading", attempt + 1)
                self.page.reload(wait_until="networkidle")
        else:
            raise CaptchaRequiredException(
                f"NewProvider: captcha failed after {_MAX_RETRIES} attempts"
            )

        xml_bytes = self._try_download("a:has-text('XML')")
        pdf_bytes = self._try_download("a:has-text('PDF')")
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    def _enter_code(self) -> None:
        el = self.page.locator(_CODE_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.2)
        el.press_sequentially(self.lookup_code, delay=100)
        self._delay(0.2, 0.5)

    def _screenshot_and_solve_captcha(self) -> str:
        img_loc = self.page.locator(_CAPTCHA_IMG_SEL)
        if img_loc.count() == 0 or not img_loc.first.is_visible():
            return ""
        self._delay(0.5, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.first.screenshot(path=captcha_path)
            result = capsolver_solve_image(captcha_path) or ""
            result = re.sub(r"\s+", "", result)
            logger.info("NewProvider: Capsolver captcha result = '%s'", result)
            return result
        finally:
            os.unlink(captcha_path)

    def _enter_captcha(self, solution: str) -> None:
        el = self.page.locator(_CAPTCHA_INPUT_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.2)
        el.press_sequentially(solution, delay=random.randint(80, 150))
        self._delay(0.2, 0.5)

    def _page_says_not_found(self) -> bool:
        text: str = self.page.evaluate("() => document.body.innerText.toLowerCase()")
        return "not found" in text

    def _downloads_visible(self) -> bool:
        return (
            self.page.locator("a:has-text('XML')").count() > 0
            or self.page.locator("a:has-text('PDF')").count() > 0
        )
```

2. Register the domain in `scrapers/factory.py`:

```python
def _get_registry() -> dict[str, type]:
    ...
    from .newprovider import NewProviderScraper
    return {
        ...
        "newprovider.vn": NewProviderScraper,
    }
```

3. Add tests in `tests/test_scrapers.py`.

### Captcha strategy

All scrapers use **Capsolver** (`capsolver_solve_image` in `scrapers/base.py`): screenshots the captcha `<img>` element, submits the PNG to the [Capsolver `ImageToTextTask` API](https://docs.capsolver.com/guide/recognition/ImageToTextTask.html), and returns the solved text. Requires `CAPSOLVER_API_KEY` env var.

Pre-submission validation rejects any solution that doesn't match `[0-9]{4}` before wasting a form attempt — invalid answers trigger a captcha refresh and retry instead.

**VNPT bypass probe** (`VnptScraper._probe_bypass`): before the retry loop, submits `"0000"` to test whether the portal enforces captcha server-side. If the results table appears, OCR is skipped entirely for that session.

---

## Development

### Running a specific test file

```bash
pytest tests/test_scrapers.py -v
pytest tests/test_web_extraction_router.py -v
```

### Debug scripts

```bash
# Test Petrolimex E2E with a real lookup code
python scripts/e2e_petrolimex.py <URL> <CODE>

# Fetch and display a raw email by UID
python scripts/fetch_email_uid.py <UID>
```

### Logs

Logs go to `logs/rvc-invoices-bot.log` (JSON structured) and stdout. Log level is `INFO` by default; set `LOG_LEVEL=DEBUG` for scraper traces.
