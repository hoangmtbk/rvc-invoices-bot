#!/usr/bin/env python3
"""Diagnostic: inspect EasyInvoice invoice portal.

Usage (inside container):
    # With ViewFromEmail URL (direct view — no lookup form needed):
    python /app/scripts/debug_easyinvoice.py <lookup_code> [url]

    # Default URL is the ViewFromEmail token URL from UID 324
"""
import sys, os, time, re, tempfile
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "UEEF7KD2V"
URL = sys.argv[2] if len(sys.argv) > 2 else (
    "http://0312668018hd.easyinvoice.vn/Invoice/ViewFromEmail"
    "?token=MUMyNlRUVl9fNTU2fFVFRUY3S0QyVnwzMDQ5Nw=="
)
SHOT_DIR = "/tmp/easyinvoice_debug"
os.makedirs(SHOT_DIR, exist_ok=True)


def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=p, full_page=True)
    print(f"  [screenshot] {p}")


def dump_elements(page, selector, label):
    locs = page.locator(selector)
    n = locs.count()
    print(f"\n{label} ({selector}): {n} elements")
    for i in range(n):
        el = locs.nth(i)
        tag  = el.evaluate("e => e.tagName").lower()
        typ  = el.get_attribute("type") or ""
        id_  = el.get_attribute("id") or ""
        name_ = el.get_attribute("name") or ""
        cls  = el.get_attribute("class") or ""
        href = el.get_attribute("href") or ""
        onclick = el.get_attribute("onclick") or ""
        txt  = ""
        try: txt = el.inner_text()[:80]
        except: pass
        visible = el.is_visible()
        print(f"  [{i}] tag={tag!r} type={typ!r} id={id_!r} name={name_!r} class={cls!r} "
              f"href={href!r} onclick={onclick!r} text={txt!r} visible={visible}")


with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    # ── Step 1: Load page ────────────────────────────────────────────────
    print(f"\n1) Navigating to {URL}")
    page.goto(URL, wait_until="networkidle")
    shot(page, "01_loaded")
    print(f"   Title: {page.title()!r}")
    print(f"   Current URL: {page.url!r}")

    # ── Step 2: Enumerate interactive elements ───────────────────────────
    dump_elements(page, "input", "All inputs")
    dump_elements(page, "button", "All buttons")
    dump_elements(page, "img", "All images (first 10)")
    dump_elements(page, "a", "All links")
    dump_elements(page, "form", "All forms")

    # ── Step 3: Check if this is a direct-view URL (no search form) ──────
    is_direct_view = "ViewFromEmail" in page.url or (
        "token=" in page.url and "tra-cuu" not in page.url.lower()
    )
    print(f"\n3) is_direct_view = {is_direct_view}")

    # ── Step 4: Look for XML/PDF download buttons ────────────────────────
    print("\n4) Checking for download buttons...")
    xml_sels = [
        "button:has-text('Tải tệp XML')",
        "a:has-text('Tải tệp XML')",
        "text='Tải tệp XML'",
        "button:has-text('Tải XML')",
        "a:has-text('Tải XML')",
        "button:has-text('Tải về')",
        "a:has-text('Tải về')",
        "a[href*='.xml']",
        "a[href*='xml' i]",
    ]
    pdf_sels = [
        "button:has-text('Tải PDF')",
        "a:has-text('Tải PDF')",
        "a[href*='.pdf']",
        "a[href*='pdf' i]",
    ]
    for sel in xml_sels:
        loc = page.locator(sel)
        n = loc.count()
        if n > 0:
            print(f"  XML sel {sel!r}: {n} elements")
            for i in range(n):
                el = loc.nth(i)
                try:
                    print(f"    [{i}] text={el.inner_text()!r} visible={el.is_visible()} "
                          f"onclick={el.get_attribute('onclick')!r} "
                          f"href={el.get_attribute('href')!r}")
                except Exception as e:
                    print(f"    [{i}] error: {e}")
    for sel in pdf_sels:
        loc = page.locator(sel)
        n = loc.count()
        if n > 0:
            print(f"  PDF sel {sel!r}: {n} elements")
            for i in range(n):
                el = loc.nth(i)
                try:
                    print(f"    [{i}] text={el.inner_text()!r} visible={el.is_visible()} "
                          f"onclick={el.get_attribute('onclick')!r} "
                          f"href={el.get_attribute('href')!r}")
                except Exception as e:
                    print(f"    [{i}] error: {e}")

    # ── Step 5: Try to trigger XML download ──────────────────────────────
    print("\n5) Attempting XML download via 'Tải tệp XML'...")
    xml_loc = page.locator("button:has-text('Tải tệp XML'), a:has-text('Tải tệp XML')")
    if xml_loc.count() > 0 and xml_loc.first.is_visible():
        onclick = xml_loc.first.get_attribute("onclick") or ""
        href = xml_loc.first.get_attribute("href") or ""
        print(f"  XML button: onclick={onclick!r} href={href!r}")

        # Check if it opens a new page/tab or downloads directly
        try:
            with page.expect_download(timeout=10_000) as dl_info:
                xml_loc.first.hover()
                time.sleep(0.3)
                xml_loc.first.click()
            dl = dl_info.value
            dl_path = dl.path()
            with open(dl_path, "rb") as f:
                data = f.read()
            print(f"  Download: filename={dl.suggested_filename!r} size={len(data)}B type={data[:4]!r}")
            shot(page, "05_after_xml_download")
        except Exception as e:
            print(f"  expect_download timed out: {e}")
            shot(page, "05_after_xml_click")
            # Maybe it opened a popup / modal
            print(f"  Checking for popup content on current page...")
            dump_elements(page, "button:has-text('Tải'), a:has-text('Tải')", "Tải buttons after click")
    else:
        print("  No 'Tải tệp XML' button visible — trying 'Tải về' master dropdown")
        master = page.locator("button:has-text('Tải về'), a:has-text('Tải về')")
        if master.count() > 0 and master.first.is_visible():
            master.first.hover()
            time.sleep(0.5)
            master.first.click()
            shot(page, "05_master_dropdown_clicked")
            time.sleep(1)
            dump_elements(page, "button:has-text('Tải'), a:has-text('Tải')", "Download items after dropdown")
        else:
            print("  No download buttons found at all")
            shot(page, "05_no_download")

    # ── Step 6: Try PDF download ─────────────────────────────────────────
    print("\n6) Attempting PDF download via 'Tải PDF'...")
    pdf_loc = page.locator("button:has-text('Tải PDF'), a:has-text('Tải PDF')")
    if pdf_loc.count() > 0 and pdf_loc.first.is_visible():
        onclick = pdf_loc.first.get_attribute("onclick") or ""
        href = pdf_loc.first.get_attribute("href") or ""
        print(f"  PDF button: onclick={onclick!r} href={href!r}")
        try:
            with page.expect_download(timeout=10_000) as dl_info:
                pdf_loc.first.hover()
                time.sleep(0.3)
                pdf_loc.first.click()
            dl = dl_info.value
            dl_path = dl.path()
            with open(dl_path, "rb") as f:
                data = f.read()
            print(f"  PDF Download: filename={dl.suggested_filename!r} size={len(data)}B type={data[:4]!r}")
            shot(page, "06_after_pdf_download")
        except Exception as e:
            print(f"  expect_download timed out for PDF: {e}")
            shot(page, "06_after_pdf_click")
    else:
        print("  No 'Tải PDF' button visible")

    # ── Step 7: Body text summary ────────────────────────────────────────
    body = page.evaluate("() => document.body.innerText")
    print(f"\n7) Body text (first 500 chars):\n{body[:500]}")

    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}/")
