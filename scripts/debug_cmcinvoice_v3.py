#!/usr/bin/env python3
"""Diagnostic v3: try clicking the reCAPTCHA checkbox directly."""
import sys, os, time
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "CTEL.50A742E6A1F81205E0630E01040AB7A2"
BASE_URL = "https://cinvoice.cmctelecom.vn/"
SHOT_DIR = "/tmp/cmcinvoice_debug"
os.makedirs(SHOT_DIR, exist_ok=True)

def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=p, full_page=True)
    print(f"  [screenshot] {p}")

def dump(ctx, selector, label):
    try:
        locs = ctx.locator(selector)
        n = locs.count()
    except Exception as e:
        print(f"  {label}: ERROR {e}")
        return
    print(f"\n  {label} ({selector}): {n} elements")
    for i in range(min(n, 10)):
        el = locs.nth(i)
        try:
            tag  = el.evaluate("e => e.tagName").lower()
            id_  = el.get_attribute("id") or ""
            href = el.get_attribute("href") or ""
            onclick = el.get_attribute("onclick") or ""
            txt  = ""
            try: txt = el.inner_text()[:80]
            except: pass
            visible = el.is_visible()
            print(f"    [{i}] {tag} id={id_!r} href={href!r} onclick={onclick!r} text={txt!r} visible={visible}")
        except Exception as e:
            print(f"    [{i}] ERROR: {e}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    print(f"\n=== Step 1: Navigate ===")
    page.goto(BASE_URL, wait_until="networkidle")
    time.sleep(2)
    shot(page, "01_loaded")

    print(f"\n=== Step 2: Enter code ===")
    page.locator("#invoiceCode").first.fill(LOOKUP_CODE)
    time.sleep(0.5)
    print(f"  code entered: {LOOKUP_CODE!r}")

    print(f"\n=== Step 3: Find reCAPTCHA anchor iframe ===")
    anchor_frame = None
    for f in page.frames:
        if "recaptcha/api2/anchor" in f.url:
            anchor_frame = f
            print(f"  Found anchor frame: {f.url[:80]!r}")
            break
    if not anchor_frame:
        print("  ERROR: anchor frame not found!")
        shot(page, "error")
        browser.close()
        sys.exit(1)

    print(f"\n=== Step 4: Inspect checkbox in anchor frame ===")
    dump(anchor_frame, "#recaptcha-anchor", "reCAPTCHA anchor div")
    dump(anchor_frame, ".recaptcha-checkbox", "checkbox")
    chk = anchor_frame.locator("#recaptcha-anchor")
    print(f"  checkbox aria-checked={chk.get_attribute('aria-checked')!r}")
    print(f"  checkbox visible={chk.is_visible()}")

    print(f"\n=== Step 5: Click checkbox ===")
    shot(page, "02_before_click")
    chk.click()
    print("  Clicked. Waiting 5s for result...")
    time.sleep(5)
    shot(page, "03_after_click")

    print(f"\n=== Step 6: Check result ===")
    chk_state = chk.get_attribute("aria-checked")
    print(f"  aria-checked after click: {chk_state!r}")

    # Check if there's a challenge popup (bframe)
    bframe = None
    for f in page.frames:
        if "recaptcha/api2/bframe" in f.url:
            bframe = f
            break
    if bframe:
        try:
            bframe_visible = bframe.locator(".rc-imageselect").is_visible()
            print(f"  bframe (challenge) visible: {bframe_visible}")
        except:
            print(f"  bframe exists but could not check visibility")
    else:
        print(f"  No bframe (challenge popup) — checkbox may have passed!")

    # Check if submit button is now enabled
    btn = page.locator("button:has-text('Tra cứu hóa đơn')").first
    disabled = btn.evaluate("e => e.disabled")
    print(f"  Submit button disabled: {disabled}")

    # Check g-recaptcha-response
    token_val = page.evaluate("() => { const t = document.getElementById('g-recaptcha-response'); return t ? t.value.substring(0,40) : 'not found'; }")
    print(f"  g-recaptcha-response (first 40): {token_val!r}")

    if not disabled:
        print(f"\n=== Step 7: Click submit ===")
        btn.click()
        print("  Submitted. Waiting 5s...")
        time.sleep(5)
        shot(page, "04_after_submit")
        body = page.evaluate("() => document.body.innerText")
        print(f"  body (first 500): {body[:500]!r}")
        dump(page, "a:has-text('Tải XML'), a:has-text('Tải PDF')", "Download links")
        dump(page, "a[href*='.xml' i], a[href*='.pdf' i]", "Download by href")
        dump(page, "[role=dialog], [class*=modal]", "Modals")
        dump(page, "a:visible", "All visible links")
    else:
        print(f"\n  Submit still disabled — checkbox click did not pass, need full reCAPTCHA solve.")

    shot(page, "05_final")
    print(f"\n[done] screenshots in {SHOT_DIR}/")
    browser.close()
