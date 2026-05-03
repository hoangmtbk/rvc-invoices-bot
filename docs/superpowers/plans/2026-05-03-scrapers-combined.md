# Scrapers OOP Refactor + VNPT Captcha Accuracy — Combined Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full OOP `scrapers/` package with `scrape_invoice(url, lookup_code, download_dir) → ScrapedResult`, stealth Playwright, and Capsolver-based captcha for VNPT and Petrolimex — achieving ≥95% captcha pass rate.

**Architecture:** All scrapers inherit `BaseInvoiceScraper` which owns human simulation, generic captcha handling, and the shared `capsolver_solve_image()` helper. `ScraperFactory` maps provider domains via suffix matching. VNPT uses a bypass probe (submit dummy captcha first) + pre-submission digit validation. Petrolimex uses the same Capsolver-only pipeline with a page-reload retry loop. `web_extraction_router.process_branch_web()` orchestrates Tier-1 direct-link downloads and Tier-2 Playwright scraping.

**Tech Stack:** Python 3.11+, Playwright (sync), playwright-stealth v2, Capsolver API, google-genai (Gemini 2.5 Flash — data_extractor PDF fallback only), pytest + unittest.mock

> **Status:** All tasks below are **COMPLETE** as of 2026-05-03. This document is the definitive as-built reference. Tick marks show completed work.

---

## Deviations from Original Plans

| Original Plan | As-Built |
|---|---|
| VNPT: tiered ddddocr → Capsolver → Gemini in `_solve_vnpt_captcha()` | All scrapers: **Capsolver-only** via `capsolver_solve_image()` in `base.py`; ddddocr/Gemini dropped from all scrapers after field testing |
| `_capsolver_solve()` as module-level function in `vnpt.py` | `capsolver_solve_image()` promoted to `base.py` as shared utility; all scrapers use it |
| `playwright_stealth.stealth_sync(page)` v1 API | `Stealth().apply_stealth_sync(page)` v2 API wrapper in `scrapers/__init__.py` |
| `scrape_invoice()` uses raw lookup_code in filename | Lookup code sanitised with `re.sub(r"[^A-Za-z0-9_\-]", "_", ...)` before building filename |
| `_solve_vnpt_captcha()` module-level function | `_screenshot_and_solve_captcha()` + `_enter_captcha()` instance methods on all scrapers |
| EasyInvoice/MISA/Viettel used `_handle_captcha_if_present()` (Gemini) | All three updated to Capsolver pattern matching petrolimex; `_handle_captcha_if_present` and `_solve_captcha` removed from `base.py` |

---

## File Map (as-built)

| Path | Responsibility |
|------|----------------|
| `scrapers/__init__.py` | Public API: `scrape_invoice()`, `stealth_sync()` |
| `scrapers/result.py` | `ScrapedResult` dataclass |
| `scrapers/exceptions.py` | `CaptchaRequiredException`, `InvoiceNotFoundException`, `ScraperNotSupportedException` |
| `scrapers/browser.py` | `build_stealth_context()` — stealth chromium context |
| `scrapers/base.py` | `BaseInvoiceScraper` ABC: human simulation + `capsolver_solve_image()` shared helper |
| `scrapers/factory.py` | `ScraperFactory.get()` + `_get_registry()`: suffix domain → class |
| `scrapers/easyinvoice.py` | `EasyInvoiceScraper` — Capsolver captcha, direct-view URL detection, ZIP unpack |
| `scrapers/misa.py` | `MisaScraper` — Capsolver captcha, XML dropdown handling |
| `scrapers/petrolimex.py` | `PetrolimexScraper` — Capsolver, 4-digit validation, page-reload retry |
| `scrapers/viettel.py` | `ViettelScraper` — Capsolver captcha, XML/PDF download |
| `scrapers/vnpt.py` | `VnptScraper` — bypass probe + Capsolver-only + pre-submission digit validation |
| `web_extraction_router.py` | Tier-1 direct link + Tier-2 Playwright via `process_branch_web()` |
| `router.py` | WEB branch: calls `process_branch_web`, builds pair dict, calls `_process_pair` |
| `tests/test_scrapers.py` | 131 tests covering factory, result, base, VnptScraper, PetrolimexScraper |
| `tests/test_web_extraction_router.py` | Tests for `_pick_best_url`, `process_branch_web`, URL extraction |

---

## Task 1: Scaffold scrapers package ✅

**Files:**
- Created: `scrapers/__init__.py`
- Modified: `requirements.txt`

