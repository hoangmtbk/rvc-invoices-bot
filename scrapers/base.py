import os
import re
import time
import random
import tempfile
from abc import ABC, abstractmethod

import PIL.Image
from google import genai

from .result import ScrapedResult
from .exceptions import CaptchaRequiredException

_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    return _gemini_client

_CAPTCHA_IMG = (
    "img[src*='captcha' i], img[id*='captcha' i], img[class*='captcha' i]"
)
_CAPTCHA_INPUT = (
    "input[id*='captcha' i], input[placeholder*='xác thực' i]"
)


class BaseInvoiceScraper(ABC):
    def __init__(self, page, url: str, lookup_code: str) -> None:
        self.page = page
        self.url = url
        self.lookup_code = lookup_code

    @abstractmethod
    def scrape(self) -> ScrapedResult:
        pass

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

    def _handle_captcha_if_present(self) -> None:
        img_loc = self.page.locator(_CAPTCHA_IMG)
        inp_loc = self.page.locator(_CAPTCHA_INPUT)
        if img_loc.count() == 0 or not img_loc.first.is_visible():
            return
        if inp_loc.count() == 0:
            return

        self._delay(1.0, 1.5)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.first.screenshot(path=captcha_path)
            solution = self._solve_captcha(captcha_path)
        finally:
            os.unlink(captcha_path)

        if not solution:
            raise CaptchaRequiredException(
                "Gemini returned no characters from captcha image"
            )
        self._type(_CAPTCHA_INPUT, solution)

    @staticmethod
    def _solve_captcha(image_path: str) -> str:
        img = PIL.Image.open(image_path)
        response = _get_gemini_client().models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                "You are an expert OCR. Read the captcha text exactly as shown. "
                "Return ONLY the characters, no spaces or explanation.",
                img,
            ],
        )
        return re.sub(r"\s+", "", response.text.strip())
