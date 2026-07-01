import logging
import os
import random
import re
import tempfile
import zipfile
import io

from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# Selectors from playwright codegen — https://vttphcm-tt78.vnpt-invoice.com.vn/
_CODE_SEL = '[placeholder="Nhập mã tra cứu hóa đơn"], input#strFkey, input[name="strFkey"]'
_CAPTCHA_IMG = "#text img"
_CAPTCHA_INPUT = "#text #captch"
_SUBMIT_BTN = 'button:has-text("Tìm kiếm"), button[type="submit"]'
# Results land in #ReportViewInv; fall back to any visible table row
_RESULT_ROW = "#ReportViewInv table tbody tr, table tbody tr"

# jQuery Unobtrusive Validation injects this span when /Captcha/ValidateCaptcha returns false.
# data-val-remote="ErrorMessage" is the message; the span gets class field-validation-error.
_CAPTCHA_VAL_ERROR_SEL = (
    'span[data-valmsg-for="captch"].field-validation-error, '
    'span[data-valmsg-for="captch"]:not(.field-validation-valid)'
)

_MAX_CAPTCHA_RETRIES = 3

# The portal POSTs the form and returns a full results page; the server can be
# slow — observed up to ~60s before the results page renders. Wait generously so
# we don't give up mid-navigation (which also triggers "Execution context was
# destroyed" if we then touch the page).
_RESULT_TIMEOUT_MS = 90_000
# The bypass probe submits a dummy captcha that will never succeed, so it should
# fail fast instead of blocking for the full result timeout.
_PROBE_TIMEOUT_MS = 12_000

# Column header for PDF download in the result table
_COL_TAI_FILE = "Tải File"

# "Xem" button in the result row — opens a popup with the invoice viewer
_XEM_BTN_SEL = (
    'td a:has(i.icon-eye-open), '
    'td a[title*="Xem" i], '
    'td a:has-text("Xem")'
)
# "Download invoice zip" button inside the modal opened by ajxCall4Portal
_DOWNLOAD_ZIP_SEL = (
    'a:has-text("Tải hóa đơn Zip"), '
    'button:has-text("Tải hóa đơn Zip"), '
    'a:has-text("Download invoice zip"), '
    'button:has-text("Download invoice zip")'
)


class VnptScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self._load_fresh_form()
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
            # Each submit (and the bypass probe above) navigates the page to the
            # results URL, whose captcha/form is stale. Reload a clean form before
            # every attempt — a fresh page load is the only reliable reset.
            self._load_fresh_form()

            self._fill_lookup_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution or not re.fullmatch(r"[0-9]{4}", solution):
                logger.warning(
                    "VNPT: solver returned invalid solution '%s', retrying", solution
                )
                continue
            logger.info("VNPT attempt %d/%d: captcha='%s'", attempt + 1, _MAX_CAPTCHA_RETRIES, solution)
            self._enter_captcha(solution)

            if self._submit_and_wait_for_results():
                break

            logger.warning(
                "VNPT: results table absent after attempt %d, retrying", attempt + 1
            )
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

    def _load_fresh_form(self) -> None:
        """Navigate to the portal and wait for the lookup-code input.
        A fresh load resets any stale captcha/form state left by a prior submit."""
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.page.locator(_CODE_SEL).first.wait_for(state="visible", timeout=30_000)

    def _fill_lookup_code(self) -> None:
        el = self.page.locator(_CODE_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.3)
        el.press_sequentially(self.lookup_code, delay=80)
        self._delay(0.2, 0.5)

    def _probe_bypass(self) -> bool:
        """Submit with dummy captcha '0000' to detect absent server-side validation."""
        try:
            self._fill_lookup_code()
            self._enter_captcha("0000")
            result = self._submit_and_wait_for_results(_PROBE_TIMEOUT_MS)
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
        el.click(click_count=3)                                # select all
        self._delay(0.1, 0.2)
        el.press_sequentially(solution, delay=random.randint(80, 150))
        self._delay(0.2, 0.5)

    def _submit_and_wait_for_results(self, timeout_ms: int = _RESULT_TIMEOUT_MS) -> bool:
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
            # The results page can take ~60s to render, so wait up to timeout_ms.
            self.page.wait_for_selector(
                f"{_RESULT_ROW}, {_CAPTCHA_VAL_ERROR_SEL}, .text-danger:not(:empty)",
                state="visible",
                timeout=timeout_ms,
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
        """Fetch XML via Xem→popup→zip, PDF via Tải File column or /downloadPDF href."""
        xml_bytes: bytes | None = None
        pdf_bytes: bytes | None = None

        # ── XML: click "Xem", get popup, download zip, extract XML ──────────
        try:
            xml_bytes = self._download_xml_via_xem()
        except Exception as exc:
            logger.warning("VNPT: XML via Xem failed: %s", exc)

        # ── PDF: try Tải File column, then /downloadPDF href ──────────────────
        try:
            data = self._download_column(_COL_TAI_FILE)
            if data and _classify_bytes(data) == "pdf":
                logger.info("VNPT: '%s' → PDF (%d bytes)", _COL_TAI_FILE, len(data))
                pdf_bytes = data
        except Exception as exc:
            logger.debug("VNPT: '%s' download failed: %s", _COL_TAI_FILE, exc)

        if pdf_bytes is None:
            pdf_bytes = self._download_pdf_via_href()

        return xml_bytes, pdf_bytes

    def _download_xml_via_xem(self) -> bytes | None:
        """Click the 'Xem' eye button → wait for the in-page modal → click
        'Tải hóa đơn Zip' → unzip → return the first XML file's bytes.

        NOTE: ajxCall4Portal() opens a modal on the SAME page (no new tab),
        so we wait for the zip button to appear on page, not via expect_page.
        """
        xem = self.page.locator(_XEM_BTN_SEL).first
        if xem.count() == 0 or not xem.is_visible():
            logger.debug("VNPT: 'Xem' button not found in result row")
            return None

        xem.hover()
        self._delay(0.2, 0.5)
        xem.click()

        # Wait for the modal/overlay with the zip download button
        dl_btn = self.page.locator(_DOWNLOAD_ZIP_SEL).first
        try:
            dl_btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            logger.warning(
                "VNPT: 'Tải hóa đơn Zip' button not found after Xem click. "
                "Body snippet: %s",
                self.page.evaluate("() => document.body.innerText")[:400],
            )
            return None

        with self.page.expect_download(timeout=30_000) as dl_info:
            dl_btn.hover()
            self._delay(0.2, 0.5)
            dl_btn.click()

        download = dl_info.value
        zip_path = download.path()
        logger.info("VNPT: downloaded zip: %s", zip_path)

        return _extract_xml_from_zip(zip_path)

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
        col_idx = {_COL_TAI_FILE: 11}.get(col_name)
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
        img_loc = self.page.locator(_CAPTCHA_IMG)
        if img_loc.count() == 0 or not img_loc.first.is_visible():
            return ""
        self._delay(0.5, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.first.screenshot(path=captcha_path)
            result = capsolver_solve_image(captcha_path) or ""
            result = re.sub(r"\s+", "", result)
            logger.info("VNPT: Capsolver captcha result = '%s'", result)
            return result
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


def _extract_xml_from_zip(zip_path: str) -> bytes | None:
    """Open a ZIP file and return the bytes of the first .xml entry found."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                logger.warning("VNPT: ZIP contains no .xml files: %s", zf.namelist())
                return None
            data = zf.read(xml_names[0])
            logger.info("VNPT: extracted XML '%s' from zip (%d bytes)", xml_names[0], len(data))
            return data
    except zipfile.BadZipFile as exc:
        logger.warning("VNPT: downloaded file is not a valid ZIP: %s", exc)
        return None