- [x] **Step 1: Install playwright-stealth**

```bash
pip install playwright-stealth
```

- [x] **Step 2: Add to requirements.txt**

```
playwright-stealth>=1.0.6
ddddocr>=1.4.11,<2
```

- [x] **Step 3: Create package directory**

```bash
mkdir -p /home/ai/rvc-invoices-bot/scrapers
touch /home/ai/rvc-invoices-bot/scrapers/__init__.py
```

- [x] **Step 4: Verify import**

```bash
cd /home/ai/rvc-invoices-bot
python -c "import scrapers; print('OK')"
```

- [x] **Step 5: Commit**

```bash
git commit -m "chore: scaffold scrapers package, add playwright-stealth dep"
```

---

## Task 2: result.py and exceptions.py ✅

**Files:**
- Created: `scrapers/result.py`
- Created: `scrapers/exceptions.py`
- Created: `tests/test_scrapers.py`

- [x] **Step 1: Create scrapers/result.py**

```python
from dataclasses import dataclass

@dataclass
class ScrapedResult:
    xml_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    xml_path: str | None = None
    pdf_path: str | None = None
```

- [x] **Step 2: Create scrapers/exceptions.py**

```python
class CaptchaRequiredException(Exception):
    pass

class InvoiceNotFoundException(Exception):
    pass

class ScraperNotSupportedException(Exception):
    pass
```

- [x] **Step 3: Tests pass**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

- [x] **Step 4: Commit**

```bash
git commit -m "feat: add ScrapedResult dataclass and custom exceptions"
```

---

## Task 3: browser.py ✅

**Files:**
- Created: `scrapers/browser.py`

- [x] **Step 1: Create scrapers/browser.py**

```python
from playwright.sync_api import Browser, BrowserContext, Playwright

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

def build_stealth_context(playwright: Playwright) -> tuple[Browser, BrowserContext]:
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="vi-VN",
    )
    return browser, context
```

- [x] **Step 2: Commit**

```bash
git commit -m "feat: add stealth browser context builder"
```

---

## Task 4: base.py — human simulation + shared Capsolver helper ✅

**Files:**
- Created: `scrapers/base.py`

> **Note:** `capsolver_solve_image()` was originally planned as a module-level function in `vnpt.py`. It was promoted to `base.py` after field testing showed Petrolimex also needed it.

- [x] **Step 1: Create scrapers/base.py (as-built)**

Key additions vs. original plan:
- `capsolver_solve_image(image_path)` — shared Capsolver HTTP helper (CAPSOLVER_API_KEY env var gates it)
- `_get_gemini_client()` — **removed**; Gemini no longer used in scrapers
- `BaseInvoiceScraper._classify_bytes()` — static method returning `'xml'`, `'pdf'`, or `None`

```python
def capsolver_solve_image(image_path: str) -> str | None:
    """Submit captcha screenshot to Capsolver; return text or None.
    Inactive when CAPSOLVER_API_KEY is not set."""
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        return None
    import requests as _requests
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    create_resp = _requests.post(
        "https://api.capsolver.com/createTask",
        json={"clientKey": api_key, "task": {"type": "ImageToTextTask", "body": b64}},
        timeout=15,
    ).json()
    # ImageToTextTask is synchronous — result may already be in createTask response
    if create_resp.get("status") == "ready":
        return create_resp.get("solution", {}).get("text", "")
    task_id = create_resp.get("taskId")
    for _ in range(10):
        time.sleep(1)
        result_resp = _requests.post(
            "https://api.capsolver.com/getTaskResult",
            json={"clientKey": api_key, "taskId": task_id},
            timeout=10,
        ).json()
        if result_resp.get("status") == "ready":
            return result_resp.get("solution", {}).get("text", "")
    return None
```

- [x] **Step 2: Tests pass**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

- [x] **Step 3: Commit**

```bash
git commit -m "feat: add BaseInvoiceScraper with human simulation and capsolver shared helper"
```

---

## Task 5: factory.py ✅

**Files:**
- Created: `scrapers/factory.py`

- [x] **Step 1: Create scrapers/factory.py (as-built)**

