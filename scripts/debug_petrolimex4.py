#!/usr/bin/env python3
"""Debug scraper state: screenshot before submit and log field values."""
import sys, os, time, re, tempfile

sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image
from scrapers.petrolimex import (
    _CODE_SEL, _CAPTCHA_IMG_SEL, _CAPTCHA_INPUT_SEL, _SUBMIT_SEL, _DOWNLOAD_LINK_SEL
)

SHOT = "/tmp/plx_dbg4"
os.makedirs(SHOT, exist_ok=True)

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    page.goto("https://hoadon.petrolimex.com.vn", wait_until="networkidle")

    # Scroll (same as scraper)
    import random
    down = random.randint(300, 700)
    page.mouse.wheel(0, down)
    time.sleep(random.uniform(0.5, 1.2))
    page.mouse.wheel(0, -random.randint(100, down // 2))
    time.sleep(random.uniform(0.5, 1.0))

    # _enter_code (same as scraper)
    el = page.locator(_CODE_SEL).first
    el.wait_for(state="visible", timeout=10_000)
    el.click(click_count=3)
    time.sleep(random.uniform(0.1, 0.2))
    el.press_sequentially("VF4S5TMTE*", delay=100)
    time.sleep(random.uniform(0.2, 0.5))
    print(f"After _enter_code: code_field={el.input_value()!r}")

    # _screenshot_and_solve_captcha (same as scraper)
    img_loc = page.locator(_CAPTCHA_IMG_SEL)
    print(f"Captcha img count={img_loc.count()} visible={img_loc.first.is_visible()}")
    time.sleep(random.uniform(0.5, 1.0))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        captcha_path = tf.name
    img_loc.first.screenshot(path=captcha_path)
    import shutil; shutil.copy(captcha_path, f"{SHOT}/captcha.png")
    print(f"Captcha screenshot saved to {SHOT}/captcha.png")
    solution = re.sub(r"\s+", "", capsolver_solve_image(captcha_path) or "")
    os.unlink(captcha_path)
    print(f"Capsolver solution: {solution!r}")

    if not re.fullmatch(r"[0-9]{4}", solution):
        print("Bad solution, exiting")
        browser.close()
        sys.exit(1)

    # _enter_captcha (same as scraper)
    captcha_el = page.locator(_CAPTCHA_INPUT_SEL).first
    captcha_el.wait_for(state="visible", timeout=10_000)
    captcha_el.click(click_count=3)
    time.sleep(random.uniform(0.1, 0.2))
    captcha_el.press_sequentially(solution, delay=random.randint(80, 150))
    time.sleep(random.uniform(0.2, 0.5))

    # Check field values BEFORE submit
    code_val = el.input_value()
    cap_val = captcha_el.input_value()
    print(f"\nBEFORE submit: code={code_val!r} captcha={cap_val!r}")
    page.screenshot(path=f"{SHOT}/before_submit.png", full_page=True)

    # Find submit button
    btn = page.locator(_SUBMIT_SEL).first
    btn.wait_for(state="visible", timeout=15_000)
    print(f"Submit btn: tag={page.evaluate('e => e.tagName', btn.element_handle())!r} type={btn.get_attribute('type')!r} id={btn.get_attribute('id')!r} name={btn.get_attribute('name')!r}")

    # Hover then click (same as scraper)
    btn.hover()
    time.sleep(random.uniform(0.3, 0.8))

    # Before click — code value still there?
    print(f"Code JUST BEFORE click: {el.input_value()!r}  captcha: {captcha_el.input_value()!r}")

    btn.click()
    print("Clicked submit. Polling for Tải links...")

    for i in range(25):
        time.sleep(1)
        n = page.locator('a:has-text("Tải")').count()
        print(f"  t+{i+1}s: Tải links={n}")
        if n > 0:
            page.screenshot(path=f"{SHOT}/after_submit_success.png", full_page=True)
            print("SUCCESS!")
            break
    else:
        page.screenshot(path=f"{SHOT}/after_submit_fail.png", full_page=True)
        body = page.evaluate("() => document.body.innerText").lower()
        print(f"No results. Body: {body[:400]}")

    browser.close()
print(f"Done. Screenshots in {SHOT}/")
