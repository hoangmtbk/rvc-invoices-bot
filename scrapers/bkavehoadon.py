import logging
import os
import time

from .base import BaseInvoiceScraper
from .exceptions import InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# Navigate to the lookup URL — the page auto-opens a jQuery UI modal with an
# iframe (#frameViewInvoice) that contains the invoice and download buttons.
# No captcha, no search form to fill: the MTC code is passed as a URL query param.
_FRAME_NAME       = "frameViewInvoice"
_BTN_DOWNLOAD_SEL = "#btnDownload"           # hover to reveal dropdown in iframe
_XML_SEL          = "#LinkDownXML"           # a:has-text('Hóa đơn dạng XML')
_PDF_SEL          = "#LinkDownPDF"           # a:has-text('Hóa đơn dạng PDF')
_NOT_FOUND_TEXT   = "không tìm thấy"         # body text when code is invalid


class BKAVeHoadonScraper(BaseInvoiceScraper):
    """Scraper for BKAV eHoadon portal (tchd.ehoadon.vn).

    Flow:
      1. Navigate to https://tchd.ehoadon.vn/TCHD?MTC=<code>
         → page auto-opens a jQuery UI modal with an iframe (frameViewInvoice)
      2. Wait for the iframe to load
      3. Hover #btnDownload inside the iframe to reveal the download dropdown
      4. Download XML via #LinkDownXML  (ASP.NET __doPostBack)
      5. Download PDF via #LinkDownPDF  (DownloadFile() onclick)
    """

    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()

        # Build the direct lookup URL — use the code embedded in the URL path
        # if the URL already has the right format, otherwise construct it.
        lookup_url = self._build_lookup_url()
        logger.info("BKAVeHoadon: navigating to %s", lookup_url)
        self.page.goto(lookup_url, wait_until="networkidle")

        # Check for "not found" on the main page
        body_text = self.page.evaluate("() => document.body.innerText").lower()
        if _NOT_FOUND_TEXT in body_text and self.page.locator(_FRAME_NAME).count() == 0:
            raise InvoiceNotFoundException(
                f"BKAVeHoadon: invoice not found for '{self.lookup_code}'"
            )

        # Wait for the iframe to attach
        try:
            self.page.locator(f"#{_FRAME_NAME}").wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            raise InvoiceNotFoundException(
                f"BKAVeHoadon: invoice modal did not open for '{self.lookup_code}': {exc}"
            ) from exc

        # Obtain the frame object
        frame = self.page.frame(name=_FRAME_NAME)
        if frame is None:
            for f in self.page.frames:
                if "Lookup" in f.url:
                    frame = f
                    break
        if frame is None:
            raise InvoiceNotFoundException(
                f"BKAVeHoadon: could not find frameViewInvoice for '{self.lookup_code}'"
            )

        try:
            frame.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            self._delay(2.0, 3.0)

        # Hover #btnDownload to reveal the hidden download links
        btn = frame.locator(_BTN_DOWNLOAD_SEL)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.hover()
            self._delay(0.5, 0.9)
        else:
            logger.warning("BKAVeHoadon: #btnDownload not found, proceeding anyway")

        # Download XML
        xml_bytes = self._download_from_frame(frame, _XML_SEL)

        # Download PDF
        pdf_bytes = self._download_from_frame(frame, _PDF_SEL)

        logger.info(
            "BKAVeHoadon: xml=%s pdf=%s",
            f"{len(xml_bytes)}B" if xml_bytes else "none",
            f"{len(pdf_bytes)}B" if pdf_bytes else "none",
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    def _build_lookup_url(self) -> str:
        """Return https://tchd.ehoadon.vn/TCHD?MTC=<code>.

        If the incoming url already points at tchd.ehoadon.vn we use it as-is
        (it may already have MTC in the query string from _pick_best_url).
        Otherwise construct the canonical lookup URL.
        """
        from urllib.parse import urlparse, urlencode, urlunparse, parse_qs
        parsed = urlparse(self.url)
        host = (parsed.hostname or "").lower()
        qs = parse_qs(parsed.query)
        # If code already present in URL, use the URL as-is
        if host == "tchd.ehoadon.vn" and "MTC" in qs:
            return self.url
        # Build canonical URL
        return f"https://tchd.ehoadon.vn/TCHD?MTC={self.lookup_code}"

    def _download_from_frame(self, frame, selector: str) -> bytes | None:
        """Click a link inside the iframe and capture the download on the parent page."""
        loc = frame.locator(selector)
        if loc.count() == 0:
            logger.debug("BKAVeHoadon: selector %r not found in frame", selector)
            return None
        try:
            with self.page.expect_download(timeout=15_000) as dl:
                loc.first.hover()
                self._delay(0.2, 0.4)
                loc.first.click()
            path = dl.value.path()
            with open(path, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.warning("BKAVeHoadon: download failed for %r: %s", selector, exc)
            return None
