import logging
import os
import time
import requests

from .base import BaseInvoiceScraper
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# cinvoice.cmctelecom.vn — React SPA with reCAPTCHA v2
_BASE_URL   = "https://cinvoice.cmctelecom.vn/"
_SITE_KEY   = "6LfXVNQrAAAAAHnUNhAoJlx7W7p8HP7pxX8NSTqt"
_CODE_SEL   = "#invoiceCode"
_SUBMIT_SEL = "button:has-text('Tra cứu hóa đơn')"
_XML_SEL    = "button:has-text('Tải XML')"
_PDF_SEL    = "button:has-text('Tải PDF')"
_MODAL_SEL  = "[id^=radix][role=dialog], [id^=radix]"
_NOT_FOUND  = "không tìm thấy"

_MAX_RETRIES = 3


def _capsolver_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    """Solve reCAPTCHA v2 via Capsolver ReCaptchaV2TaskProxyLess; return token or None."""
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        logger.warning("CMCInvoice: CAPSOLVER_API_KEY not set")
        return None
    try:
        create = requests.post(
            "https://api.capsolver.com/createTask",
            json={"clientKey": api_key, "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }},
            timeout=15,
        ).json()
    except Exception as exc:
        logger.warning("CMCInvoice: Capsolver createTask failed: %s", exc)
        return None
    if create.get("errorId", 0) != 0:
        logger.warning("CMCInvoice: Capsolver createTask error: %s", create)
        return None
    task_id = create.get("taskId")
    logger.info("CMCInvoice: Capsolver taskId=%s", task_id)
    for _ in range(60):
        time.sleep(2)
        try:
            result = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=10,
            ).json()
        except Exception as exc:
            logger.debug("CMCInvoice: Capsolver poll failed: %s", exc)
            continue
        status = result.get("status")
        if status == "ready":
            token = result.get("solution", {}).get("gRecaptchaResponse", "")
            logger.info("CMCInvoice: Capsolver token len=%d", len(token))
            return token
        if status not in ("processing", "idle", None):
            logger.warning("CMCInvoice: Capsolver unexpected status %r: %s", status, result)
            return None
    logger.warning("CMCInvoice: Capsolver timed out for taskId=%s", task_id)
    return None


class CMCInvoiceScraper(BaseInvoiceScraper):
    """Scraper for CMC Telecom cinvoice portal (cinvoice.cmctelecom.vn).

    Flow:
      1. Navigate to base URL.
      2. Fill #invoiceCode with lookup_code.
      3. Solve reCAPTCHA v2 via Capsolver; inject token via clients[0].T.T.callback.
      4. Click submit button.
      5. Wait for Radix dialog with 'Tải XML' / 'Tải PDF' buttons.
      6. Trigger downloads via page.expect_download().
    """

    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()

        for attempt in range(_MAX_RETRIES):
            logger.info(
                "CMCInvoice: attempt %d/%d code=%r",
                attempt + 1, _MAX_RETRIES, self.lookup_code,
            )
            self.page.goto(_BASE_URL, wait_until="networkidle")
            self._delay(1.0, 2.0)

            self._enter_code()
            token = _capsolver_recaptcha_v2(_SITE_KEY, _BASE_URL)
            if not token:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("CMCInvoice: no reCAPTCHA token on attempt %d, retrying", attempt + 1)
                    continue
                raise CaptchaRequiredException(
                    f"CMCInvoice: Capsolver failed after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
                )

            self._inject_token(token)
            self._delay(0.3, 0.7)

            # Verify button became enabled
            btn = self.page.locator(_SUBMIT_SEL).first
            if btn.evaluate("e => e.disabled"):
                logger.warning("CMCInvoice: submit still disabled after token inject, attempt %d", attempt + 1)
                if attempt < _MAX_RETRIES - 1:
                    continue
                raise CaptchaRequiredException(
                    f"CMCInvoice: submit never enabled after reCAPTCHA for '{self.lookup_code}'"
                )

            btn.hover()
            self._delay(0.2, 0.5)
            btn.click()
            logger.info("CMCInvoice: submitted, waiting for modal ...")

            try:
                self.page.locator(_XML_SEL).first.wait_for(state="visible", timeout=15_000)
            except Exception:
                # Check if page indicates not found
                body = self.page.evaluate("() => document.body.innerText").lower()
                if _NOT_FOUND in body:
                    raise InvoiceNotFoundException(
                        f"CMCInvoice: invoice not found for '{self.lookup_code}'"
                    )
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("CMCInvoice: modal did not open on attempt %d, retrying", attempt + 1)
                    continue
                raise CaptchaRequiredException(
                    f"CMCInvoice: modal never opened after {_MAX_RETRIES} attempts for '{self.lookup_code}'"
                )

            # Modal is open — download XML then PDF
            xml_bytes = self._download_btn(_XML_SEL)
            pdf_bytes = self._download_btn(_PDF_SEL)

            logger.info(
                "CMCInvoice: xml=%s pdf=%s",
                f"{len(xml_bytes)}B" if xml_bytes else "none",
                f"{len(pdf_bytes)}B" if pdf_bytes else "none",
            )
            return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

        raise CaptchaRequiredException(
            f"CMCInvoice: all {_MAX_RETRIES} attempts failed for '{self.lookup_code}'"
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _enter_code(self) -> None:
        inp = self.page.locator(_CODE_SEL).first
        inp.wait_for(state="visible", timeout=10_000)
        inp.click(click_count=3)
        self._delay(0.1, 0.3)
        inp.fill(self.lookup_code)
        self._delay(0.2, 0.5)

    def _inject_token(self, token: str) -> None:
        """Inject the solved reCAPTCHA token and trigger the React onChange callback."""
        self.page.evaluate(
            """(token) => {
                const ta = document.getElementById('g-recaptcha-response');
                if (ta) { ta.value = token; }
                try {
                    const cfg = window.___grecaptcha_cfg;
                    if (cfg && cfg.clients && cfg.clients[0] &&
                            cfg.clients[0].T && cfg.clients[0].T.T) {
                        const cb = cfg.clients[0].T.T.callback;
                        if (typeof cb === 'function') { cb(token); }
                    }
                } catch (e) {}
            }""",
            token,
        )

    def _download_btn(self, selector: str) -> bytes | None:
        btn = self.page.locator(selector).first
        if btn.count() == 0 or not btn.is_visible():
            return None
        try:
            with self.page.expect_download(timeout=15_000) as dl:
                btn.hover()
                self._delay(0.1, 0.3)
                btn.click()
            path = dl.value.path()
            with open(path, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.warning("CMCInvoice: download failed for %r: %s", selector, exc)
            return None
