import logging
import os
import random
import re
import tempfile

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageFilter

from .base import BaseInvoiceScraper, _get_gemini_client, capsolver_solve_image
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
# Submit button text is "Tìm kiếm"
_SUBMIT_SEL = 'button:has-text("Tìm kiếm"), #SearchformByfkey button[type="submit"], button[type="submit"]'
# Both files are labelled "Tải" — classify by content after download
_DOWNLOAD_LINK_SEL = 'a:has-text("Tải")'

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

            if self._page_says_not_found():
                raise InvoiceNotFoundException(
                    f"Petrolimex: invoice not found for '{self.lookup_code}'"
                )
            if self._downloads_visible():
                break

            if attempt < _MAX_RETRIES - 1:
                logger.warning(
                    "Petrolimex: no downloads after attempt %d, reloading", attempt + 1
                )
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
            return _solve_petrolimex_captcha(captcha_path)
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
        btn.wait_for(state="visible", timeout=10_000)
        btn.hover()
        self._delay(0.3, 0.8)
        btn.click()
        self._delay(2.5, 4.0)

    def _page_says_not_found(self) -> bool:
        text: str = self.page.evaluate("() => document.body.innerText.toLowerCase()")
        return "không tìm thấy" in text or "không có hóa đơn" in text

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


def _solve_petrolimex_captcha(image_path: str) -> str:
    """Solve 4-digit numeric captcha: ddddocr → Capsolver (if key set) → Gemini."""
    # Solver 1: ddddocr
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        with open(image_path, "rb") as f:
            raw = re.sub(r"\s+", "", ocr.classification(f.read()))
        if re.fullmatch(r"[0-9]{4}", raw):
            logger.info("Petrolimex: ddddocr captcha = '%s'", raw)
            return raw
        logger.debug("Petrolimex: ddddocr returned '%s', trying next solver", raw)
    except Exception as exc:
        logger.debug("Petrolimex: ddddocr failed: %s", exc)

    # Solver 2: Capsolver (only when CAPSOLVER_API_KEY env var is set)
    if os.environ.get("CAPSOLVER_API_KEY"):
        try:
            cap_result = capsolver_solve_image(image_path)
            if cap_result:
                stripped = re.sub(r"\s+", "", cap_result)
                if re.fullmatch(r"[0-9]{4}", stripped):
                    logger.info("Petrolimex: Capsolver captcha = '%s'", stripped)
                    return stripped
            logger.debug("Petrolimex: Capsolver returned '%s', falling back to Gemini", cap_result)
        except Exception as exc:
            logger.debug("Petrolimex: Capsolver failed: %s", exc)

    # Solver 3: Gemini with Pillow preprocessing
    img = PIL.Image.open(image_path).convert("L")
    w, h = img.size
    img = img.resize((w * 4, h * 4), PIL.Image.LANCZOS)
    img = img.filter(PIL.ImageFilter.SHARPEN)
    img = PIL.ImageEnhance.Contrast(img).enhance(2.5)
    img = img.convert("RGB")
    response = _get_gemini_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "This is a captcha image showing exactly 4 digits (0–9 only). "
            "Return ONLY the 4-digit sequence with no spaces or explanation.",
            img,
        ],
    )
    raw = response.text.strip()
    logger.info("Petrolimex: Gemini raw captcha response = '%s'", raw)
    return re.sub(r"\s+", "", raw)
