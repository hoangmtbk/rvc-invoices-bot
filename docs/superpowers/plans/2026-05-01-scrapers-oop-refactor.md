# Scrapers OOP Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat `scrape_*` functions in `web_extraction_router.py` with a proper OOP `scrapers/` package inside `rvc-invoices-bot/`, exposing `scrape_invoice(url, lookup_code, download_dir) → ScrapedResult`, with stealth Playwright + shared Gemini captcha solving for all providers.

**Architecture:** All scrapers inherit from `BaseInvoiceScraper` which provides human simulation and captcha detection/solving. `ScraperFactory` maps provider domains via suffix matching. `scrape_invoice()` manages the browser lifecycle and file saving. The WEB branch in `router.py` calls `process_branch_web()` and feeds the result into `_process_pair()` identical to the ATTACH branch.

**Tech Stack:** Python 3.11+, Playwright (sync), playwright-stealth, google-genai (1.73+), Pillow, pytest + unittest.mock

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scrapers/__init__.py` | Public API: `scrape_invoice()` |
| Create | `scrapers/result.py` | `ScrapedResult` dataclass |
| Create | `scrapers/exceptions.py` | `CaptchaRequiredException`, `InvoiceNotFoundException`, `ScraperNotSupportedException` |
| Create | `scrapers/browser.py` | Stealth browser context builder |
| Create | `scrapers/base.py` | `BaseInvoiceScraper` ABC: human simulation + captcha toolkit |
| Create | `scrapers/factory.py` | `ScraperFactory`: suffix domain → class |
| Create | `scrapers/easyinvoice.py` | `EasyInvoiceScraper` |
| Create | `scrapers/misa.py` | `MisaScraper` |
| Create | `scrapers/petrolimex.py` | `PetrolimexScraper` |
| Create | `scrapers/viettel.py` | `ViettelScraper` |
| Create | `scrapers/vnpt.py` | `VnptScraper` |
| Create | `tests/test_scrapers.py` | Unit tests for factory, result, URL selection |
| Modify | `web_extraction_router.py` | Remove flat scrapers, rename `process_branch_4` → `process_branch_web`, add `_pick_best_url` |
| Modify | `router.py` | WEB branch: call `process_branch_web`, build pair dict, call `_process_pair` |
| Delete | `/home/ai/scrapers/` | Superseded standalone directory |

---

## Task 1: Install playwright-stealth and scaffold the package

**Files:**
- Create: `scrapers/__init__.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Install playwright-stealth**

```bash
cd /home/ai/rvc-invoices-bot
pip install playwright-stealth
```

Expected: `Successfully installed playwright-stealth-x.x.x`

- [ ] **Step 2: Add to requirements.txt**

Open `requirements.txt` and add after the `playwright` line:
```
playwright-stealth>=1.0.6
```

- [ ] **Step 3: Create the package directory and empty __init__.py**

```bash
mkdir -p /home/ai/rvc-invoices-bot/scrapers
touch /home/ai/rvc-invoices-bot/scrapers/__init__.py
```

- [ ] **Step 4: Verify import works**

```bash
cd /home/ai/rvc-invoices-bot
python -c "import scrapers; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt scrapers/__init__.py
git commit -m "chore: scaffold scrapers package, add playwright-stealth dep"
```

---

## Task 2: result.py and exceptions.py

**Files:**
- Create: `scrapers/result.py`
- Create: `scrapers/exceptions.py`
- Create: `tests/test_scrapers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scrapers.py`:

```python
import pytest
from scrapers.result import ScrapedResult
from scrapers.exceptions import (
    CaptchaRequiredException,
    InvoiceNotFoundException,
    ScraperNotSupportedException,
)


def test_scraped_result_defaults():
    r = ScrapedResult()
    assert r.xml_bytes is None
    assert r.pdf_bytes is None
    assert r.xml_path is None
    assert r.pdf_path is None


def test_scraped_result_with_xml():
    r = ScrapedResult(xml_bytes=b"<xml/>", xml_path="/tmp/a.xml")
    assert r.xml_bytes == b"<xml/>"
    assert r.xml_path == "/tmp/a.xml"
    assert r.pdf_bytes is None


def test_exceptions_are_exceptions():
    assert issubclass(CaptchaRequiredException, Exception)
    assert issubclass(InvoiceNotFoundException, Exception)
    assert issubclass(ScraperNotSupportedException, Exception)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

Expected: `ImportError` — modules don't exist yet.

- [ ] **Step 3: Create scrapers/result.py**

```python
from dataclasses import dataclass


