#!/usr/bin/env python3
"""Diagnostic v5: CMC invoice — inspect modal download buttons and trigger downloads."""
import sys, os, time
import requests
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "CTEL.50A742E6A1F81205E0630E01040AB7A2"
BASE_URL  = "https://cinvoice.cmctelecom.vn/"
SITE_KEY  = "6LfXVNQrAAAAAHnUNhAoJlx7W7p8HP7pxX8NSTqt"
SHOT_DIR  = "/tmp/cmcinvoice_debug"
os.makedirs(SHOT_DIR, exist_ok=True)


def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=p, full_page=True)
    print(f"  [screenshot] {p}")


def dump_deep(ctx, selector, label):
    try:
        locs = ctx.locator(selector)
        n = locs.count()
    except Exception as e:
        print(f"  {label}: ERROR {e}")
        return
    print(f"\n  {label} ({selector}): {n} elements")
    for i in range(min(n, 20)):
        el = locs.nth(i)
        try:
            tag     = el.evaluate("e => e.tagName").lower()
            id_     = el.get_attribute("id") or ""
            cls     = (el.get_attribute("class") or "")[:80]
            href    = el.get_attribute("href") or ""
            onclick = el.get_attribute("onclick") or ""
            download = el.get_attribute("download") or ""
            typ     = el.get_attribute("type") or ""
            txt = ""
            try: txt = el.inner_text()[:80]
            except: pass
            visible = el.is_visible()
            print(f"    [{i}] {tag} id={id_!r} type={typ!r} class={cls!r} href={href!r} download={download!r} onclick={onclick!r} text={txt!r} visible={visible}")
        except Exception as e:
            print(f"    [{i}] ERROR: {e}")


def capsolver_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        return None
    print(f"  [capsolver] submitting ...")
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
    except Exception as e:
        print(f"  [capsolver] createTask failed: {e}")
        return None
    if create.get("errorId", 0) != 0:
        return None
    task_id = create.get("taskId")
    for i in range(60):
        time.sleep(2)
        try:
            result = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=10,
            ).json()
        except Exception:
            continue
        status = result.get("status")
        print(f"  [capsolver] poll {i+1}: {status}")
        if status == "ready":
            token = result.get("solution", {}).get("gRecaptchaResponse", "")
            print(f"  [capsolver] token len={len(token)}")
            return token
        if status not in ("processing", "idle", None):
            return None
    return None


def inject_recaptcha_token(page, token: str) -> None:
    page.evaluate("""(token) => {
        const ta = document.getElementById('g-recaptcha-response');
        if (ta) { ta.value = token; }
        const cfg = window.___grecaptcha_cfg;
        if (cfg && cfg.clients && cfg.clients[0] && cfg.clients[0].T && cfg.clients[0].T.T) {
            const cb = cfg.clients[0].T.T.callback;
            if (typeof cb === 'function') { cb(token); }
        }
    }""", token)


with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    # Navigate + fill + solve + submit
    page.goto(BASE_URL, wait_until="networkidle")
    time.sleep(2)
    page.locator("#invoiceCode").first.fill(LOOKUP_CODE)
    time.sleep(0.5)

    token = capsolver_recaptcha_v2(SITE_KEY, BASE_URL)
    if not token:
        print("FATAL: no token"); browser.close(); sys.exit(1)

    inject_recaptcha_token(page, token)
    time.sleep(0.5)

    btn = page.locator("button:has-text('Tra cứu hóa đơn')").first
    btn.hover(); time.sleep(0.3); btn.click()
    print("Submitted. Waiting 6s...")
    time.sleep(6)
    shot(page, "01_modal_open")

    print("\n=== Inspect modal ===")
    modal = page.locator("[role=dialog], [class*=modal], [id^=radix]").first
    try:
        print(f"  modal inner HTML (first 800): {modal.inner_html()[:800]!r}")
    except Exception as e:
        print(f"  modal innerHTML error: {e}")

    # Dump all buttons and links inside the modal area
    dump_deep(page, "[id^=radix] button, [id^=radix] a, [role=dialog] button, [role=dialog] a", "Modal buttons/links")
    dump_deep(page, "button:has-text('Tải'), button:has-text('PDF'), button:has-text('XML')", "Tải buttons")
    dump_deep(page, "a:has-text('Tải'), a:has-text('PDF'), a:has-text('XML')", "Tải links")
    dump_deep(page, "[class*=download], [id*=download]", "download elements")

    # All buttons on page
    print("\n=== All buttons ===")
    all_btns = page.locator("button")
    n = all_btns.count()
    print(f"  Total buttons: {n}")
    for i in range(n):
        b = all_btns.nth(i)
        try:
            txt = b.inner_text()[:60]
            cls = (b.get_attribute("class") or "")[:60]
            visible = b.is_visible()
            print(f"  [{i}] text={txt!r} class={cls!r} visible={visible}")
        except:
            pass

    print("\n=== Try download XML ===")
    xml_btn = page.locator("button:has-text('Tải XML'), button:has-text('XML')").first
    if xml_btn.count() > 0 and xml_btn.is_visible():
        print(f"  Found XML btn, clicking...")
        try:
            with page.expect_download(timeout=15_000) as dl:
                xml_btn.click()
            d = dl.value
            path = d.path()
            data = open(path, "rb").read()
            print(f"  XML download: {len(data)} bytes, first 80: {data[:80]!r}")
        except Exception as e:
            print(f"  XML download error: {e}")
    else:
        print("  XML button not found or not visible")

    shot(page, "02_after_xml")

    print("\n=== Try download PDF ===")
    pdf_btn = page.locator("button:has-text('Tải PDF'), button:has-text('PDF')").first
    if pdf_btn.count() > 0 and pdf_btn.is_visible():
        print(f"  Found PDF btn, clicking...")
        try:
            with page.expect_download(timeout=15_000) as dl:
                pdf_btn.click()
            d = dl.value
            path = d.path()
            data = open(path, "rb").read()
            print(f"  PDF download: {len(data)} bytes, first 4: {data[:4]!r}")
        except Exception as e:
            print(f"  PDF download error: {e}")
    else:
        print("  PDF button not found or not visible")

    shot(page, "03_after_pdf")
    print(f"\n[done] screenshots in {SHOT_DIR}/")
    browser.close()
