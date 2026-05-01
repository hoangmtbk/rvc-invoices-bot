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