@dataclass
class ScrapedResult:
    xml_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    xml_path: str | None = None
    pdf_path: str | None = None
```

- [ ] **Step 4: Create scrapers/exceptions.py**

```python
class CaptchaRequiredException(Exception):
    pass


class InvoiceNotFoundException(Exception):
    pass


class ScraperNotSupportedException(Exception):
    pass
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add scrapers/result.py scrapers/exceptions.py tests/test_scrapers.py
git commit -m "feat: add ScrapedResult dataclass and custom exceptions"
```

---

## Task 3: browser.py — stealth context builder

**Files:**
- Create: `scrapers/browser.py`

- [ ] **Step 1: Create scrapers/browser.py**

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

- [ ] **Step 2: Verify import**

```bash
cd /home/ai/rvc-invoices-bot
python -c "from scrapers.browser import build_stealth_context; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scrapers/browser.py
git commit -m "feat: add stealth browser context builder"
```

---

## Task 4: base.py — human simulation toolkit

**Files:**
- Create: `scrapers/base.py`

- [ ] **Step 1: Create scrapers/base.py with human simulation methods**

```python
import os
import re
import time
import random
import tempfile
from abc import ABC, abstractmethod

import PIL.Image
from google import genai

from .result import ScrapedResult
from .exceptions import CaptchaRequiredException

_gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

_CAPTCHA_IMG = (
    "img[src*='captcha' i], img[id*='captcha' i], img[class*='captcha' i]"
)
_CAPTCHA_INPUT = (
    "input[id*='captcha' i], input[placeholder*='xác thực' i]"
)


class BaseInvoiceScraper(ABC):
    def __init__(self, page, url: str, lookup_code: str) -> None:
        self.page = page
        self.url = url
        self.lookup_code = lookup_code

    @abstractmethod
    def scrape(self) -> ScrapedResult:
        pass

    def _setup_dialogs(self) -> None:
        self.page.on("dialog", lambda d: d.dismiss())

    def _delay(self, min_sec: float = 0.5, max_sec: float = 1.5) -> None:
        time.sleep(random.uniform(min_sec, max_sec))

    def _scroll(self) -> None:
        down = random.randint(300, 700)
        self.page.mouse.wheel(0, down)
        self._delay(0.5, 1.2)
        self.page.mouse.wheel(0, -random.randint(100, down // 2))
        self._delay(0.5, 1.0)

    def _click(self, selector: str, timeout: int = 10000) -> None:
        el = self.page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.hover()
        self._delay(0.3, 0.8)
        el.click()

    def _type(self, selector: str, text: str, timeout: int = 10000) -> None:
        el = self.page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.hover()
        self._delay(0.2, 0.5)
        el.click()
        el.press_sequentially(text, delay=random.randint(100, 250))
        self._delay(0.3, 0.7)

    def _try_download(self, *selectors: str, timeout: int = 15000) -> bytes | None:
        for sel in selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                with self.page.expect_download(timeout=timeout) as dl:
                    loc.first.hover()
                    self._delay(0.2, 0.5)
                    loc.first.click()
                path = dl.value.path()
                with open(path, "rb") as f:
                    return f.read()
        return None

    def _handle_captcha_if_present(self) -> None:
        img_loc = self.page.locator(_CAPTCHA_IMG)
        inp_loc = self.page.locator(_CAPTCHA_INPUT)
        if img_loc.count() == 0 or not img_loc.first.is_visible():
            return
        if inp_loc.count() == 0:
            return

        self._delay(1.0, 1.5)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.first.screenshot(path=captcha_path)
            solution = self._solve_captcha(captcha_path)
        finally:
            os.unlink(captcha_path)

        if not solution:
            raise CaptchaRequiredException(
                "Gemini returned no characters from captcha image"
            )
        self._type(_CAPTCHA_INPUT, solution)

    @staticmethod
    def _solve_captcha(image_path: str) -> str:
        img = PIL.Image.open(image_path)
        response = _gemini_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                "You are an expert OCR. Read the captcha text exactly as shown. "
                "Return ONLY the characters, no spaces or explanation.",
                img,
            ],
        )
        return re.sub(r"\s+", "", response.text.strip())
