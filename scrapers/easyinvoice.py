import io
import zipfile

from .base import BaseInvoiceScraper
from .exceptions import InvoiceNotFoundException
from .result import ScrapedResult


def _unzip_if_needed(data: bytes, ext: str) -> bytes:
    """If data is a ZIP, extract the first entry matching ext; otherwise return as-is."""
    if data[:2] != b"PK":
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.lower().endswith("." + ext):
                    return zf.read(name)
    except Exception:
        pass
    return data

_ERROR_SELECTORS = (
    "text='Mã xác thực không đúng'",
    "text='Không tìm thấy'",
)


class EasyInvoiceScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        # ViewFromEmail / token-based URLs already display the invoice directly —
        # skip the lookup-code entry step.
        _is_direct_view = "ViewFromEmail" in self.url or (
            "token=" in self.url and "tra-cuu" not in self.url.lower()
        )

        if not _is_direct_view:
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
        else:
            self._delay(1.5, 2.5)

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

        if xml_bytes is not None:
            xml_bytes = _unzip_if_needed(xml_bytes, "xml")
        if pdf_bytes is not None:
            pdf_bytes = _unzip_if_needed(pdf_bytes, "pdf")

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