```python
from urllib.parse import urlparse
from .base import BaseInvoiceScraper
from .exceptions import ScraperNotSupportedException

def _get_registry() -> dict[str, type]:
    from .easyinvoice import EasyInvoiceScraper
    from .misa import MisaScraper
    from .petrolimex import PetrolimexScraper
    from .viettel import ViettelScraper
    from .vnpt import VnptScraper
    return {
        "easyinvoice.com.vn":           EasyInvoiceScraper,
        "meinvoice.vn":                 MisaScraper,
        "misa.vn":                      MisaScraper,
        "hoadon.petrolimex.com.vn":     PetrolimexScraper,
        "vietteltelecom.vn":            ViettelScraper,
        "vnpt-invoice.com.vn":          VnptScraper,
    }

class ScraperFactory:
    @classmethod
    def get(cls, url: str, page, lookup_code: str) -> BaseInvoiceScraper:
        netloc = (urlparse(url).hostname or "").lower()
        registry = _get_registry()
        for key, scraper_cls in registry.items():
            if netloc == key or netloc.endswith("." + key):
                return scraper_cls(page, url, lookup_code)
        raise ScraperNotSupportedException(f"No scraper registered for domain: {netloc}")
```

> **Note:** Uses `urlparse(url).hostname` (not `.netloc`) to strip port numbers cleanly.

- [x] **Step 2: Factory tests pass**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -k "factory" -v
```

- [x] **Step 3: Commit**

```bash
git commit -m "feat: add ScraperFactory with suffix domain routing"
```

---

## Task 6: easyinvoice.py, misa.py, viettel.py ✅

**Files:**
- Created: `scrapers/easyinvoice.py`
- Created: `scrapers/misa.py`
- Created: `scrapers/viettel.py`

These three follow the same Capsolver pattern as petrolimex: `_screenshot_and_solve_captcha()` + `_enter_captcha()` + `page.reload()` on retry. If the portal has no captcha, `_screenshot_and_solve_captcha()` returns `""` and is skipped silently.

- [x] **All implementations complete and verified with `python -c "from scrapers.X import Y; print('OK')"`**

- [x] **Commit:** `feat: implement EasyInvoiceScraper, MisaScraper, ViettelScraper with Capsolver`

---

## Task 7: petrolimex.py — Capsolver-only ✅

**Files:**
- Created: `scrapers/petrolimex.py`

> **Design decision:** Petrolimex captcha is strictly 4-digit numeric. Capsolver is used exclusively; validates with `re.fullmatch(r"[0-9]{4}", solution)` before submitting.

- [x] **Step 1: Key implementation points**

- Uses `capsolver_solve_image()` from `base.py`
- Validates solution with `re.fullmatch(r"[0-9]{4}", solution)` before submitting
- On invalid solution: `self.page.reload(wait_until="networkidle")` resets the form
- Selectors derived from `playwright codegen` on `hoadon.petrolimex.com.vn`
- Submit button is `<input type="submit" name="submit">` (not `<button>`)

- [x] **Step 2: Tests pass**

- [x] **Step 3: Commit:** `feat: implement PetrolimexScraper with Capsolver-only captcha`

---

## Task 8: vnpt.py — Capsolver-only with bypass probe ✅

**Files:**
- Created/Modified: `scrapers/vnpt.py`

> **Design decision:** VNPT captcha is 4-digit numeric. Capsolver is used exclusively. The bypass probe (`_probe_bypass`) remains because some VNPT sub-domains skip server-side captcha validation entirely — if it succeeds, OCR is skipped for that session.

### VNPT bypass probe (`_probe_bypass`)

Submit with `"0000"` before the retry loop. If the results table appears, captcha validation is absent server-side — skip OCR entirely.

```python
def _probe_bypass(self) -> bool:
    try:
        self._fill_lookup_code()
        self._enter_captcha("0000")
        result = self._submit_and_wait_for_results()
        logger.info("VNPT: bypass probe result=%s", result)
        return result
    except Exception as exc:
        logger.debug("VNPT: bypass probe error: %s", exc)
        return False
```

### VNPT captcha retry loop with pre-submission validation

```python
for attempt in range(_MAX_CAPTCHA_RETRIES):
    self._fill_lookup_code()
    solution = self._screenshot_and_solve_captcha()
    if not solution or not re.fullmatch(r"[0-9]{4}", solution):
        logger.warning("VNPT: invalid solution '%s', refreshing captcha", solution)
        if attempt < _MAX_CAPTCHA_RETRIES - 1:
            self._refresh_captcha_image()
        continue
    self._enter_captcha(solution)
    if self._submit_and_wait_for_results():
        break
    if attempt < _MAX_CAPTCHA_RETRIES - 1:
        self._refresh_captcha_image()
else:
    raise CaptchaRequiredException(f"VNPT: captcha failed after {_MAX_CAPTCHA_RETRIES} attempts")
