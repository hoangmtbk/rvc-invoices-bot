#!/usr/bin/env python3
"""Check if captcha refreshes when we click the captcha INPUT field."""
import sys, os, time, re, tempfile, hashlib

sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")
from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

SHOT = "/tmp/plx_cap"
os.makedirs(SHOT, exist_ok=True)

def hash_screenshot(page, sel):
    loc = page.locator(sel).first
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        p = tf.name
    loc.screenshot(path=p)
    with open(p, "rb") as f:
        h = hashlib.md5(f.read()).hexdigest()
    os.unlink(p)
    return h

def save_captcha(page, sel, name):
    loc = page.locator(sel).first
    p = f"{SHOT}/{name}.png"
    loc.screenshot(path=p)
    print(f"  Saved captcha: {p}")
    return p

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())
    page.goto("https://hoadon.petrolimex.com.vn", wait_until="networkidle")

    CAPTCHA_IMG = '#SearchformByfkey img[src*="captch" i]'
    CAPTCHA_IN  = '#SearchformByfkey #captch'
    CODE_SEL    = '#SearchformByfkey input#strFkey'  # direct id

    # 1. Hash captcha image BEFORE doing anything
    time.sleep(1)
    h1 = hash_screenshot(page, CAPTCHA_IMG)
    p1 = save_captcha(page, CAPTCHA_IMG, "cap_before_code")
    print(f"Captcha hash BEFORE code fill: {h1}")

    # 2. Fill code
    code_el = page.locator(CODE_SEL).first
    code_el.click(click_count=3)
    code_el.press_sequentially("VF4S5TMTE*", delay=80)
    time.sleep(0.3)

    # 3. Hash after code fill
    h2 = hash_screenshot(page, CAPTCHA_IMG)
    p2 = save_captcha(page, CAPTCHA_IMG, "cap_after_code")
    print(f"Captcha hash AFTER code fill:  {h2}  (changed={h1!=h2})")

    # 4. Solve the captcha (from CURRENT image)
    with open(p2, "rb") as f:
        import base64
        b64 = base64.b64encode(f.read()).decode()
    import requests
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    resp = requests.post("https://api.capsolver.com/createTask", json={
        "clientKey": api_key,
        "task": {"type": "ImageToTextTask", "body": b64}
    }, timeout=15).json()
    sol = resp.get("solution", {}).get("text", "") or ""
    sol = re.sub(r"\s+", "", sol)
    print(f"Capsolver solution: {sol!r}")

    # 5. Click captcha INPUT — does the captcha image change?
    captcha_el = page.locator(CAPTCHA_IN).first
    captcha_el.click(click_count=3)
    time.sleep(0.3)
    h3 = hash_screenshot(page, CAPTCHA_IMG)
    p3 = save_captcha(page, CAPTCHA_IMG, "cap_after_input_click")
    print(f"Captcha hash AFTER clicking captcha input: {h3}  (changed={h2!=h3})")

    # 6. Type solution
    captcha_el.press_sequentially(sol, delay=100)
    time.sleep(0.3)
    h4 = hash_screenshot(page, CAPTCHA_IMG)
    save_captcha(page, CAPTCHA_IMG, "cap_after_type")
    print(f"Captcha hash AFTER typing solution:        {h4}  (changed={h3!=h4})")

    captcha_val = captcha_el.input_value()
    code_val = code_el.input_value()
    print(f"\nFinal — code={code_val!r} captcha_field={captcha_val!r}")

    # 7. Submit and check
    SUBMIT_SEL = '#SearchformByfkey input[type="submit"], #SearchformByfkey button[type="submit"]'
    btn = page.locator(SUBMIT_SEL).first
    btn.click()
    time.sleep(6)
    body = page.evaluate("() => document.body.innerText").lower()
    n = page.locator('a:has-text("Tải")').count()
    print(f"After submit: Tải links={n}")
    print(f"Body (300 chars): {body[:300]}")

    browser.close()
print(f"\nDone. Screenshots in {SHOT}/")
