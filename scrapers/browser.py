from playwright.sync_api import Browser, BrowserContext, Playwright

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def build_stealth_context(playwright: Playwright) -> tuple[Browser, BrowserContext]:
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="vi-VN",
    )
    return browser, context