```

### VNPT captcha image refresh

```python
def _refresh_captcha_image(self) -> None:
    self.page.evaluate("""() => {
        const img = document.querySelector('#text img');
        if (!img) return;
        const base = img.src.split('?')[0];
        img.src = base + '?t=' + Date.now();
    }""")
    try:
        self.page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        self._delay(1.0, 1.5)
```

### VNPT submit detection

Uses `page.wait_for_selector` to watch for **either** the result row `#ReportViewInv table tbody tr` **or** the jQuery captcha validation error span `span[data-valmsg-for="captch"].field-validation-error` — whichever appears first.

- [x] **Step 9: All tests pass (131 total)**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/ -v
```

- [x] **Commit:** `feat: VnptScraper Capsolver-only, bypass probe, pre-submission validation`

---

## Task 9: scrapers/__init__.py — scrape_invoice() ✅

**Files:**
- Modified: `scrapers/__init__.py`

- [x] **As-built implementation (key differences from plan)**

```python
import re as _re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .browser import build_stealth_context
from .factory import ScraperFactory
from .result import ScrapedResult

def stealth_sync(page) -> None:
    """playwright-stealth v2 API wrapper."""
    Stealth().apply_stealth_sync(page)

def scrape_invoice(url: str, lookup_code: str, download_dir: str | None = None) -> ScrapedResult:
    safe_code = _re.sub(r"[^A-Za-z0-9_\-]", "_", lookup_code)  # sanitise for filesystem
    with sync_playwright() as p:
        browser, context = build_stealth_context(p)
        try:
            page = context.new_page()
            stealth_sync(page)
            scraper = ScraperFactory.get(url, page, lookup_code)
            result = scraper.scrape()
            if result.xml_bytes is None and result.pdf_bytes is None:
                raise ValueError(f"Scraper returned no files for {url}")
            if download_dir:
                if result.xml_bytes is not None:
                    xml_path = os.path.join(download_dir, f"web_{safe_code}.xml")
                    with open(xml_path, "wb") as f:
                        f.write(result.xml_bytes)
                    result.xml_path = xml_path
                if result.pdf_bytes is not None:
                    pdf_path = os.path.join(download_dir, f"web_{safe_code}.pdf")
                    with open(pdf_path, "wb") as f:
                        f.write(result.pdf_bytes)
                    result.pdf_path = pdf_path
            return result
        finally:
            browser.close()
```

- [x] **Commit:** `feat: implement scrape_invoice() public entry point`

---

## Task 10: web_extraction_router.py ✅

**Files:**
- Modified: `web_extraction_router.py`

`process_branch_web(email, download_dir)` implements a two-tier strategy:

1. **Tier 1 (direct HTTP):** `extract_direct_link()` — tries all URLs from email body matching download-like patterns via `requests`. No browser needed.
2. **Tier 2 (Playwright):** `scrape_invoice()` via `ScraperFactory`. Falls back here when Tier 1 returns nothing.

`_pick_best_url(urls)` selects the scraper-registered URL with the most subdomain parts (e.g. `0102362584001hd.easyinvoice.com.vn` beats `easyinvoice.com.vn`).

- [x] **Tests pass**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_web_extraction_router.py -v
```

- [x] **Commit:** `feat: replace flat scrapers with OOP scrape_invoice, add process_branch_web`

---

## Task 11: router.py WEB branch ✅

**Files:**
- Modified: `router.py`

WEB branch in `process_email` calls `web_extraction_router.process_branch_web(email, uid_temp)`, builds a pair dict from the returned `ScrapedResult` paths, then calls the same `_process_pair()` used by the ATTACH branch.

- [x] **Commit:** `feat: update router WEB branch to use process_branch_web and _process_pair`

---

## Task 12: Cleanup ✅

- [x] Deleted `/home/ai/scrapers/` (superseded standalone directory)
- [x] All 131 tests pass

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/ -v
# 131 passed, 1 warning in 20.87s
```

---

## Future Work

These were not part of either original plan but may be worth pursuing:

| Item | Priority | Notes |
|------|----------|-------|
| Add `MBBank` / `BIDV` scraper | Medium | New invoice portals seen in production |
| Capsolver fallback → Gemini when `CAPSOLVER_API_KEY` absent | Low | Currently: returns empty string → loop exhausts retries |
| VnptScraper `_MAX_CAPTCHA_RETRIES` configurable via env var | Low | Hardcoded to 3 |
| E2E integration test against a real VNPT test sub-domain | Medium | All current tests use mocks |