```

- [ ] **Step 2: Write tests for the non-browser parts**

Add to `tests/test_scrapers.py`:

```python
from unittest.mock import MagicMock, patch, PropertyMock
from scrapers.base import BaseInvoiceScraper
from scrapers.result import ScrapedResult
from scrapers.exceptions import CaptchaRequiredException


class _ConcreteScaper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        return ScrapedResult(xml_bytes=b"<xml/>")


def test_handle_captcha_no_op_when_no_image():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 0
    page.locator.return_value = img_loc

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    scraper._handle_captcha_if_present()  # must not raise


def test_handle_captcha_no_op_when_image_not_visible():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.first.is_visible.return_value = False
    page.locator.return_value = img_loc

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    scraper._handle_captcha_if_present()  # must not raise


def test_handle_captcha_raises_when_gemini_returns_empty():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.first.is_visible.return_value = True
    inp_loc = MagicMock()
    inp_loc.count.return_value = 1

    def locator_side_effect(sel):
        if "captcha" in sel.lower() and "input" not in sel.lower():
            return img_loc
        return inp_loc

    page.locator.side_effect = locator_side_effect

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    with patch.object(scraper, "_solve_captcha", return_value=""):
        with patch("tempfile.NamedTemporaryFile"):
            with patch("os.unlink"):
                with pytest.raises(CaptchaRequiredException):
                    scraper._handle_captcha_if_present()
```

- [ ] **Step 3: Run tests**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add scrapers/base.py tests/test_scrapers.py
git commit -m "feat: add BaseInvoiceScraper with human simulation and captcha toolkit"
```

---

## Task 5: factory.py — domain suffix routing

**Files:**
- Create: `scrapers/factory.py`
- Modify: `tests/test_scrapers.py`

- [ ] **Step 1: Write failing factory tests**

Add to `tests/test_scrapers.py`:

```python
from scrapers.factory import ScraperFactory
from scrapers.exceptions import ScraperNotSupportedException


def test_factory_easyinvoice_subdomain():
    from scrapers.easyinvoice import EasyInvoiceScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://0102362584001hd.easyinvoice.com.vn/Search/Index", page, "CODE"
    )
    assert isinstance(scraper, EasyInvoiceScraper)


def test_factory_vnpt_subdomain():
    from scrapers.vnpt import VnptScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://6101145281-tt78.vnpt-invoice.com.vn/lookup", page, "CODE"
    )
    assert isinstance(scraper, VnptScraper)


def test_factory_meinvoice():
    from scrapers.misa import MisaScraper
    page = MagicMock()
    scraper = ScraperFactory.get("https://www.meinvoice.vn/tra-cuu", page, "CODE")
    assert isinstance(scraper, MisaScraper)


def test_factory_unknown_raises():
    page = MagicMock()
    with pytest.raises(ScraperNotSupportedException):
        ScraperFactory.get("https://unknown-provider.vn/invoice", page, "CODE")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py::test_factory_easyinvoice_subdomain -v
```

Expected: `ImportError` — factory doesn't exist yet.

- [ ] **Step 3: Create scrapers/factory.py**

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
        netloc = urlparse(url).netloc.lower()
        registry = _get_registry()
        for key, scraper_cls in registry.items():
            if netloc == key or netloc.endswith("." + key):
                return scraper_cls(page, url, lookup_code)
        raise ScraperNotSupportedException(f"No scraper registered for domain: {netloc}")
```

Note: `_get_registry()` uses deferred imports to avoid circular imports since scraper modules also import from `base.py`.

- [ ] **Step 4: Create stub scraper files so factory tests can import**

Create each with a minimal stub — full implementation comes in Tasks 6–9:

`scrapers/easyinvoice.py`:
```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

class EasyInvoiceScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
```

`scrapers/misa.py`:
```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

class MisaScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
```

`scrapers/petrolimex.py`:
```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

class PetrolimexScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
```

`scrapers/viettel.py`:
```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

class ViettelScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
```

`scrapers/vnpt.py`:
```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

class VnptScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
```

- [ ] **Step 5: Run factory tests**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -k "factory" -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add scrapers/factory.py scrapers/easyinvoice.py scrapers/misa.py \
        scrapers/petrolimex.py scrapers/viettel.py scrapers/vnpt.py \
        tests/test_scrapers.py
git commit -m "feat: add ScraperFactory with suffix domain routing and scraper stubs"
```

---

## Task 6: easyinvoice.py — full implementation

**Files:**
- Modify: `scrapers/easyinvoice.py`

- [ ] **Step 1: Replace stub with full implementation**

