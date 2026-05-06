import html as _html
import logging
import os
import random
import re
import tempfile

from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

_MISA_BASE = "https://www.meinvoice.vn/tra-cuu"

# Dropdown trigger and hidden item selectors
_DOWNLOAD_SPAN = "span.download-invoice"
_PDF_SEL = "div.txt-download-pdf"
_XML_SEL = "div.txt-download-xml"

# Fallback form selectors (used when no sc= param in URL)
_CODE_SEL = (
    'input[placeholder*="mã tra cứu" i], '
    'input[name*="invoiceCode" i], '
    'input[id*="code" i], '
    'input[placeholder*="mã" i]'
)
_CAPTCHA_IMG_SEL = (
    'img[src*="captcha" i], img[id*="captcha" i], img[class*="captcha" i]'
)
_CAPTCHA_INPUT_SEL = (
    'input[id*="captcha" i], input[placeholder*="xác thực" i]'
)
_SUBMIT_SEL = 'button[type="submit"], button:has-text("Tra cứu"), button:has-text("Tìm kiếm")'

_MAX_RETRIES = 3


class MisaScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()

        # HTML-unescape URL to convert &amp; → & (common in email HTML bodies)
        nav_url = _html.unescape(self.url)

        self.page.goto(nav_url, wait_until="networkidle", timeout=30_000)
        self._delay(2.0, 3.5)

        # sc= param auto-loads invoice — wait for result section
        if not self._wait_for_invoice():
            # Fallback: fill the search form manually
            self._form_fill_flow()

        # Download PDF and XML via dispatch_event (items hidden by CSS hover)
        pdf_bytes = self._download_item(_PDF_SEL)
        xml_bytes = self._download_item(_XML_SEL)

        logger.info(
            "MISA: code='%s' xml=%s pdf=%s",
            self.lookup_code,
            f"{len(xml_bytes)}B" if xml_bytes else "none",
            f"{len(pdf_bytes)}B" if pdf_bytes else "none",
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    def _wait_for_invoice(self, timeout: int = 12_000) -> bool:
        """Return True when span.download-invoice becomes visible (invoice loaded)."""
        try:
            self.page.locator(_DOWNLOAD_SPAN).wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def _download_item(self, sel: str) -> bytes | None:
        """Trigger download of the hidden dropdown item via dispatch_event('click')."""
        loc = self.page.locator(sel)
        if loc.count() == 0:
            logger.warning("MISA: selector %r not found on page", sel)
            return None
        try:
            with self.page.expect_download(timeout=20_000) as dl:
                loc.first.dispatch_event("click")
            path = dl.value.path()
            with open(path, "rb") as f:
                data = f.read()
            logger.info("MISA: downloaded %r → %d bytes", sel, len(data))
            return data
        except Exception as exc:
            logger.warning("MISA: _download_item(%r) failed: %s", sel, exc)
            return None

    # ---- fallback form-fill flow ----

    def _form_fill_flow(self) -> None:
        """Navigate to base form URL, enter code + captcha, submit, wait for result."""
        if _MISA_BASE not in self.page.url:
            self.page.goto(_MISA_BASE, wait_until="networkidle")
            self._scroll()

        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            solution = self._screenshot_and_solve_captcha()
            if solution:
                self._enter_captcha(solution)
            self._click(_SUBMIT_SEL)
            self._delay(2.5, 4.0)

            if self._page_says_not_found():
                raise InvoiceNotFoundException(
                    f"MISA: invoice not found for '{self.lookup_code}'"
                )
            if self._wait_for_invoice(timeout=5_000):
                return
            if attempt < _MAX_RETRIES - 1:
                logger.warning("MISA: no download buttons after attempt %d, reloading", attempt + 1)
                self.page.reload(wait_until="networkidle")

        raise CaptchaRequiredException(
            f"MISA: no results after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
        )

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
            logger.info("MISA: Capsolver captcha result = '%s'", result)
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
        return "không tìm thấy" in text or "không có hóa đơn" in text
