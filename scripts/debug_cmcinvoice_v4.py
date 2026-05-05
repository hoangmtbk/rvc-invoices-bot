#!/usr/bin/env python3
"""Diagnostic v4: CMC invoice — Capsolver token + inject via clients[0].T.T.callback."""
import sys, os, time, re
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
            tag     = el.evaluate("e => e.tagName").lower()
            id_     = el.get_attribute("id") or ""
            href    = el.get_attribute("href") or ""
            onclick = el.get_attribute("onclick") or ""
            txt = ""
            try: txt = el.inner_text()[:80]
            except: pass
            visible = el.is_visible()
            print(f"    [{i}] {tag} id={id_!r} href={href!r} onclick={onclick!r} text={txt!r} visible={visible}")
        except Exception as e:
            print(f"    [{i}] ERROR: {e}")


def capsolver_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        print("  [capsolver] No CAPSOLVER_API_KEY")
        return None
    print(f"  [capsolver] Submitting ReCaptchaV2TaskProxyLess ...")
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
        print(f"  [capsolver] createTask error: {create}")
        return None
    task_id = create.get("taskId")
    print(f"  [capsolver] taskId={task_id}")
    for i in range(60):
        time.sleep(2)
        try:
            result = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=10,
            ).json()
        except Exception as e:
            print(f"  [capsolver] poll {i} failed: {e}")
            continue
        status = result.get("status")
        if i < 5 or status == "ready":
            print(f"  [capsolver] poll {i+1}: status={status!r}")
        if status == "ready":
            token = result.get("solution", {}).get("gRecaptchaResponse", "")
            print(f"  [capsolver] token len={len(token)}")
            return token
        if status not in ("processing", "idle", None):
            print(f"  [capsolver] unexpected: {result}")
            return None
    print("  [capsolver] timed out")
    return None


with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    print(f"\n=== Step 1: Navigate ===")
    page.goto(BASE_URL, wait_until="networkidle")
    time.sleep(2)
    shot(page, "01_loaded")

    print(f"\n=== Step 2: Enter lookup code ===")
    page.locator("#invoiceCode").first.fill(LOOKUP_CODE)
    time.sleep(0.5)
    print(f"  code: {LOOKUP_CODE!r}")

    print(f"\n=== Step 3: Solve reCAPTCHA via Capsolver ===")
    token = capsolver_recaptcha_v2(SITE_KEY, BASE_URL)
    if not token:
        print("  FATAL: no token")
        browser.close()
        sys.exit(1)

    print(f"\n=== Step 4: Inject token via clients[0].T.T.callback ===")
    inject_result = page.evaluate("""(token) => {
        // 1. Set hidden textarea
        const ta = document.getElementById('g-recaptcha-response');
        if (ta) { ta.value = token; }
        // 2. Call the reCAPTCHA success callback (react-google-recaptcha onChange)
        try {
            const cfg = window.___grecaptcha_cfg;
            if (cfg && cfg.clients && cfg.clients[0] && cfg.clients[0].T && cfg.clients[0].T.T) {
                const cb = cfg.clients[0].T.T.callback;
                if (typeof cb === 'function') {
                    cb(token);
                    return 'callback called OK';
                }
                return 'callback not a function: ' + typeof cb;
            }
            return 'path not found';
        } catch(e) {
            return 'error: ' + e.toString();
        }
    }""", token)
    print(f"  inject result: {inject_result!r}")
    time.sleep(1)

    # Check if button is now enabled
    btn = page.locator("button:has-text('Tra cứu hóa đơn')").first
    disabled = btn.evaluate("e => e.disabled")
    print(f"  Submit disabled: {disabled}")
    shot(page, "03_after_inject")

    if disabled:
        print("  Button still disabled! Trying alternative: set aria-checked + dispatch change event on anchor frame")
        # Try marking anchor frame checkbox as checked
        anchor_frame = None
        for f in page.frames:
            if "recaptcha/api2/anchor" in f.url:
                anchor_frame = f
                break
        if anchor_frame:
            anchor_frame.evaluate("""(token) => {
                const chk = document.getElementById('recaptcha-anchor');
                if (chk) {
                    chk.setAttribute('aria-checked', 'true');
                    chk.classList.add('recaptcha-checkbox-checked');
                }
            }""", token)
        disabled2 = btn.evaluate("e => e.disabled")
        print(f"  Submit disabled after aria-checked: {disabled2}")

    if not btn.evaluate("e => e.disabled"):
        print(f"\n=== Step 5: Click submit ===")
        btn.hover()
        time.sleep(0.3)
        btn.click()
        print("  Clicked submit. Waiting 6s...")
        time.sleep(6)
        shot(page, "04_after_submit")
        body = page.evaluate("() => document.body.innerText")
        print(f"  body (500): {body[:500]!r}")

        dump(page, "a:has-text('Tải XML'), a:has-text('Tải PDF')", "Download links by text")
        dump(page, "a[href*='.xml' i], a[href*='.pdf' i], a[download]", "Download by href/download")
        dump(page, "[role=dialog], [class*=modal], [class*=dialog]", "Modals")
        dump(page, "a:visible", "All visible links")

        # Also check for new page/popup
        print(f"\n  All frames after submit:")
        for f in page.frames:
            if f.url and f.url != "about:blank" and "recaptcha" not in f.url:
                print(f"    {f.name!r}  {f.url!r}")
    else:
        print("  Submit still disabled after all attempts.")

    shot(page, "05_final")
    print(f"\n[done] screenshots in {SHOT_DIR}/")
    browser.close()
