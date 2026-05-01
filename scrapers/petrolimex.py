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