```python
from .base import BaseInvoiceScraper
from .exceptions import InvoiceNotFoundException
from .result import ScrapedResult

_ERROR_TEXT = "text='Mã xác thực không đúng', text='Không tìm thấy'"


class EasyInvoiceScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        self._type(
            "input#Code, input[placeholder*='Mã tra cứu']",
            self.lookup_code,
        )
        self._handle_captcha_if_present()

        self._click(
            "button:has-text('Tra cứu'), button.btn-success, button#btnSearch"
        )
        self._delay(2.0, 3.5)

        if self.page.locator(_ERROR_TEXT).count() > 0:
            raise InvoiceNotFoundException(
                "EasyInvoice: invalid captcha or invoice not found"
            )

        xml_bytes = self._try_download(
            "button:has-text('Tải XML')",
            "a:has-text('Tải XML')",
        )
        if xml_bytes is None:
            master = self.page.locator(
                "button:has-text('Tải về'), a:has-text('Tải về')"
            )
            if master.count() > 0 and master.first.is_visible():
                master.first.hover()
                self._delay(0.3, 0.7)
                master.first.click()
                xml_bytes = self._try_download("text='XML'")

        pdf_bytes = self._try_download(
            "button:has-text('Tải PDF')",
            "a:has-text('Tải PDF')",
        )

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 2: Verify import**

```bash
cd /home/ai/rvc-invoices-bot
python -c "from scrapers.easyinvoice import EasyInvoiceScraper; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scrapers/easyinvoice.py
git commit -m "feat: implement EasyInvoiceScraper with XML+PDF download"
```

---

## Task 7: misa.py — full implementation

**Files:**
- Modify: `scrapers/misa.py`

- [ ] **Step 1: Replace stub with full implementation**

```python
from .base import BaseInvoiceScraper
from .exceptions import InvoiceNotFoundException
from .result import ScrapedResult

_MISA_URL = "https://www.meinvoice.vn/tra-cuu"
_CODE_SEL = 'input[placeholder*="mã" i], input[id*="code" i], input[type="text"]'
_SEARCH_SEL = 'button[type="submit"], button:has-text("Tra cứu"), button:has-text("Tìm kiếm")'


class MisaScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(_MISA_URL, wait_until="networkidle")
        self._scroll()

        self._type(_CODE_SEL, self.lookup_code)
        self._handle_captcha_if_present()
        self._click(_SEARCH_SEL)
        self._delay(2.0, 3.5)

        if self.page.locator("text='Không tìm thấy'").count() > 0:
            raise InvoiceNotFoundException("MISA: invoice not found")

        dropdown = self.page.locator("text='Định dạng XML'")
        if dropdown.count() > 0 and dropdown.first.is_visible():
            self._click("text='Định dạng XML'")

        xml_bytes = self._try_download(
            'a:has-text("XML")',
            'button:has-text("Tải XML")',
            'a[href*=".xml"]',
        )
        pdf_bytes = self._try_download(
            'a:has-text("PDF")',
            'button:has-text("Tải PDF")',
            'a[href*=".pdf"]',
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 2: Verify import**

```bash
cd /home/ai/rvc-invoices-bot
python -c "from scrapers.misa import MisaScraper; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scrapers/misa.py
git commit -m "feat: implement MisaScraper with XML+PDF download"
```

---

## Task 8: petrolimex.py, viettel.py, vnpt.py — full implementations

**Files:**
- Modify: `scrapers/petrolimex.py`
- Modify: `scrapers/viettel.py`
- Modify: `scrapers/vnpt.py`

- [ ] **Step 1: Replace petrolimex.py stub**

```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

_CODE_SEL = (
    'input[id*="lookup" i], input[name*="lookup" i], '
    'input[placeholder*="mã" i], input[type="text"]'
)
_SEARCH_SEL = 'button[type="submit"], button:has-text("Tra cứu"), input[type="submit"]'


class PetrolimexScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()
        self._type(_CODE_SEL, self.lookup_code)
        self._handle_captcha_if_present()
        self._click(_SEARCH_SEL)
        self._delay(2.0, 3.5)
        xml_bytes = self._try_download(
            'a:has-text("XML")', 'a[href*="xml"]', 'button:has-text("XML")'
        )
        pdf_bytes = self._try_download(
            'a:has-text("PDF")', 'a[href*="pdf"]', 'button:has-text("PDF")'
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 2: Replace viettel.py stub**

```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

_VIETTEL_URL = "https://vietteltelecom.vn/hoadondientu"
_CODE_SEL = (
    'input[placeholder*="bí mật" i], input[name*="secret" i], input[type="text"]'
)


class ViettelScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(_VIETTEL_URL, wait_until="networkidle")
        self._scroll()
        self._type(_CODE_SEL, self.lookup_code)
        self._handle_captcha_if_present()
        self._click('button:has-text("Tra cứu"), button[type="submit"]')
        self._delay(2.0, 3.5)
        xml_bytes = self._try_download(
            'a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("Tải XML")'
        )
        pdf_bytes = self._try_download(
            'a:has-text("PDF")', 'a[href*=".pdf"]', 'button:has-text("Tải PDF")'
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 3: Replace vnpt.py stub**

```python
from .base import BaseInvoiceScraper
from .result import ScrapedResult

_VNPT_URL = "https://vnpt-invoice.com.vn/invoice"
_CODE_SEL = (
    'input[placeholder*="mã" i], input[id*="invoice" i], input[type="text"]'
)


class VnptScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(_VNPT_URL, wait_until="networkidle")
        self._scroll()
        self._type(_CODE_SEL, self.lookup_code)
        self._handle_captcha_if_present()
        self._click(
            'button:has-text("Tra cứu"), button:has-text("Tìm"), button[type="submit"]'
        )
        self._delay(2.0, 3.5)
        xml_bytes = self._try_download(
            'a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("XML")'
        )
        pdf_bytes = self._try_download(
            'a:has-text("PDF")', 'a[href*=".pdf"]', 'button:has-text("PDF")'
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 4: Verify all imports**

```bash
cd /home/ai/rvc-invoices-bot
python -c "
from scrapers.petrolimex import PetrolimexScraper
from scrapers.viettel import ViettelScraper
from scrapers.vnpt import VnptScraper
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add scrapers/petrolimex.py scrapers/viettel.py scrapers/vnpt.py
git commit -m "feat: implement PetrolimexScraper, ViettelScraper, VnptScraper"
```

---

## Task 9: __init__.py — public scrape_invoice()

**Files:**
- Modify: `scrapers/__init__.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_scrapers.py`:

```python
from unittest.mock import patch, MagicMock
from scrapers import scrape_invoice
from scrapers.result import ScrapedResult
from scrapers.exceptions import ScraperNotSupportedException


def test_scrape_invoice_raises_for_unknown_domain():
    with pytest.raises(ScraperNotSupportedException):
        scrape_invoice("https://unknown-provider.vn/invoice", "CODE")


def test_scrape_invoice_saves_files_when_download_dir_given(tmp_path):
    mock_result = ScrapedResult(xml_bytes=b"<xml/>", pdf_bytes=b"%PDF")

    with patch("scrapers.sync_playwright") as mock_pw, \
         patch("scrapers.build_stealth_context") as mock_ctx, \
         patch("scrapers.ScraperFactory.get") as mock_factory, \
         patch("scrapers.stealth_sync"):

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_ctx.return_value = (mock_browser, mock_context)
        mock_context.new_page.return_value = mock_page
        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = mock_result
        mock_factory.return_value = mock_scraper
        mock_pw.return_value.__enter__ = lambda s, *a: MagicMock()
        mock_pw.return_value.__exit__ = MagicMock(return_value=False)

        result = scrape_invoice(
            "https://0102362584001hd.easyinvoice.com.vn/Search/Index",
            "CODE123",
            download_dir=str(tmp_path),
        )

    assert result.xml_path is not None
    assert result.pdf_path is not None
    assert (tmp_path / "web_CODE123.xml").exists()
    assert (tmp_path / "web_CODE123.pdf").exists()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py::test_scrape_invoice_raises_for_unknown_domain -v
```

Expected: `ImportError` or `AttributeError` — `scrape_invoice` not yet implemented.

- [ ] **Step 3: Implement scrapers/__init__.py**

```python
import os

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

from .browser import build_stealth_context
from .factory import ScraperFactory
from .result import ScrapedResult


def scrape_invoice(
    url: str,
    lookup_code: str,
    download_dir: str | None = None,
) -> ScrapedResult:
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
                    xml_path = os.path.join(download_dir, f"web_{lookup_code}.xml")
                    with open(xml_path, "wb") as f:
                        f.write(result.xml_bytes)
                    result.xml_path = xml_path
                if result.pdf_bytes is not None:
                    pdf_path = os.path.join(download_dir, f"web_{lookup_code}.pdf")
                    with open(pdf_path, "wb") as f:
                        f.write(result.pdf_bytes)
                    result.pdf_path = pdf_path

            return result
        finally:
            browser.close()
```

- [ ] **Step 4: Run the scrape_invoice tests**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_scrapers.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scrapers/__init__.py tests/test_scrapers.py
git commit -m "feat: implement scrape_invoice() public entry point"
```

---

## Task 10: web_extraction_router.py — remove flat scrapers, add _pick_best_url, rename to process_branch_web

**Files:**
- Modify: `web_extraction_router.py`
- Modify: `tests/test_web_extraction_router.py`

- [ ] **Step 1: Write failing tests for _pick_best_url and process_branch_web**

Add to `tests/test_web_extraction_router.py`:

```python
def test_pick_best_url_prefers_subdomain_over_root():
    from web_extraction_router import _pick_best_url
    urls = [
        "https://easyinvoice.com.vn",
        "https://0102362584001hd.easyinvoice.com.vn/Search/Index",
    ]
    result = _pick_best_url(urls)
    assert "0102362584001hd" in result


def test_pick_best_url_returns_none_for_empty():
    from web_extraction_router import _pick_best_url
    assert _pick_best_url([]) is None


def test_pick_best_url_unknown_domain_falls_back_to_first():
    from web_extraction_router import _pick_best_url
    urls = ["https://unknown.vn/a", "https://another.vn/b"]
    result = _pick_best_url(urls)
    assert result == "https://unknown.vn/a"


def test_process_branch_web_returns_none_when_no_url_or_code():
    import tempfile, os
    from web_extraction_router import process_branch_web

    email = MagicMock()
    email.html = "<p>No invoice info here</p>"
    email.text = "No invoice info here"
    email.uid = "test123"

    with tempfile.TemporaryDirectory() as tmp:
        result = process_branch_web(email, tmp)
    assert result is None


def test_process_branch_web_returns_scraped_result_on_success():
    import tempfile
    from web_extraction_router import process_branch_web
    from scrapers.result import ScrapedResult

    email = MagicMock()
    email.html = (
        '<p>Mã tra cứu: MYCODE123 '
        '<a href="https://0102362584001hd.easyinvoice.com.vn/Search/Index">link</a></p>'
    )
    email.text = "Mã tra cứu: MYCODE123"
    email.uid = "uid999"

    mock_result = ScrapedResult(
        xml_bytes=b"<xml/>",
        xml_path="/tmp/web_MYCODE123.xml",
    )
    with tempfile.TemporaryDirectory() as tmp:
        with patch("web_extraction_router.scrape_invoice", return_value=mock_result):
            result = process_branch_web(email, tmp)

    assert result is not None
    assert result.xml_bytes == b"<xml/>"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_web_extraction_router.py -k "pick_best_url or process_branch_web" -v
```

Expected: `ImportError` — `_pick_best_url` and `process_branch_web` don't exist yet.

- [ ] **Step 3: Edit web_extraction_router.py**

At the top of the file, replace the import block and remove flat scraper code. The full updated file:

```python
import base64
import logging
import os
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers import scrape_invoice
from scrapers.result import ScrapedResult

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
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{60,}={0,2}$")
_VN_DOWNLOAD_TEXT_RE = re.compile(
    r"(Tải XML|Download XML|Xuất XML|Tải PDF|Download PDF)",
    re.IGNORECASE,
)
_HREF_DOWNLOAD_RE = re.compile(
    r"(getXml|exportXml|downloadXml|download)",
    re.IGNORECASE,
)


def extract_xml_from_html_attachment(html_content: str) -> bytes | None:
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all("input", {"type": "hidden"}):
            tag_id = (tag.get("id") or "").lower()
            tag_name = (tag.get("name") or "").lower()
            if "xml" in tag_id or "xml" in tag_name:
                value = tag.get("value", "")
                try:
                    decoded = base64.b64decode(value)
                    if decoded.strip().startswith((b"<?xml", b"<")):
                        return decoded
                except Exception:
                    pass
        for tag in soup.find_all(True):
            for attr_val in tag.attrs.values():
                if not isinstance(attr_val, str):
                    continue
                if _BASE64_RE.match(attr_val.strip()):
                    try:
                        decoded = base64.b64decode(attr_val.strip())
                        if decoded.strip().startswith((b"<?xml", b"<")):
                            return decoded
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"extract_xml_from_html_attachment error: {e}")
    return None


def extract_direct_link(
    email_body_html: str,
    email_body_text: str = "",
) -> tuple[bytes, str] | None:
    combined = email_body_text + " " + email_body_html
    result = _try_direct_download(_extract_urls(combined))
    if result is not None:
        return result
    if not email_body_html:
        return None
    try:
        soup = BeautifulSoup(email_body_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not (_VN_DOWNLOAD_TEXT_RE.search(text) or _HREF_DOWNLOAD_RE.search(href)):
                continue
            try:
                resp = requests.get(href, headers={"User-Agent": USER_AGENT}, timeout=30)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "xml" in ct or resp.content.strip().startswith(b"<?xml"):
                    return resp.content, "xml"
                if "pdf" in ct or resp.content[:4] == b"%PDF":
                    return resp.content, "pdf"
            except Exception as e:
                logger.debug(f"Vietnamese link download failed {href}: {e}")
    except Exception as e:
        logger.debug(f"extract_direct_link BeautifulSoup error: {e}")
    return None


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
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
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


def _pick_best_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    from scrapers.factory import _get_registry
    registry_keys = list(_get_registry().keys())
    known = []
    for url in urls:
        try:
            netloc = urlparse(url).netloc.lower()
            for key in registry_keys:
                if netloc == key or netloc.endswith("." + key):
                    known.append(url)
                    break
        except Exception:
            continue
    candidates = known if known else urls
    return max(candidates, key=lambda u: len(urlparse(u).netloc.split(".")))


def process_branch_web(email, download_dir: str) -> ScrapedResult | None:
    email_body_html = email.html or ""
    email_body_text = email.text or ""
    combined = email_body_text + " " + email_body_html

    logger.debug(f"process_branch_web email body text:\n{email_body_text}")
    logger.debug(f"process_branch_web email body html:\n{email_body_html}")

    # Tier 1: direct link (requests, no Playwright)
    direct = extract_direct_link(email_body_html, email_body_text)
    if direct:
        file_bytes, content_type = direct
        uid = getattr(email, "uid", "unknown")
        fname = os.path.join(download_dir, f"direct_{uid}.{content_type}")
        with open(fname, "wb") as f:
            f.write(file_bytes)
        if content_type == "xml":
            return ScrapedResult(xml_bytes=file_bytes, xml_path=fname)
        return ScrapedResult(pdf_bytes=file_bytes, pdf_path=fname)

    # Tier 2: Playwright scraper
    code = _extract_lookup_code(combined)
    lookup_url = _pick_best_url(_extract_urls(combined))
    if not code or not lookup_url:
        logger.warning("process_branch_web: no lookup code or URL found in email body")
        return None

    for attempt in range(2):
        try:
            result = scrape_invoice(lookup_url, code, download_dir)
            logger.info(f"Playwright scrape success: url={lookup_url} code={code}")
            return result
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Playwright attempt 1 failed ({lookup_url}): {e}, retrying in 3s")
                time.sleep(3)
            else:
                logger.error(f"Playwright attempt 2 failed ({lookup_url}): {e}")
                return None
    return None


class _EmailBodyProxy:
    __slots__ = ("text", "html")

    def __init__(self, text: str, html: str) -> None:
        self.text = text
        self.html = html


def download_invoice_file(body_text: str, body_html: str) -> tuple[bytes, str]:
    """Compatibility shim — wraps process_branch_web for callers using the old signature."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = process_branch_web(_EmailBodyProxy(body_text, body_html), tmp)
    if result is None:
        raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
    if result.xml_bytes is not None:
        return result.xml_bytes, "xml"
    if result.pdf_bytes is not None:
        return result.pdf_bytes, "pdf"
    raise ValueError("ScrapedResult has no bytes")
```


- [ ] **Step 4: Run all web_extraction_router tests**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_web_extraction_router.py -v
```

Expected: all pass (existing tests still pass, new ones pass too).

- [ ] **Step 5: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py
git commit -m "feat: replace flat scrapers with OOP scrape_invoice, add process_branch_web"
```

---

## Task 11: router.py — update WEB branch

**Files:**
- Modify: `router.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Check current router.py WEB branch state**

The ATTACH→WEB fallthrough was partially applied in a prior session. Verify the current state of lines 129–195 in `router.py` before editing. The target state for the full `process_email` try block:

```python
    try:
        if email.attachments:
            branch = "ATTACH"
            had_zip = _dump_and_extract(email, uid_temp)
            pairs = _collect_pairs(uid_temp)
            if pairs:
                for pair in pairs:
                    _process_pair(pair, email, had_zip)
                return
            logger.info(f"No invoice files in attachments — falling through to WEB | uid={email.uid}")

        branch = "WEB"
        logger.info(f"Branch WEB | uid={email.uid} | subject='{subject}'")
        result = web_extraction_router.process_branch_web(email, uid_temp)
        if result is None:
            raise ValueError("All extraction tiers failed — no XML or PDF retrieved")

        pair = {"stem": f"web_{email.uid}"}
        if result.xml_path:
            pair["xml"] = result.xml_path
        if result.pdf_path:
            pair["pdf"] = result.pdf_path
        if "xml" not in pair and "pdf" not in pair:
            raise ValueError("ScrapedResult has no file paths")
        _process_pair(pair, email, had_zip=False)
```

- [ ] **Step 2: Write a failing test for the WEB branch**

Add to `tests/test_router.py` (check existing file first to avoid duplicate fixtures):

```python
def test_process_email_web_branch_calls_process_pair(tmp_path, monkeypatch):
    import router
    from scrapers.result import ScrapedResult

    xml_file = tmp_path / "web_CODE.xml"
    xml_file.write_bytes(b"<xml/>")
    mock_result = ScrapedResult(
        xml_bytes=b"<xml/>",
        xml_path=str(xml_file),
    )

    email = MagicMock()
    email.attachments = []
    email.subject = "Invoice"
    email.from_ = "sender@example.com"
    email.date = MagicMock(strftime=lambda f: "10:00")
    email.uid = "uid001"
    email.html = '<a href="https://0102362584001hd.easyinvoice.com.vn/Search/Index">link</a>'
    email.text = "Mã tra cứu: CODE"

    with patch("router.web_extraction_router.process_branch_web", return_value=mock_result), \
         patch("router._process_pair") as mock_pair, \
         patch("router.shutil.rmtree"), \
         patch("router.email_handler.mark_as_seen"):
        router.process_email(email)

    mock_pair.assert_called_once()
    call_args = mock_pair.call_args[0]
    assert call_args[0].get("xml") == str(xml_file)
```

- [ ] **Step 3: Run test to confirm failure**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_router.py::test_process_email_web_branch_calls_process_pair -v
```

Expected: `AttributeError: module 'web_extraction_router' has no attribute 'process_branch_web'` — or similar, depending on current state.

- [ ] **Step 4: Apply the WEB branch change to router.py**

Find and replace the entire `try` block in `process_email` (lines ~129–194) with the target state shown in Step 1. Use the Edit tool, matching the exact current content.

- [ ] **Step 5: Run all router tests**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/test_router.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full test suite**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/ -v
```

Expected: all pass. Fix any breakage before continuing.

- [ ] **Step 7: Commit**

```bash
git add router.py tests/test_router.py
git commit -m "feat: update router WEB branch to use process_branch_web and _process_pair"
```

---

## Task 12: Cleanup and smoke test

**Files:**
- Delete: `/home/ai/scrapers/` (standalone directory)

- [ ] **Step 1: Delete the old standalone scrapers directory**

```bash
rm -rf /home/ai/scrapers
```

- [ ] **Step 2: Confirm no imports reference the old path**

```bash
grep -r "from /home/ai/scrapers\|import /home/ai/scrapers" /home/ai/rvc-invoices-bot/ 2>/dev/null || echo "clean"
```

Expected: `clean`

- [ ] **Step 3: Run full test suite one final time**

```bash
cd /home/ai/rvc-invoices-bot
python -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Verify the package structure is complete**

```bash
ls /home/ai/rvc-invoices-bot/scrapers/
```

Expected:
```
__init__.py  base.py  browser.py  easyinvoice.py  exceptions.py
factory.py   misa.py  petrolimex.py  result.py  viettel.py  vnpt.py
```

- [ ] **Step 5: Smoke test imports**

```bash
cd /home/ai/rvc-invoices-bot
python -c "
from scrapers import scrape_invoice
from scrapers.result import ScrapedResult
from scrapers.factory import ScraperFactory
from scrapers.exceptions import CaptchaRequiredException, InvoiceNotFoundException, ScraperNotSupportedException
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: remove superseded /home/ai/scrapers standalone directory"
```
