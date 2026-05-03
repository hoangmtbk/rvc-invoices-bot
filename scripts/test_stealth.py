#!/usr/bin/env python3
"""Test scrape_invoice() with stealth disabled vs enabled."""
import sys, os
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.petrolimex import PetrolimexScraper
from playwright_stealth import Stealth
import tempfile

URL = "https://hoadon.petrolimex.com.vn"
CODE = "VF4S5TMTE*"
APPLY_STEALTH = "--stealth" in sys.argv

print(f"Testing WITH stealth = {APPLY_STEALTH}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    if APPLY_STEALTH:
        print("Applying stealth_sync...")
        Stealth().apply_stealth_sync(page)

    scraper = PetrolimexScraper(page, URL, CODE)
    try:
        result = scraper.scrape()
        print(f"SUCCESS: xml={len(result.xml_bytes or b'')}B pdf={len(result.pdf_bytes or b'')}B")
    except Exception as e:
        print(f"FAILED: {e}")
    finally:
        browser.close()
