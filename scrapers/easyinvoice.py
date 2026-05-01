from .base import BaseInvoiceScraper
from .exceptions import InvoiceNotFoundException
from .result import ScrapedResult

_ERROR_SELECTORS = (
    "text='Mã xác thực không đúng'",
    "text='Không tìm thấy'",
)


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

        for sel in _ERROR_SELECTORS:
            if self.page.locator(sel).count() > 0:
                raise InvoiceNotFoundException(
                    "EasyInvoice: invalid captcha or invoice not found"
                )

        xml_bytes = self._try_download(
            "button:has-text('Tải tệp XML')",
            "a:has-text('Tải tệp XML')",
        )
        if xml_bytes is None:
            master = self.page.locator(
                "button:has-text('Tải về'), a:has-text('Tải về')"
            )
            if master.count() > 0 and master.first.is_visible():
                master.first.hover()
                self._delay(0.3, 0.7)
                master.first.click()
                xml_bytes = self._try_download("text='Tải tệp XML'")

        pdf_bytes = self._try_download(
            "button:has-text('Tải PDF')",
            "a:has-text('Tải PDF')",
        )

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
