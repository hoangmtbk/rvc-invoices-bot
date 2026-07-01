#!/usr/bin/env python3
"""Diagnostic: find the reCAPTCHA success-callback path on cinvoice.cmctelecom.vn.

The scraper hardcodes clients[0].T.T.callback, but the minified path can change,
leaving the submit button disabled after token injection. This solves the
captcha, dumps every function under ___grecaptcha_cfg.clients, then tries each
1-arg `callback` candidate and reports which one enables the submit button.

Usage (inside container, mount scrapers to pick up local edits):
    python /app/scripts/debug_cmcinvoice_cb2.py <lookup_code>
"""
import sys
import os

sys.path.insert(0, "/app")
from dotenv import load_dotenv

load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from scrapers.browser import build_stealth_context
from scrapers.cmcinvoice import _capsolver_recaptcha_v2, _BASE_URL, _SITE_KEY, _CODE_SEL, _SUBMIT_SEL

CODE = sys.argv[1] if len(sys.argv) > 1 else "TESTCODE"
SHOT_DIR = "/tmp/cmc_debug"
os.makedirs(SHOT_DIR, exist_ok=True)

SCAN_JS = """() => {
    const cfg = window.___grecaptcha_cfg;
    if (!cfg || !cfg.clients) return {err: 'no clients'};
    const funcs = [];
    function scan(obj, path, depth) {
        if (depth > 6 || !obj || typeof obj !== 'object') return;
        for (const k of Object.keys(obj)) {
            let v;
            try { v = obj[k]; } catch (e) { continue; }
            if (typeof v === 'function') {
                funcs.push({path: path + '.' + k, len: v.length, key: k});
            } else if (v && typeof v === 'object') {
                scan(v, path + '.' + k, depth + 1);
            }
        }
    }
    Object.keys(cfg.clients).forEach(ci => scan(cfg.clients[ci], 'clients[' + ci + ']', 0));
    return {funcs};
}"""

# Try a candidate callback path: set textarea, call the function at `path`, return disabled state
TRY_JS = """([token, path]) => {
    const ta = document.getElementById('g-recaptcha-response');
    if (ta) { ta.value = token; }
    let called = false, err = null;
    try {
        // resolve path like clients[0].T.T.callback
        const m = path.match(/^clients\\[(\\d+)\\]\\.(.+)$/);
        let obj = window.___grecaptcha_cfg.clients[m[1]];
        const parts = m[2].split('.');
        for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
        const fn = obj[parts[parts.length - 1]];
        if (typeof fn === 'function') { fn(token); called = true; }
    } catch (e) { err = String(e); }
    const btn = document.querySelector("button");
    return {called, err};
}"""

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    page.on("dialog", lambda d: d.dismiss())

    print(f"1) goto {_BASE_URL}")
    page.goto(_BASE_URL, wait_until="networkidle")
    inp = page.locator(_CODE_SEL).first
    inp.wait_for(state="visible", timeout=15_000)
    inp.fill(CODE)
    print(f"   code filled = {inp.input_value()!r}")

    btn = page.locator(_SUBMIT_SEL).first
    print(f"   submit disabled (before) = {btn.evaluate('e => e.disabled')}")

    print("\n2) Solving reCAPTCHA via Capsolver ...")
    token = _capsolver_recaptcha_v2(_SITE_KEY, _BASE_URL)
    print(f"   token len = {len(token) if token else None}")
    if not token:
        print("   NO TOKEN — aborting")
        browser.close()
        sys.exit(1)

    print("\n3) Scanning ___grecaptcha_cfg for functions:")
    scan = page.evaluate(SCAN_JS)
    if scan.get("err"):
        print(f"   ERROR: {scan['err']}")
    funcs = scan.get("funcs", [])
    for f in funcs:
        print(f"   {f['path']}  len={f['len']}")

    # Candidate callbacks: 1-arg functions, prefer key literally 'callback'
    candidates = [f for f in funcs if f["len"] == 1]
    candidates.sort(key=lambda f: (f["key"] != "callback", len(f["path"])))
    print(f"\n4) Trying {len(candidates)} one-arg candidate(s):")
    winner = None
    for f in candidates:
        res = page.evaluate(TRY_JS, [token, f["path"]])
        disabled = btn.evaluate("e => e.disabled")
        print(f"   {f['path']:40s} called={res['called']} err={res['err']} -> submit disabled={disabled}")
        if res["called"] and not disabled:
            winner = f["path"]
            break

    print(f"\nRESULT: winning callback path = {winner!r}")
    page.screenshot(path=f"{SHOT_DIR}/after_inject.png", full_page=True)
    browser.close()

print(f"\nDone. Screenshot in {SHOT_DIR}/")
