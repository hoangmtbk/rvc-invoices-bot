#!/usr/bin/env python3
"""Diagnostic: inspect meinvoice.vn invoice portal — hover & download flow.

Usage (inside container):
    python /app/scripts/debug_misa.py <lookup_code_or_sc_url>

Example:
    python /app/scripts/debug_misa.py GJF0HED59BA6
    python /app/scripts/debug_misa.py "https://www.meinvoice.vn/tra-cuu/?sc=GJF0HED59BA6&m=..."
"""

import sys
import os
import time

sys.path.insert(0, "/app")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers import stealth_sync

BASE_URL = "https://www.meinvoice.vn/tra-cuu"


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "GJF0HED59BA6"

    # Determine navigate URL and lookup code
    if arg.startswith("http"):
        # HTML-unescape &amp; in URL
        import html
        nav_url = html.unescape(arg)
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(nav_url).query)
        lookup_code = qs.get("sc", [arg])[0]
    else:
        lookup_code = arg
        nav_url = f"{BASE_URL}/?sc={lookup_code}"

    print(f"[DEBUG] lookup_code = {lookup_code!r}")
    print(f"[DEBUG] nav_url     = {nav_url!r}")

    with sync_playwright() as pw:
        browser, context = build_stealth_context(pw)
        try:
            page = context.new_page()
            stealth_sync(page)

            print(f"\n[1] Navigating to: {nav_url}")
            page.goto(nav_url, wait_until="networkidle", timeout=30_000)
            time.sleep(3)

            print(f"[2] Page title: {page.title()!r}")
            print(f"[2] URL after nav: {page.url!r}")

            # Dump all visible buttons/links
            print("\n[3] Visible buttons/links:")
            for el in page.locator("button, a").all():
                try:
                    if el.is_visible():
                        txt = el.inner_text().strip()[:80]
                        if txt:
                            print(f"    [{el.tag_name()}] {txt!r}")
                except Exception:
                    pass

            # Try hovering "Tải hóa đơn"
            hover_sel = 'button:has-text("Tải hóa đơn"), a:has-text("Tải hóa đơn"), span:has-text("Tải hóa đơn")'
            hover_loc = page.locator(hover_sel).first
            if hover_loc.count() > 0:
                print(f"\n[4] Found 'Tải hóa đơn' — hovering...")
                hover_loc.hover()
                time.sleep(1.5)
                print("[4] After hover — visible buttons/links:")
                for el in page.locator("button, a, li, span").all():
                    try:
                        if el.is_visible():
                            txt = el.inner_text().strip()[:80]
                            if txt and any(k in txt for k in ("PDF", "XML", "Tải", "hóa đơn")):
                                print(f"    [{el.tag_name()}] {txt!r}  tag_attrs={el.evaluate('e => e.outerHTML')[:120]}")
                    except Exception:
                        pass
            else:
                print("\n[4] 'Tải hóa đơn' button NOT found. Checking all text...")
                body_text = page.evaluate("() => document.body.innerText")
                # Print relevant lines
                for line in body_text.splitlines():
                    line = line.strip()
                    if line and any(k in line.lower() for k in ("tải", "pdf", "xml", "download")):
                        print(f"    {line!r}")

            # Screenshot
            shot_path = "/tmp/debug_misa.png"
            page.screenshot(path=shot_path, full_page=True)
            print(f"\n[5] Screenshot saved: {shot_path}")

            # Try to find download triggers
            print("\n[6] Scanning for download selectors:")
            download_sels = [
                'a:has-text("XML")',
                'button:has-text("Tải XML")',
                'a:has-text("Tải XML")',
                'a:has-text("PDF")',
                'button:has-text("Tải PDF")',
                'a[href*=".xml"]',
                'a[href*=".pdf"]',
                'button:has-text("Tải hóa đơn dạng PDF")',
                'button:has-text("Tải hóa đơn dạng XML")',
                'a:has-text("Tải hóa đơn dạng PDF")',
                'a:has-text("Tải hóa đơn dạng XML")',
                'li:has-text("Tải hóa đơn dạng PDF")',
                'li:has-text("Tải hóa đơn dạng XML")',
            ]
            for sel in download_sels:
                loc = page.locator(sel)
                count = loc.count()
                if count > 0:
                    visible = loc.first.is_visible()
                    try:
                        html_snip = loc.first.evaluate("e => e.outerHTML")[:150]
                    except Exception:
                        html_snip = "(error)"
                    print(f"    FOUND [{count}x visible={visible}] {sel!r}")
                    print(f"          HTML: {html_snip}")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
