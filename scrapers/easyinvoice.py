import io
import logging
import zipfile

from .base import BaseInvoiceScraper
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

_CODE_SEL = "input#Code, input[placeholder*='Mã tra cứu'], input[placeholder*='mã tra cứu' i]"
_SUBMIT_SEL = "button:has-text('Tra cứu'), button.btn-success, button#btnSearch"

_XML_SELS = (
    "button:has-text('Tải tệp XML')",
    "a:has-text('Tải tệp XML')",
    "text='Tải tệp XML'",
)
_PDF_SELS = (
    "button:has-text('Tải PDF')",
    "a:has-text('Tải PDF')",
)

_ERROR_TEXTS = ("Mã xác thực không đúng", "Không tìm thấy")
_MAX_RETRIES = 2


class EasyInvoiceScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        # ViewFromEmail / token URLs already display the invoice — skip lookup form.
        is_direct_view = "ViewFromEmail" in self.url or (
            "token=" in self.url and "tra-cuu" not in self.url.lower()
        )

        if is_direct_view:
            logger.info("EasyInvoice: direct-view URL — skipping search form")
            self._delay(1.5, 2.5)
        else:
            self._search_with_retry()

        xml_bytes = self._try_download(*_XML_SELS)
        if xml_bytes is None:
            # Some pages put XML behind a "Tải về" master dropdown
            master = self.page.locator("button:has-text('Tải về'), a:has-text('Tải về')")
            if master.count() > 0 and master.first.is_visible():
                master.first.hover()
                self._delay(0.3, 0.7)
                master.first.click()
                xml_bytes = self._try_download("text='Tải tệp XML'")

        pdf_bytes = self._try_download(*_PDF_SELS)

        if xml_bytes is not None:
            xml_bytes = _unzip_if_needed(xml_bytes, "xml")
        if pdf_bytes is not None:
            pdf_bytes = _unzip_if_needed(pdf_bytes, "pdf")

        logger.info(
            "EasyInvoice: url='%s' xml=%s pdf=%s",
            self.url,
            f"{len(xml_bytes)}B" if xml_bytes else "none",
            f"{len(pdf_bytes)}B" if pdf_bytes else "none",
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    def _search_with_retry(self) -> None:
        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            self._handle_captcha_if_present()
            self._click(_SUBMIT_SEL)
            self._delay(2.0, 3.5)

            for err_text in _ERROR_TEXTS:
                if self.page.locator(f"text='{err_text}'").count() > 0:
                    if "Không tìm thấy" in err_text:
                        raise InvoiceNotFoundException(
                            f"EasyInvoice: invoice not found for '{self.lookup_code}'"
                        )
                    # "Mã xác thực không đúng" — retry if attempts remain
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "EasyInvoice: '%s' on attempt %d, retrying", err_text, attempt + 1
                        )
                        self._delay(1.5, 2.0)
                        break
                    raise CaptchaRequiredException(
                        f"EasyInvoice: {err_text} after {_MAX_RETRIES} attempts"
                    )
            else:
                return  # No error text seen — assume success

    def _enter_code(self) -> None:
        el = self.page.locator(_CODE_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.2)
        el.press_sequentially(self.lookup_code, delay=100)
        self._delay(0.2, 0.5)


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
