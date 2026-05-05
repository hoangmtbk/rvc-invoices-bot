#!/usr/bin/env python3
"""Diagnostic v2: CMC Telecom cinvoice portal — solve reCAPTCHA + submit + download."""
import sys, os, time, re, base64
import requests
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "CTEL.50A742E6A1F81205E0630E01040AB7A2"
BASE_URL = "https://cinvoice.cmctelecom.vn/"
SITE_KEY  = "6LfXVNQrAAAAAHnUNhAoJlx7W7p8HP7pxX8NSTqt"

def capsolver_solve_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    """Use Capsolver ReCaptchaV2TaskProxyLess to get a g-recaptcha-response token."""
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        print("  [capsolver] No CAPSOLVER_API_KEY set")
        return None
    print(f"  [capsolver] Submitting ReCaptchaV2TaskProxyLess for sitekey={site_key!r}")
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
        print(f"  [capsolver] createTask request failed: {e}")
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
        print(f"  [capsolver] poll {i+1}: status={status!r}")
        if status == "ready":
            token = result.get("solution", {}).get("gRecaptchaResponse", "")
            print(f"  [capsolver] token length={len(token)}")
            return token
        if status not in ("processing", "idle", None):
            print(f"  [capsolver] unexpected status: {result}")
            return None
    print("  [capsolver] timed out")
    return None
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
        print(f"  {label} ({selector}): ERROR {e}")
        return
    print(f"\n  {label} ({selector}): {n} elements")
    for i in range(min(n, 20)):
        el = locs.nth(i)
        try:
            tag     = el.evaluate("e => e.tagName").lower()
            id_     = el.get_attribute("id") or ""
            name_   = el.get_attribute("name") or ""
            href    = el.get_attribute("href") or ""
            onclick = el.get_attribute("onclick") or ""
            txt = ""
            try: txt = el.inner_text()[:80]
            except: pass
            visible = el.is_visible()
            print(f"    [{i}] {tag} id={id_!r} name={name_!r} href={href!r} onclick={onclick!r} text={txt!r} visible={visible}")
        except Exception as e:
            print(f"    [{i}] ERROR: {e}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    print(f"\n=== Step 1: Navigate to {BASE_URL} ===")
    page.goto(BASE_URL, wait_until="networkidle")
    shot(page, "01_homepage")

    print(f"\n=== Step 2: Enter lookup code ===")
    code_input = page.locator("#invoiceCode").first
    code_input.wait_for(state="visible", timeout=10_000)
    code_input.click(click_count=3)
    code_input.fill(LOOKUP_CODE)
    time.sleep(0.5)
    print(f"  Entered: {LOOKUP_CODE!r}")

    print(f"\n=== Step 3: Solve reCAPTCHA via Capsolver ===")
    token = capsolver_solve_recaptcha_v2(SITE_KEY, BASE_URL)
    if not token:
        print("  FATAL: could not get reCAPTCHA token; aborting")
        shot(page, "error_no_token")
        browser.close()
        sys.exit(1)

    print(f"\n=== Step 4: Inject reCAPTCHA token ===")
    # Inject into hidden textarea + trigger callback used by the React app
    page.evaluate(f"""(token) => {{
        // Set the hidden textarea
        const ta = document.getElementById('g-recaptcha-response');
        if (ta) {{ ta.value = token; }}
        // Also set all hidden g-recaptcha-response fields
        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {{ el.value = token; }});
        // Try to call the registered reCAPTCHA callback if available
        try {{
            if (window.grecaptcha && window.grecaptcha.getResponse) {{
                // Override getResponse to return our token
                const orig = window.grecaptcha.getResponse.bind(window.grecaptcha);
                window.grecaptcha.getResponse = () => token;
            }}
        }} catch(e) {{}}
    }}""", token)
    print(f"  Injected token (first 40): {token[:40]}...")
    shot(page, "03_token_injected")

    print(f"\n=== Step 5: Click submit ===")
    submit = page.locator("button:has-text('Tra cứu hóa đơn')").first
    submit.hover()
    time.sleep(0.3)
    submit.click()
    print("  Clicked submit, waiting for result...")
    time.sleep(5)
    shot(page, "04_after_submit")

    print(f"\n=== Step 6: Inspect result / popup ===")
    print(f"  page URL: {page.url!r}")
    body = page.evaluate("() => document.body.innerText")
    print(f"  body (first 500): {body[:500]!r}")

    # Look for download links
    dump(page, "a:has-text('Tải XML'), a:has-text('Tải PDF'), a:has-text('XML'), a:has-text('PDF')", "Download links")
    dump(page, "a[href*='.xml' i], a[href*='.pdf' i], button:has-text('Tải')", "Download by href")

    # All dialogs / modals / overlays
    dump(page, "[role=dialog], [class*=modal], [class*=dialog], [class*=popup]", "Modals/dialogs")

    # All visible links
    dump(page, "a:visible", "All visible links")

    # Check frames
    print(f"\n  All frames:")
    for f in page.frames:
        if f.url and f.url != "about:blank":
            print(f"    name={f.name!r}  url={f.url!r}")

    shot(page, "05_result_inspect")
    print(f"\n[done] screenshots in {SHOT_DIR}/")
    browser.close()
