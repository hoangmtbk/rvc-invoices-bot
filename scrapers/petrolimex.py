import logging

from .base import BaseInvoiceScraper
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# hoadon.petrolimex.com.vn — uses self.url (portal URL from email)
_CODE_SEL = (
    'input[id*="lookup" i], '
    'input[name*="lookup" i], '
    'input[placeholder*="mã tra cứu" i], '
    'input[placeholder*="mã" i], '
    'input[type="text"]'
)
_SUBMIT_SEL = 'button[type="submit"], button:has-text("Tra cứu"), input[type="submit"]'

_XML_SELS = (
    'a:has-text("XML")',
    'button:has-text("XML")',
    'a[href*="xml" i]',
    'button:has-text("Tải XML")',
)
_PDF_SELS = (
    'a:has-text("PDF")',
    'button:has-text("PDF")',
    'a[href*="pdf" i]',
    'button:has-text("Tải PDF")',
)

_MAX_RETRIES = 2


class PetrolimexScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            self._handle_captcha_if_present()
            self._click(_SUBMIT_SEL)
            self._delay(2.5, 4.0)

            if self._page_says_not_found():
                raise InvoiceNotFoundException(
                    f"Petrolimex: invoice not found for '{self.lookup_code}'"
                )
            if self._downloads_visible():
                break
            if attempt < _MAX_RETRIES - 1:
                logger.warning(
                    "Petrolimex: no download buttons after attempt %d, retrying", attempt + 1
                )
                self._delay(1.5, 2.5)
            else:
                raise CaptchaRequiredException(
                    f"Petrolimex: no results after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
                )

        xml_bytes = self._try_download(*_XML_SELS)
        pdf_bytes = self._try_download(*_PDF_SELS)

        logger.info(
            "Petrolimex: code='%s' xml=%s pdf=%s",
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

    def _page_says_not_found(self) -> bool:
        text: str = self.page.evaluate("() => document.body.innerText.toLowerCase()")
        return "không tìm thấy" in text or "không có hóa đơn" in text

    def _downloads_visible(self) -> bool:
        return any(
            self.page.locator(s).count() > 0 for s in (*_XML_SELS, *_PDF_SELS)
        )
