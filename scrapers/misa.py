import logging
import os
import random
import re
import tempfile

from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

_MISA_URL = "https://www.meinvoice.vn/tra-cuu"

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

_XML_SELS = (
    'a:has-text("XML")',
    'button:has-text("Tải XML")',
    'a[href*=".xml"]',
)
_PDF_SELS = (
    'a:has-text("PDF")',
    'button:has-text("Tải PDF")',
    'a[href*=".pdf"]',
)

_MAX_RETRIES = 3


class MisaScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(_MISA_URL, wait_until="networkidle")
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
            if self._downloads_visible():
                break
            if attempt < _MAX_RETRIES - 1:
                logger.warning("MISA: no download buttons after attempt %d, reloading", attempt + 1)
                self.page.reload(wait_until="networkidle")
        else:
            raise CaptchaRequiredException(
                f"MISA: no results after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
            )

        # Some MISA pages nest XML behind a "Định dạng XML" dropdown
        dropdown = self.page.locator("text='Định dạng XML'")
        if dropdown.count() > 0 and dropdown.first.is_visible():
            self._click("text='Định dạng XML'")
            self._delay(0.5, 1.0)

        xml_bytes = self._try_download(*_XML_SELS)
        pdf_bytes = self._try_download(*_PDF_SELS)

        logger.info(
            "MISA: code='%s' xml=%s pdf=%s",
            self.lookup_code,
            f"{len(xml_bytes)}B" if xml_bytes else "none",
            f"{len(pdf_bytes)}B" if pdf_bytes else "none",
        )
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

    def _downloads_visible(self) -> bool:
        return any(
            self.page.locator(s).count() > 0 for s in (*_XML_SELS, *_PDF_SELS)
        )
