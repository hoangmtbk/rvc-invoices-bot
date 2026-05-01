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
