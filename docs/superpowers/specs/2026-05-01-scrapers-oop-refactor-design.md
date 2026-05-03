# Design: OOP Scraper Module Inside rvc-invoices-bot

**Date:** 2026-05-01
**Status:** Approved

---

## Overview

Replace the flat `scrape_*` functions in `web_extraction_router.py` with a proper OOP scraper package at `rvc-invoices-bot/scrapers/`. The package uses stealth Playwright + human simulation for all providers, solves captchas via Gemini, and exposes a single public function `scrape_invoice(url, lookup_code, download_dir) → ScrapedResult`.

The WEB branch in `router.py` is renamed from `process_branch_4` to `process_branch_web` and uses the same `_process_pair` path as ATTACH — no duplicated upload/storage logic.

---

## Package Structure

```
rvc-invoices-bot/
└── scrapers/
    ├── __init__.py        # public API: scrape_invoice()
    ├── result.py          # ScrapedResult dataclass
    ├── browser.py         # stealth browser context builder
    ├── base.py            # BaseInvoiceScraper ABC + human simulation toolkit
    ├── factory.py         # ScraperFactory: domain → class
    ├── easyinvoice.py     # EasyInvoiceScraper
    ├── misa.py            # MisaScraper
    ├── petrolimex.py      # PetrolimexScraper
    ├── viettel.py         # ViettelScraper
    └── vnpt.py            # VnptScraper
```

The standalone `/home/ai/scrapers/` directory is superseded by this package and no longer used.

---

## Core Interfaces

### `ScrapedResult` (result.py)

```python
@dataclass
class ScrapedResult:
    xml_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    xml_path: str | None = None    # set when download_dir is provided
    pdf_path: str | None = None    # set when download_dir is provided
```

At least one of `xml_bytes`/`pdf_bytes` must be non-None for a valid result. Both can be set if the provider exposes both files. Either path field is set only when `download_dir` is passed to `scrape_invoice`.

### Public entry point (`__init__.py`)

```python
def scrape_invoice(
    url: str,
    lookup_code: str,
    download_dir: str | None = None,
) -> ScrapedResult:
    ...
```

- Builds stealth browser context via `browser.py`
- Resolves correct scraper class via `ScraperFactory`
- Calls `scraper.scrape() → ScrapedResult`
- If `download_dir` is provided: saves XML/PDF to disk and sets `xml_path`/`pdf_path` on result
- Raises `ValueError` if scraper returns both `xml_bytes=None` and `pdf_bytes=None`
- Raises `ScraperNotSupportedException` for unknown domains

### `BaseInvoiceScraper` (base.py)

```python
class BaseInvoiceScraper(ABC):
    def __init__(self, page, lookup_code: str): ...

    @abstractmethod
    def scrape(self) -> ScrapedResult: ...

    # Human simulation toolkit (all protected, shared across scrapers)
    def _delay(self, min_sec=0.5, max_sec=1.5): ...
    def _scroll(self): ...
    def _click(self, selector, timeout=10000): ...
    def _type(self, selector, text, timeout=10000): ...
    def _download_file(self, *selectors, timeout=15000) -> bytes: ...

    # Captcha toolkit (shared across all scrapers)
    def _handle_captcha_if_present(self) -> None:
        """Detect any visible captcha image, solve via Gemini, type solution."""
    def _solve_captcha(self, image_path: str) -> str:
        """Screenshot captcha element → Gemini OCR → return digit string."""
```

### `browser.py`

```python
def build_stealth_context(playwright) -> tuple[Browser, BrowserContext]:
    """Launch Chromium with anti-detection args, stealth_sync, Vietnamese locale."""
```

All scrapers go through this — no scraper manages its own browser.

### `ScraperFactory` (factory.py)

```python
class ScraperFactory:
    _REGISTRY: dict[str, type[BaseInvoiceScraper]] = {
        "easyinvoice.com.vn":           EasyInvoiceScraper,
        "meinvoice.vn":                 MisaScraper,
        "misa.vn":                      MisaScraper,
        "hoadon.petrolimex.com.vn":     PetrolimexScraper,
        "vietteltelecom.vn":            ViettelScraper,
        "vnpt-invoice.com.vn":          VnptScraper,
    }

    @classmethod
    def get(cls, url: str, page, lookup_code: str) -> BaseInvoiceScraper:
        """Suffix-match netloc against registry → instantiate correct scraper."""
```

Domain matching is **suffix-based**: `netloc == key` or `netloc.endswith("." + key)`.
This correctly maps seller-specific subdomains like `0102362584001hd.easyinvoice.com.vn` or `6101145281-tt78.vnpt-invoice.com.vn` to the right scraper class.
The full seller URL (with subdomain) is passed through to the scraper unchanged — it is the correct lookup URL.
Raises `ScraperNotSupportedException` if no suffix match found.

---

## Scraper Implementations

### All scrapers (common pattern)

