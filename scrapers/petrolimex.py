import logging
import os
import random
import re
import tempfile
import time

from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# Selectors from playwright codegen — hoadon.petrolimex.com.vn
# Lookup code: label contains "mã tra cứu" — match via adjacent label has-text
_CODE_SEL = '#SearchformByfkey input[type="text"], label:has-text("mã tra cứu") + input, label:has-text("mã tra cứu") ~ input, input[name*="fkey" i], input[id*="fkey" i]'
# Captcha — form ID is #SearchformByfkey, input ID is #captch (NOT #captcha)
_CAPTCHA_IMG_SEL = (
    '#SearchformByfkey img[src*="captch" i], '
    '#SearchformByfkey img[src*="Captcha" i], '
    'img[src*="captch" i]'
)
_CAPTCHA_INPUT_SEL = '#SearchformByfkey #captch'
# Submit — try form-scoped first, then broad fallbacks (input or button)
_SUBMIT_SEL = (
    '#SearchformByfkey button[type="submit"], '
    '#SearchformByfkey input[type="submit"], '
    '#SearchformByfkey button, '
    'button:has-text("Tìm"), '
    'button:has-text("Tra cứu"), '
    'input[type="submit"], '
    'button[type="submit"]'
)
# Both files are labelled "Tải" — classify by content after download
_DOWNLOAD_LINK_SEL = 'a:has-text("Tải")'
# Result table appears after a successful submit; use as wait anchor
_RESULT_TABLE_SEL = 'table, .danh-sach, #SearchformByfkey ~ *, a:has-text("Tải")'
# Captcha wrong — server shows one of these messages
_CAPTCHA_ERROR_TEXTS = ("mã xác thực", "sai mã", "nhập lại", "captcha", "verification")

_MAX_RETRIES = 3


class PetrolimexScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution or not re.fullmatch(r"[0-9]{4}", solution):
                logger.warning(
                    "Petrolimex: invalid captcha solution '%s' on attempt %d, reloading",
                    solution, attempt + 1,
                )
                if attempt < _MAX_RETRIES - 1:
                    self.page.reload(wait_until="networkidle")
                continue

            logger.info(
                "Petrolimex attempt %d/%d: captcha='%s'", attempt + 1, _MAX_RETRIES, solution
            )
            self._enter_captcha(solution)
            self._click_submit()

            body = self.page.evaluate("() => document.body.innerText").lower()
            if self._captcha_error_in_body(body):
                logger.warning(
                    "Petrolimex: captcha rejected by server on attempt %d", attempt + 1
                )
                if attempt < _MAX_RETRIES - 1:
                    self.page.reload(wait_until="networkidle")
                continue

            if "không tìm thấy" in body or "không có hóa đơn" in body:
                raise InvoiceNotFoundException(
                    f"Petrolimex: invoice not found for '{self.lookup_code}'"
                )
            if self._downloads_visible():
                break

            logger.warning(
                "Petrolimex: no downloads after attempt %d — page body (300 chars): %s",
                attempt + 1, body[:300],
            )
            if attempt < _MAX_RETRIES - 1:
                self.page.reload(wait_until="networkidle")
        else:
            raise CaptchaRequiredException(
                f"Petrolimex: captcha failed after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
            )

        xml_bytes, pdf_bytes = self._download_all()

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
            logger.info("Petrolimex: Capsolver captcha result = '%s'", result)
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

    def _click_submit(self) -> None:
        btn = self.page.locator(_SUBMIT_SEL).first
        btn.wait_for(state="visible", timeout=15_000)
        btn.hover()
        self._delay(0.3, 0.8)
        btn.click()
        # Wait for EITHER download links OR any result/error content to appear
        try:
            self.page.wait_for_selector(
                _DOWNLOAD_LINK_SEL + ", .field-validation-error, #alert",
                timeout=15_000,
            )
        except Exception:
            # fallback: give the page extra time to settle
            time.sleep(6)

    def _captcha_error_in_body(self, body_lower: str) -> bool:
        return any(kw in body_lower for kw in _CAPTCHA_ERROR_TEXTS)

    def _downloads_visible(self) -> bool:
        return self.page.locator(_DOWNLOAD_LINK_SEL).count() > 0

    def _download_all(self) -> tuple[bytes | None, bytes | None]:
        """Download every 'Tải' link and classify content as XML or PDF."""
        xml_bytes: bytes | None = None
        pdf_bytes: bytes | None = None
        links = self.page.locator(_DOWNLOAD_LINK_SEL)
        count = links.count()
        for i in range(count):
            try:
                with self.page.expect_download(timeout=15_000) as dl:
                    links.nth(i).hover()
                    self._delay(0.2, 0.5)
                    links.nth(i).click()
                path = dl.value.path()
                with open(path, "rb") as f:
                    data = f.read()
                ctype = self._classify_bytes(data)
                if ctype == "xml" and xml_bytes is None:
                    xml_bytes = data
                    logger.info("Petrolimex: link[%d] → XML (%d bytes)", i, len(data))
                elif ctype == "pdf" and pdf_bytes is None:
                    pdf_bytes = data
                    logger.info("Petrolimex: link[%d] → PDF (%d bytes)", i, len(data))
                else:
                    logger.debug("Petrolimex: link[%d] unrecognised type '%s'", i, ctype)
            except Exception as exc:
                logger.debug("Petrolimex: link[%d] download failed: %s", i, exc)
        return xml_bytes, pdf_bytes


