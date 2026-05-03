import base64
import logging
import os
import re
import time
import random
import tempfile
from abc import ABC, abstractmethod

import requests as _requests

from .result import ScrapedResult

_logger = logging.getLogger(__name__)


def capsolver_solve_image(image_path: str) -> str | None:
    """Submit a captcha screenshot to Capsolver ImageToTextTask; return the text or None.

    Only active when the CAPSOLVER_API_KEY environment variable is set.
    """
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        return None

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    try:
        create_resp = _requests.post(
            "https://api.capsolver.com/createTask",
            json={"clientKey": api_key, "task": {"type": "ImageToTextTask", "body": b64}},
            timeout=15,
        ).json()
    except Exception as exc:
        _logger.warning("Capsolver: createTask request failed: %s", exc)
        return None

    if create_resp.get("errorId", 0) != 0:
        _logger.warning("Capsolver: createTask error: %s", create_resp)
        return None

    # ImageToTextTask is synchronous — solution may already be in createTask response
    if create_resp.get("status") == "ready":
        text = create_resp.get("solution", {}).get("text", "")
        _logger.info("Capsolver: solved inline, text=%r", text)
        return text

    task_id = create_resp.get("taskId")
    if not task_id:
        _logger.warning("Capsolver: createTask returned no taskId: %s", create_resp)
        return None

    for _ in range(10):
        time.sleep(1)
        try:
            result_resp = _requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=10,
            ).json()
        except Exception as exc:
            _logger.warning("Capsolver: getTaskResult request failed: %s", exc)
            return None
        status = result_resp.get("status")
        if status == "ready":
            text = result_resp.get("solution", {}).get("text", "")
            _logger.info("Capsolver: polled result, text=%r", text)
            return text
        if status not in ("processing", "idle", None):
            _logger.warning("Capsolver: unexpected status %r: %s", status, result_resp)
            return None

    _logger.warning("Capsolver: timed out waiting for task %s", task_id)
    return None


class BaseInvoiceScraper(ABC):
    def __init__(self, page, url: str, lookup_code: str) -> None:
        self.page = page
        self.url = url
        self.lookup_code = lookup_code

    @abstractmethod
    def scrape(self) -> ScrapedResult:
        pass

    @staticmethod
    def _classify_bytes(data: bytes) -> str | None:
        """Return 'xml', 'pdf', or None based on file magic bytes."""
        stripped = data.strip()
        if stripped.startswith(b"<?xml"):
            return "xml"
        if data[:4] == b"%PDF":
            return "pdf"
        return None

    def _setup_dialogs(self) -> None:
        self.page.on("dialog", lambda d: d.dismiss())

    def _delay(self, min_sec: float = 0.5, max_sec: float = 1.5) -> None:
        time.sleep(random.uniform(min_sec, max_sec))

    def _scroll(self) -> None:
        down = random.randint(300, 700)
        self.page.mouse.wheel(0, down)
        self._delay(0.5, 1.2)
        self.page.mouse.wheel(0, -random.randint(100, down // 2))
        self._delay(0.5, 1.0)

    def _click(self, selector: str, timeout: int = 10000) -> None:
        el = self.page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.hover()
        self._delay(0.3, 0.8)
        el.click()

    def _type(self, selector: str, text: str, timeout: int = 10000) -> None:
        el = self.page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.hover()
        self._delay(0.2, 0.5)
        el.click()
        el.press_sequentially(text, delay=random.randint(100, 250))
        self._delay(0.3, 0.7)

    def _try_download(self, *selectors: str, timeout: int = 15000) -> bytes | None:
        for sel in selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                with self.page.expect_download(timeout=timeout) as dl:
                    loc.first.hover()
                    self._delay(0.2, 0.5)
                    loc.first.click()
                path = dl.value.path()
                with open(path, "rb") as f:
                    return f.read()
        return None