```python
def scrape(self) -> ScrapedResult:
    self._setup_dialogs()           # dismiss unexpected alerts
    self.page.goto(self.url, wait_until="networkidle")
    self._scroll()
    self._type(CODE_SELECTOR, self.lookup_code)
    self._handle_captcha_if_present()   # all scrapers check; no-op if none visible
    self._click(SEARCH_SELECTOR)
    self._delay(2.0, 3.5)
    self._check_errors()            # raise InvoiceNotFoundException if needed
    xml_bytes = self._try_download(XML_SELECTORS)
    pdf_bytes = self._try_download(PDF_SELECTORS)
    return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

`_try_download` returns `None` if no matching button is visible — it does not raise.

### Captcha handling (base.py — shared by all scrapers)

`_handle_captcha_if_present` uses broad selectors that match any provider:

- Image detection: `img[src*='captcha' i], img[id*='captcha' i], img[class*='captcha' i]`
- Input detection: `input[id*='captcha' i], input[placeholder*='xác thực' i]`

If both a captcha image and input are visible:
1. Screenshots the captcha image element to a temp file
2. Calls `_solve_captcha(path)` → Gemini `gemini-1.5-flash` OCR, returns digits only
3. Types the solution into the captcha input via `_type()`
4. Raises `CaptchaRequiredException` if Gemini returns an empty string

`_solve_captcha` uses `google.genai` (not deprecated `google.generativeai`). API key from `os.environ["GEMINI_API_KEY"]`. The Gemini client is instantiated once at the module level in `base.py`.

---

## Exceptions (exceptions.py — moved from standalone scrapers/)

```python
class CaptchaRequiredException(Exception): ...
class InvoiceNotFoundException(Exception): ...
class ScraperNotSupportedException(Exception): ...
```

---

## web_extraction_router.py Changes

- **Remove**: `scrape_misa`, `scrape_easyinvoice`, `scrape_petrolimex`, `scrape_viettel`, `scrape_vnpt`, `scrape_generic`, `dynamic_web_router`, `_playwright_download`, `SCRAPERS` dict
- **Add**: `from scrapers import scrape_invoice` and `from scrapers.result import ScrapedResult`
- **Rename**: `process_branch_4` → `process_branch_web(email, download_dir: str) → ScrapedResult | None`
- `process_branch_web` internal flow:
  1. Try `extract_direct_link` (requests-based, no Playwright) → if hit, save bytes to `download_dir` as `direct_{uid}.xml` or `direct_{uid}.pdf`, wrap in `ScrapedResult` with path set
  2. Extract `lookup_code` from email body; extract all URLs from email body
  3. **Pick best URL**: among all extracted URLs, prefer the one that (a) matches a known provider suffix and (b) has the most subdomain parts (most specific). A seller-specific URL like `0102362584001hd.easyinvoice.com.vn/Search/Index` is preferred over a generic `easyinvoice.com.vn` root. If no known-provider URL found, fall back to first URL.
  4. Call `scrape_invoice(lookup_url, lookup_code, download_dir)` with retry (2 attempts, 3s sleep)
  5. Return `ScrapedResult | None`
- **Keep**: `extract_direct_link`, `extract_xml_from_html_attachment`, `_extract_lookup_code`, `_extract_urls`, `_try_direct_download`, `download_invoice_file` shim

---

## router.py Changes

Two branches only: `ATTACH` and `WEB`.

```python
# ATTACH branch (unchanged logic)
if email.attachments:
    branch = "ATTACH"
    had_zip = _dump_and_extract(email, uid_temp)
    pairs = _collect_pairs(uid_temp)
    if pairs:
        for pair in pairs:
            _process_pair(pair, email, had_zip)
        return
    logger.info("No invoice files in attachments — falling through to WEB")

# WEB branch
branch = "WEB"
logger.info(f"Branch WEB | uid={email.uid}")
result = web_extraction_router.process_branch_web(email, uid_temp)
if result is None:
    raise ValueError("All extraction tiers failed — no XML or PDF retrieved")

pair = {"stem": f"web_{email.uid}"}
if result.xml_path: pair["xml"] = result.xml_path
if result.pdf_path: pair["pdf"] = result.pdf_path
_process_pair(pair, email, had_zip=False)
```

`_process_pair` is unchanged — it already handles one of xml/pdf being absent.

---

## Data Flow

```
Email received
    │
    ├─ ATTACH: has attachments?
    │     ├─ dump + extract ZIPs to uid_temp
    │     ├─ collect XML/PDF/HTML pairs
    │     ├─ pairs found → _process_pair → upload → storage → DONE
    │     └─ no pairs → fall through to WEB
    │
    └─ WEB: read email body
          ├─ Tier 1: extract_direct_link (requests, no Playwright)
          │     └─ hit → save to uid_temp → ScrapedResult with paths
          └─ Tier 2: scrape_invoice(url, code, uid_temp)
                ├─ stealth browser context
                ├─ ScraperFactory → correct scraper class
                ├─ scraper.scrape() → XML + PDF bytes
                ├─ save to uid_temp → set xml_path / pdf_path
                └─ return ScrapedResult
          │
          └─ build pair dict from result paths → _process_pair → upload → storage → DONE
```

---

## Dependencies

- `playwright` (already installed)
- `playwright-stealth` (needs `pip install playwright-stealth` — not yet installed)
- Delete `/home/ai/scrapers/` standalone directory after migration is complete
- `google-genai` (already installed — replaces deprecated `google.generativeai`)
- `Pillow` (already installed)
- `GEMINI_API_KEY` env var (already in `.env`)

---

## Testing

- Unit tests for `ScraperFactory.get()` with various URLs
- Unit tests for `_extract_lookup_code` (existing, unchanged)
- Integration test: `scrape_invoice` with a real EasyInvoice URL + known lookup code
- `process_branch_web` tested with mock email objects
