#!/usr/bin/env python3
"""Diagnostic: open Petrolimex portal, fill code + captcha, submit, screenshot every step.

Usage (from repo root):
    python scripts/debug_petrolimex.py VF4S5TMTE*
"""
import os, sys, time, re, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from scrapers.base import capsolver_solve_image
from scrapers.browser import build_stealth_context

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "VF4S5TMTE*"
URL = "https://hoadon.petrolimex.com.vn"
SHOT_DIR = "/tmp/plx_debug"
os.makedirs(SHOT_DIR, exist_ok=True)

def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=p, full_page=True)
    print(f"  [screenshot] {p}")

def log_buttons(page):
    btns = page.locator("button, input[type=submit]")
    n = btns.count()
    print(f"  Buttons/inputs on page: {n}")
    for i in range(n):
        try:
            el = btns.nth(i)
            text = el.inner_text() if el.is_visible() else "(hidden)"
            typ  = el.get_attribute("type") or ""
            id_  = el.get_attribute("id") or ""
            cls  = el.get_attribute("class") or ""
            print(f"    [{i}] text={text!r} type={typ!r} id={id_!r} class={cls[:40]!r}")
        except Exception as e:
            print(f"    [{i}] error: {e}")

def log_links(page, pattern=""):
    links = page.locator(f"a{':has-text('+repr(pattern)+')' if pattern else ''}")
    n = links.count()
    print(f"  Links (pattern={pattern!r}): {n}")
    for i in range(n):
        try:
            el = links.nth(i)
            text = el.inner_text() if el.is_visible() else "(hidden)"
            href = el.get_attribute("href") or ""
            print(f"    [{i}] text={text!r} href={href[:80]!r}")
        except Exception as e:
            print(f"    [{i}] error: {e}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()

    print(f"\n1) Navigating to {URL} ...")
    page.goto(URL, wait_until="networkidle")
    shot(page, "01_loaded")

    # --- form elements ---
    print("\n2) Page title:", page.title())
    print("   URL:", page.url)

    log_buttons(page)
    log_links(page)

    # --- find & fill lookup code ---
    CODE_SEL = (
        '#SearchformByfkey input[type="text"], '
        'label:has-text("mã tra cứu") + input, '
        'label:has-text("mã tra cứu") ~ input, '
        'input[name*="fkey" i], input[id*="fkey" i]'
    )
    code_loc = page.locator(CODE_SEL).first
    print(f"\n3) Code input visible: {code_loc.is_visible()}")
    code_loc.wait_for(state="visible", timeout=10_000)
    code_loc.click(click_count=3)
    code_loc.press_sequentially(LOOKUP_CODE, delay=80)
    shot(page, "02_code_filled")

    # --- solve captcha ---
    CAPTCHA_IMG_SEL = (
        '#SearchformByfkey img[src*="captch" i], '
        'img[src*="captch" i]'
    )
    img_loc = page.locator(CAPTCHA_IMG_SEL).first
    print(f"\n4) Captcha img visible: {img_loc.is_visible()}")
    time.sleep(1)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        captcha_path = tf.name
    img_loc.screenshot(path=captcha_path)
    print(f"   Captcha saved: {captcha_path}")
    solution = capsolver_solve_image(captcha_path) or ""
    solution = re.sub(r"\s+", "", solution)
    print(f"   Capsolver solution: {solution!r}")
    os.unlink(captcha_path)

    if not re.fullmatch(r"[0-9]{4}", solution):
        print("   BAD solution — aborting, check screenshot manually")
        context.close(); browser.close()
        sys.exit(1)

    captcha_input = page.locator('#SearchformByfkey #captch').first
    captcha_input.wait_for(state="visible", timeout=10_000)
    captcha_input.click(click_count=3)
    captcha_input.press_sequentially(solution, delay=100)
    shot(page, "03_captcha_filled")

    # --- submit ---
    SUBMIT_SEL = (
        '#SearchformByfkey button[type="submit"], '
        '#SearchformByfkey input[type="submit"], '
        '#SearchformByfkey button, '
        'button:has-text("Tìm"), '
        'input[type="submit"], '
        'button[type="submit"]'
    )
    btn = page.locator(SUBMIT_SEL).first
    print(f"\n5) Submit button visible: {btn.is_visible()}")
    print(f"   Submit button text: {btn.inner_text()!r}")
    btn.hover()
    time.sleep(0.5)
    btn.click()
    print("   Clicked submit, waiting 5s ...")
    time.sleep(5)
    shot(page, "04_after_submit")

    # --- inspect result ---
    print(f"\n6) Page URL after submit: {page.url}")
    print(f"   Page title: {page.title()}")
    body_text = page.evaluate("() => document.body.innerText")
    print(f"\n   Body text (first 1000 chars):\n{body_text[:1000]}")

    log_buttons(page)
    log_links(page)
    log_links(page, "Tải")
    log_links(page, "Download")

    # --- all anchors ---
    print("\n   All anchors:")
    all_a = page.locator("a")
    for i in range(min(all_a.count(), 20)):
        try:
            el = all_a.nth(i)
            print(f"    [{i}] text={el.inner_text()!r} href={el.get_attribute('href', timeout=1000)!r}")
        except:
            pass

    context.close()
    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}/")
