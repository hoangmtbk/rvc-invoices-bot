import logging
import os
import random
import re
import tempfile

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageFilter

from .base import BaseInvoiceScraper, _get_gemini_client
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# Selectors derived from https://vttphcm-tt78.vnpt-invoice.com.vn/ HTML inspection
_CODE_SEL = 'input#strFkey, input[name="strFkey"]'
_CAPTCHA_IMG = "img.captcha_img, img[src*='/Captcha/Show' i]"
_CAPTCHA_INPUT = 'input#captch, input[name="captch"]'
_SUBMIT_BTN = 'button[name="submit"][type="submit"], button.btn-search, button[type="submit"]'
# Results land in #ReportViewInv; fall back to any visible table row
_RESULT_ROW = "#ReportViewInv table tbody tr, table tbody tr"

# jQuery Unobtrusive Validation injects this span when /Captcha/ValidateCaptcha returns false.
# data-val-remote="ErrorMessage" is the message; the span gets class field-validation-error.
_CAPTCHA_VAL_ERROR_SEL = (
    'span[data-valmsg-for="captch"].field-validation-error, '
    'span[data-valmsg-for="captch"]:not(.field-validation-valid)'
)

_MAX_CAPTCHA_RETRIES = 3

# Column headers visible in the result table (see UI screenshot)
_COL_TAI_FILE = "Tải File"       # col 11 — main invoice download (XML or PDF)
_COL_TAI_BANG_KE = "Tải bảng kê"  # col 12 — secondary file (often different format)


class VnptScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        if self._probe_bypass():
            logger.info("VNPT: captcha bypass confirmed — skipping OCR loop")
            self._assert_invoice_found()
            xml_bytes, pdf_bytes = self._download_all_files()
            if xml_bytes is None and pdf_bytes is None:
                raise InvoiceNotFoundException(
                    f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
                )
            return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

        for attempt in range(_MAX_CAPTCHA_RETRIES):
            self._fill_lookup_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution:
                raise CaptchaRequiredException("VNPT: Gemini returned empty captcha solution")
            logger.info("VNPT attempt %d/%d: captcha='%s'", attempt + 1, _MAX_CAPTCHA_RETRIES, solution)
            self._enter_captcha(solution)

            if self._submit_and_wait_for_results():
                break

            if attempt < _MAX_CAPTCHA_RETRIES - 1:
                logger.warning("VNPT: results table absent after attempt %d, refreshing captcha", attempt + 1)
                self._refresh_captcha_image()
            else:
                raise CaptchaRequiredException(
                    f"VNPT: captcha failed after {_MAX_CAPTCHA_RETRIES} attempts"
                )

        self._assert_invoice_found()

        xml_bytes, pdf_bytes = self._download_all_files()

        if xml_bytes is None and pdf_bytes is None:
            raise InvoiceNotFoundException(
                f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
            )

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    # ── form interaction ────────────────────────────────────────────────────

    def _fill_lookup_code(self) -> None:
        el = self.page.locator(_CODE_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.triple_click()
        self._delay(0.1, 0.3)
        el.press_sequentially(self.lookup_code, delay=80)
        self._delay(0.2, 0.5)

    def _probe_bypass(self) -> bool:
        """Submit with dummy captcha '0000' to detect absent server-side validation."""
        try:
            self._fill_lookup_code()
            self._enter_captcha("0000")
            result = self._submit_and_wait_for_results()
            logger.info("VNPT: bypass probe result=%s", result)
            return result
        except Exception as exc:
            logger.debug("VNPT: bypass probe error: %s", exc)
            return False

    def _enter_captcha(self, solution: str) -> None:
        """
        Clear the captcha input (triple-click selects all) then type the solution.
        _type() from the base class places cursor but does NOT clear existing text —
        on a retry the old wrong digits would be left in the field.
        """
        el = self.page.locator(_CAPTCHA_INPUT).first
        el.wait_for(state="visible", timeout=10_000)
        el.triple_click()                                      # select all
        self._delay(0.1, 0.2)
        el.press_sequentially(solution, delay=random.randint(80, 150))
        self._delay(0.2, 0.5)

    def _submit_and_wait_for_results(self) -> bool:
        btn = self.page.locator(_SUBMIT_BTN).first
        btn.wait_for(state="visible", timeout=10_000)
        btn.hover()
        self._delay(0.3, 0.8)
        # no_wait_after=True: form uses jQuery remote validation (AJAX) then POSTs;
        # we must not block on the navigation ourselves — wait_for_selector handles it.
        btn.click(no_wait_after=True)
        try:
            # Fastest signal of success: result row.
            # Fastest signal of wrong captcha: jQuery injects span.field-validation-error.
            self.page.wait_for_selector(
                f"{_RESULT_ROW}, {_CAPTCHA_VAL_ERROR_SEL}, .text-danger:not(:empty)",
                state="visible",
                timeout=15_000,
            )
        except Exception:
            return False
        if self.page.locator(_CAPTCHA_VAL_ERROR_SEL).count() > 0:
            logger.warning(
                "VNPT: jQuery captcha validation error — '%s'",
                self.page.locator(_CAPTCHA_VAL_ERROR_SEL).first.inner_text(),
            )
            return False
        return self.page.locator(_RESULT_ROW).count() > 0

    def _refresh_captcha_image(self) -> None:
        """
        Force a new captcha by changing src with a timestamp query param.
        Clicking a bare <img> does nothing — the browser must re-request the URL.
        """
        self.page.evaluate(
            """() => {
                const img = document.querySelector('img.captcha_img, img[src*="/Captcha/Show" i]');
                if (!img) return;
                const base = img.src.split('?')[0];
                img.src = base + '?t=' + Date.now();
            }"""
        )
        # Wait for the new captcha image download to complete
        try:
            self.page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            self._delay(1.0, 1.5)

    # ── result validation ───────────────────────────────────────────────────

    def _assert_invoice_found(self) -> None:
        not_found: bool = self.page.evaluate(
            """() => {
                const t = document.body.innerText.toLowerCase();
                return t.includes('không tìm thấy') || t.includes('không có hóa đơn');
            }"""
        )
        if not_found:
            raise InvoiceNotFoundException(
                f"VNPT: invoice not found for lookup code '{self.lookup_code}'"
            )

    # ── file downloads ──────────────────────────────────────────────────────

    def _download_all_files(self) -> tuple[bytes | None, bytes | None]:
        """Try every download column; classify by content and return (xml, pdf)."""
        xml_bytes: bytes | None = None
        pdf_bytes: bytes | None = None

        for col_name in (_COL_TAI_FILE, _COL_TAI_BANG_KE):
            data = self._download_column(col_name)
            if data is None:
                continue
            ctype = _classify_bytes(data)
            if ctype == "xml" and xml_bytes is None:
                logger.info("VNPT: '%s' → XML (%d bytes)", col_name, len(data))
                xml_bytes = data
            elif ctype == "pdf" and pdf_bytes is None:
                logger.info("VNPT: '%s' → PDF (%d bytes)", col_name, len(data))
                pdf_bytes = data

        # Extra attempt: direct PDF href (common in VNPT portals)
        if pdf_bytes is None:
            pdf_bytes = self._download_pdf_via_href()

        return xml_bytes, pdf_bytes

    def _download_column(self, col_name: str) -> bytes | None:
        """Locate the download link for *col_name* header; try GET then click-download."""
        link = self._find_link_by_column_header(col_name)
        if link:
            href: str = link.get("href", "")
            # If it's a real URL (not javascript:), attempt authenticated GET first
            if href and not href.lower().startswith("javascript"):
                try:
                    resp = self.page.context.request.get(href, timeout=30_000)
                    if resp.ok:
                        return resp.body()
                except Exception as exc:
                    logger.debug("VNPT: GET '%s' href failed: %s", col_name, exc)

        # Fall back: Playwright click-download (handles onclick / JS redirects)
        col_idx = {_COL_TAI_FILE: 11, _COL_TAI_BANG_KE: 12}.get(col_name)
        selectors: list[str] = []
        if col_idx:
            selectors += [
                f"#ReportViewInv table tbody tr:first-child td:nth-child({col_idx}) a",
                f"table tbody tr:first-child td:nth-child({col_idx}) a",
            ]
        selectors.append('a[onclick*="_hanleDownloadAttachment"]')
        return self._try_download(*selectors)

    def _download_pdf_via_href(self) -> bytes | None:
        """VNPT often exposes a /downloadPDF?checkCode=... link — fetch it directly."""
        href: str | None = self.page.evaluate(
            "() => { const a = document.querySelector('a[href*=\"downloadPDF\"], a[href*=\"DownloadPDF\"]'); "
            "return a ? a.href : null; }"
        )
        if not href:
            return None
        try:
            resp = self.page.context.request.get(href, timeout=30_000)
            if resp.ok:
                body = resp.body()
                if body[:4] == b"%PDF":
                    logger.info("VNPT: downloaded PDF via /downloadPDF href (%d bytes)", len(body))
                    return body
        except Exception as exc:
            logger.debug("VNPT: /downloadPDF GET failed: %s", exc)
        return None

    def _find_link_by_column_header(self, header_text: str) -> dict | None:
        """Return {href, onclick} for the first result row's cell whose column header matches."""
        return self.page.evaluate(
            """(headerText) => {
                const ths = document.querySelectorAll('table thead th, table thead td');
                let colIdx = -1;
                for (let i = 0; i < ths.length; i++) {
                    if (ths[i].textContent.trim().includes(headerText)) {
                        colIdx = i;
                        break;
                    }
                }
                if (colIdx === -1) return null;
                const row = document.querySelector('table tbody tr');
                if (!row) return null;
                const cell = row.querySelectorAll('td')[colIdx];
                if (!cell) return null;
                const a = cell.querySelector('a');
                return a ? {href: a.href, onclick: a.getAttribute('onclick')} : null;
            }""",
            header_text,
        )

    # ── captcha solving ─────────────────────────────────────────────────────

    def _screenshot_and_solve_captcha(self) -> str:
        img_loc = self.page.locator(_CAPTCHA_IMG).first
        if img_loc.count() == 0 or not img_loc.is_visible():
            return ""
        self._delay(0.5, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.screenshot(path=captcha_path)
            return _solve_vnpt_captcha(captcha_path)
        finally:
            os.unlink(captcha_path)


# ── module-level helpers ────────────────────────────────────────────────────

def _classify_bytes(data: bytes) -> str | None:
    stripped = data.strip()
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<HDon") or stripped.startswith(b"<"):
        return "xml"
    if data[:4] == b"%PDF":
        return "pdf"
    return None


def _solve_vnpt_captcha(image_path: str) -> str:
    """
    VNPT captchas show 4 distorted digits. Upscale + sharpen before sending to Gemini.
    Uses gemini-2.5-flash for best digit OCR accuracy.
    """
    img = PIL.Image.open(image_path).convert("L")       # greyscale
    w, h = img.size
    img = img.resize((w * 4, h * 4), PIL.Image.LANCZOS) # 4× upscale
    img = img.filter(PIL.ImageFilter.SHARPEN)
    img = PIL.ImageEnhance.Contrast(img).enhance(2.5)
    img = img.convert("RGB")

    response = _get_gemini_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "This is a VNPT Vietnam e-invoice portal captcha image showing exactly 4 distorted digits "
            "(digits 0–9 only, no letters). Carefully read each digit left-to-right. "
            "Return ONLY the 4-digit sequence with no spaces, punctuation, or explanation.",
            img,
        ],
    )
    raw = response.text.strip()
    logger.info("VNPT: Gemini raw captcha response = '%s'", raw)
    return re.sub(r"\s+", "", raw)
