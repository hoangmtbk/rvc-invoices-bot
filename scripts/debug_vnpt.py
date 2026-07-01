#!/usr/bin/env python3
"""Diagnostic: inspect VNPT invoice portal after a real captcha submit.

Usage (inside container):
    python /app/scripts/debug_vnpt.py <lookup_code> [url]

Loads the portal, fills the lookup code, solves the captcha via Capsolver,
clicks submit ONCE, then dumps the resulting page state (URL, tables,
validation spans, body text) and screenshots — so we can see whether the
result-row selector is wrong or the captcha genuinely failed.
"""
import sys
import os
import time
import re

sys.path.insert(0, "/app")
from dotenv import load_dotenv

load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

CODE = sys.argv[1] if len(sys.argv) > 1 else "TESTCODE"
URL = sys.argv[2] if len(sys.argv) > 2 else "https://vttphcm-tt78.vnpt-invoice.com.vn"
SHOT_DIR = "/tmp/vnpt_debug"
os.makedirs(SHOT_DIR, exist_ok=True)

_CODE_SEL = '[placeholder="Nhập mã tra cứu hóa đơn"], input#strFkey, input[name="strFkey"]'
_CAPTCHA_IMG = "#text img"
_CAPTCHA_INPUT = "#text #captch"
_SUBMIT_BTN = 'button:has-text("Tìm kiếm"), button[type="submit"]'


def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=p, full_page=True)
        print(f"  [screenshot] {p}")
    except Exception as e:
        print(f"  [screenshot FAILED] {name}: {e}")


def dump_tables(page):
    info = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('table').forEach((t, i) => {
                const rows = t.querySelectorAll('tbody tr').length;
                out.push({
                    idx: i,
                    id: t.id || '',
                    cls: t.className || '',
                    tbodyRows: rows,
                    headers: Array.from(t.querySelectorAll('thead th, thead td'))
                                  .map(h => h.textContent.trim()).slice(0, 20),
                });
            });
            return out;
        }"""
    )
    print(f"\nTABLES: {len(info)}")
    for t in info:
        print(f"  [{t['idx']}] id={t['id']!r} cls={t['cls']!r} tbodyRows={t['tbodyRows']}")
        if t["headers"]:
            print(f"        headers={t['headers']}")


def dump_errors(page):
    errs = page.evaluate(
        """() => {
            const sel = 'span.field-validation-error, .text-danger, [data-valmsg-for], .validation-summary-errors';
            return Array.from(document.querySelectorAll(sel))
                .map(e => ({cls: e.className, forf: e.getAttribute('data-valmsg-for'), txt: e.innerText.trim()}))
                .filter(e => e.txt);
        }"""
    )
    print(f"\nVALIDATION / ERROR NODES: {len(errs)}")
    for e in errs:
        print(f"  cls={e['cls']!r} for={e['forf']!r} txt={e['txt']!r}")


with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    page.on("dialog", lambda d: d.dismiss())

    print(f"\n1) Navigating to {URL}")
    page.goto(URL, wait_until="domcontentloaded")
    page.locator(_CODE_SEL).first.wait_for(state="visible", timeout=30_000)
    print(f"   URL now: {page.url}")
    print(f"   Title:   {page.title()!r}")
    shot(page, "01_loaded")

    print("\n2) Filling lookup code")
    code_el = page.locator(_CODE_SEL).first
    code_el.click(click_count=3)
    code_el.press_sequentially(CODE, delay=60)
    print(f"   code field = {code_el.input_value()!r}")

    print("\n3) Solving captcha")
    img = page.locator(_CAPTCHA_IMG).first
    print(f"   captcha img present={img.count() > 0} visible={img.is_visible() if img.count() else False}")
    cap_path = f"{SHOT_DIR}/captcha.png"
    img.screenshot(path=cap_path)
    solution = re.sub(r"\s+", "", capsolver_solve_image(cap_path) or "")
    print(f"   solution = {solution!r}")
    cap_in = page.locator(_CAPTCHA_INPUT).first
    cap_in.click(click_count=3)
    cap_in.press_sequentially(solution, delay=100)
    shot(page, "02_filled")

    print("\n4) Clicking submit (no_wait_after) and watching for navigation")
    nav_seen = {"count": 0, "urls": []}
    page.on("framenavigated", lambda f: (nav_seen.__setitem__("count", nav_seen["count"] + 1),
                                          nav_seen["urls"].append(f.url)) if f == page.main_frame else None)
    btn = page.locator(_SUBMIT_BTN).first
    btn.hover()
    time.sleep(0.4)
    btn.click(no_wait_after=True)

    # Give the page time to settle (AJAX validate + POST or full navigation)
    for i in range(12):
        time.sleep(1)
        try:
            rows = page.locator("#ReportViewInv table tbody tr, table tbody tr").count()
        except Exception as e:
            rows = f"<err: {e}>"
        print(f"   t+{i+1}s url={page.url} rows={rows} navs={nav_seen['count']}")

    shot(page, "03_after_submit")
    print(f"\n   main-frame navigations: {nav_seen['count']}")
    for u in nav_seen["urls"]:
        print(f"     -> {u}")

    dump_tables(page)
    dump_errors(page)

    body = page.evaluate("() => document.body.innerText")
    print(f"\nBODY TEXT ({len(body)} chars, first 800):\n{body[:800]}")

    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}/")
