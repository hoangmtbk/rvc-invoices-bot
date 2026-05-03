#!/usr/bin/env python3
"""Diagnostic: run with full stealth (same as production) and log link count immediately after click."""
import sys, os, time, re, tempfile

sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

SHOT = "/tmp/plx_debug3"
os.makedirs(SHOT, exist_ok=True)
TAI_SEL = 'a:has-text("Tải")'

def count_tai(page):
    return page.locator(TAI_SEL).count()

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()

    # Apply stealth exactly like production
    Stealth().apply_stealth_sync(page)

    # dialog handler
    page.on("dialog", lambda d: d.dismiss())

    page.goto("https://hoadon.petrolimex.com.vn", wait_until="networkidle")

    # scroll (like production)
    import random
    down = random.randint(300, 700)
    page.mouse.wheel(0, down)
    time.sleep(random.uniform(0.5, 1.2))
    page.mouse.wheel(0, -random.randint(100, down // 2))
    time.sleep(random.uniform(0.5, 1.0))

    page.screenshot(path=f"{SHOT}/00_after_scroll.png", full_page=True)
    print(f"After scroll — Tải links: {count_tai(page)}")

    # _enter_code
    CODE_SEL = '#SearchformByfkey input[type="text"], label:has-text("mã tra cứu") + input, label:has-text("mã tra cứu") ~ input, input[name*="fkey" i], input[id*="fkey" i]'
    code_el = page.locator(CODE_SEL).first
    code_el.wait_for(state="visible", timeout=10_000)
    code_el.click(click_count=3)
    time.sleep(0.15)
    code_el.press_sequentially("VF4S5TMTE*", delay=100)
    time.sleep(0.3)
    print(f"Code value: {code_el.input_value()!r}")

    # _screenshot_and_solve_captcha
    CAPTCHA_IMG_SEL = '#SearchformByfkey img[src*="captch" i], #SearchformByfkey img[src*="Captcha" i], img[src*="captch" i]'
    img_loc = page.locator(CAPTCHA_IMG_SEL).first
    time.sleep(0.7)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        p = tf.name
    img_loc.screenshot(path=p)
    sol = re.sub(r"\s+", "", capsolver_solve_image(p) or "")
    print(f"Capsolver solution: {sol!r}")
    os.unlink(p)

    if not re.fullmatch(r"[0-9]{4}", sol):
        print("Bad solution — exiting")
        browser.close()
        sys.exit(1)

    # _enter_captcha
    captcha_el = page.locator('#SearchformByfkey #captch').first
    captcha_el.wait_for(state="visible", timeout=10_000)
    captcha_el.click(click_count=3)
    time.sleep(0.15)
    captcha_el.press_sequentially(sol, delay=100)
    time.sleep(0.3)
    page.screenshot(path=f"{SHOT}/01_before_submit.png", full_page=True)
    print(f"Code value before submit: {code_el.input_value()!r}")
    print(f"Captcha value before submit: {captcha_el.input_value()!r}")

    # _click_submit — log link count at multiple timepoints
    SUBMIT_SEL = '#SearchformByfkey button[type="submit"], #SearchformByfkey input[type="submit"], #SearchformByfkey button, button:has-text("Tìm"), input[type="submit"], button[type="submit"]'
    btn = page.locator(SUBMIT_SEL).first
    print(f"Submit btn visible: {btn.is_visible()}")
    btn.hover()
    time.sleep(0.5)
    btn.click()
    print("  Clicked submit.")

    for wait_s in [1, 2, 3, 5, 8, 12, 15, 20]:
        time.sleep(1)
        n = count_tai(page)
        print(f"  t+{wait_s}s → Tải links: {n}")
        if n > 0:
            page.screenshot(path=f"{SHOT}/02_result.png", full_page=True)
            body = page.evaluate("() => document.body.innerText").lower()
            print(f"  Body (500 chars): {body[:500]}")
            break
    else:
        page.screenshot(path=f"{SHOT}/02_no_result.png", full_page=True)
        body = page.evaluate("() => document.body.innerText").lower()
        print(f"No results after 20s. Body (400 chars): {body[:400]}")

    browser.close()
print(f"\nDone. Screenshots in {SHOT}/")
