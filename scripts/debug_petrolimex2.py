#!/usr/bin/env python3
"""Targeted diagnostic: inspect form inputs and try JS form submit."""
import sys, os, time, re, tempfile

sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")
from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

SHOT = "/tmp/plx_debug2"
os.makedirs(SHOT, exist_ok=True)

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.goto("https://hoadon.petrolimex.com.vn", wait_until="networkidle")

    CODE_SEL = '#SearchformByfkey input[type="text"], label:has-text("mã tra cứu") + input, label:has-text("mã tra cứu") ~ input, input[name*="fkey" i], input[id*="fkey" i]'
    inputs = page.locator(CODE_SEL)
    print(f"CODE_SEL matches: {inputs.count()} elements")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        print(f"  [{i}] id={el.get_attribute('id')!r} name={el.get_attribute('name')!r} type={el.get_attribute('type')!r} placeholder={el.get_attribute('placeholder')!r}")

    all_inputs = page.locator('#SearchformByfkey input')
    print(f"\nAll inputs in #SearchformByfkey: {all_inputs.count()}")
    for i in range(all_inputs.count()):
        el = all_inputs.nth(i)
        print(f"  [{i}] id={el.get_attribute('id')!r} name={el.get_attribute('name')!r} type={el.get_attribute('type')!r} visible={el.is_visible()}")

    # fill code
    code_el = inputs.first
    code_el.click(click_count=3)
    code_el.press_sequentially("VF4S5TMTE*", delay=80)
    page.screenshot(path=f"{SHOT}/A_code_filled.png", full_page=True)
    print(f"\nCode field value after fill: {code_el.input_value()!r}")

    # captcha
    img = page.locator('#SearchformByfkey img[src*="captch" i]').first
    time.sleep(1)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        p = tf.name
    img.screenshot(path=p)
    sol = re.sub(r"\s+", "", capsolver_solve_image(p) or "")
    print(f"Capsolver solution: {sol!r}")
    os.unlink(p)

    captcha_input = page.locator('#SearchformByfkey #captch').first
    captcha_input.click(click_count=3)
    captcha_input.press_sequentially(sol, delay=100)
    page.screenshot(path=f"{SHOT}/B_captcha_filled.png", full_page=True)
    print(f"Captcha field value: {captcha_input.input_value()!r}")
    print(f"Code field value now (after captcha fill): {code_el.input_value()!r}")

    # --- Try 1: button click ---
    SUBMIT_SEL = '#SearchformByfkey button[type="submit"], #SearchformByfkey input[type="submit"], #SearchformByfkey button, button[type="submit"]'
    btn = page.locator(SUBMIT_SEL).first
    print(f"\nSubmit button: id={btn.get_attribute('id')!r} text={btn.inner_text()!r} visible={btn.is_visible()}")
    btn.click()
    time.sleep(5)
    page.screenshot(path=f"{SHOT}/C_after_click.png", full_page=True)
    body = page.evaluate("() => document.body.innerText").lower()
    tai_sel = 'a:has-text("Tải")'
    print(f"Body after button click (400 chars):\n{body[:400]}")
    print(f"Tải links: {page.locator(tai_sel).count()}")

    # if no results, try JS submit
    if page.locator(tai_sel).count() == 0:
        print("\n--- No results from button click, trying JS form.submit() ---")
        page.reload(wait_until="networkidle")
        # re-fill
        code_el2 = page.locator(CODE_SEL).first
        code_el2.click(click_count=3)
        code_el2.press_sequentially("VF4S5TMTE*", delay=80)
        img2 = page.locator('#SearchformByfkey img[src*="captch" i]').first
        time.sleep(1)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            p2 = tf.name
        img2.screenshot(path=p2)
        sol2 = re.sub(r"\s+", "", capsolver_solve_image(p2) or "")
        print(f"New captcha solution: {sol2!r}")
        os.unlink(p2)
        captcha_input2 = page.locator('#SearchformByfkey #captch').first
        captcha_input2.click(click_count=3)
        captcha_input2.press_sequentially(sol2, delay=100)
        print(f"Code value before JS submit: {code_el2.input_value()!r}")
        print(f"Captcha value before JS submit: {captcha_input2.input_value()!r}")
        page.evaluate("() => document.querySelector('#SearchformByfkey').submit()")
        time.sleep(6)
        page.screenshot(path=f"{SHOT}/D_after_jssubmit.png", full_page=True)
        body2 = page.evaluate("() => document.body.innerText").lower()
        print(f"Body after JS submit (400 chars):\n{body2[:400]}")
        print(f"Tải links: {page.locator(tai_sel).count()}")

    browser.close()
print(f"\nDone. Screenshots in {SHOT}/")
