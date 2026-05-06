#!/usr/bin/env python3
"""Test click methods for MISA dropdown."""
import sys, time, os, html
sys.path.insert(0, "/app")
from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers import stealth_sync

nav_url = html.unescape(
    "https://www.meinvoice.vn/tra-cuu/?sc=GJF0HED59BA6&amp;m=ketoan@rvc.net.vn"
    "&amp;n=&amp;c=&amp;b=&amp;d=0&amp;t=1&amp;r=1"
)

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    stealth_sync(page)
    page.goto(nav_url, wait_until="networkidle", timeout=30000)
    time.sleep(4)

    span = page.locator("span.download-invoice")
    span.wait_for(state="visible", timeout=10000)

    # Test 1: force=True click
    print("Test 1: PDF via force=True click...")
    try:
        pdf_item = page.locator("div.txt-download-pdf")
        with page.expect_download(timeout=15000) as dl:
            pdf_item.first.click(force=True)
        path = dl.value.path()
        size = os.path.getsize(path)
        print(f"  PDF force-click: {size} bytes")
    except Exception as e:
        print(f"  force=True failed: {e}")

    # Test 2: JS evaluate click
    print("Test 2: PDF via JS evaluate...")
    try:
        with page.expect_download(timeout=15000) as dl:
            page.evaluate("document.querySelector('div.txt-download-pdf').click()")
        path = dl.value.path()
        size = os.path.getsize(path)
        print(f"  PDF JS click: {size} bytes")
    except Exception as e:
        print(f"  JS click failed: {e}")

    # Test 3: dispatch_event
    print("Test 3: PDF via dispatch_event...")
    try:
        with page.expect_download(timeout=15000) as dl:
            page.locator("div.txt-download-pdf").first.dispatch_event("click")
        path = dl.value.path()
        size = os.path.getsize(path)
        print(f"  PDF dispatch_event: {size} bytes")
    except Exception as e:
        print(f"  dispatch_event failed: {e}")

    # Test 4: XML via JS evaluate
    print("Test 4: XML via JS evaluate...")
    try:
        with page.expect_download(timeout=15000) as dl:
            page.evaluate("document.querySelector('div.txt-download-xml').click()")
        path = dl.value.path()
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            header = f.read(80)
        print(f"  XML JS click: {size} bytes, header={header!r}")
    except Exception as e:
        print(f"  XML JS click failed: {e}")

    browser.close()
