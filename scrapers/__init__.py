import os

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .browser import build_stealth_context
from .factory import ScraperFactory
from .result import ScrapedResult


def stealth_sync(page) -> None:
    """Apply stealth evasions to a sync Playwright page (v2 API wrapper)."""
    Stealth().apply_stealth_sync(page)


def scrape_invoice(
    url: str,
    lookup_code: str,
    download_dir: str | None = None,
) -> ScrapedResult:
    with sync_playwright() as p:
        browser, context = build_stealth_context(p)
        try:
            page = context.new_page()
            stealth_sync(page)
            scraper = ScraperFactory.get(url, page, lookup_code)
            result = scraper.scrape()

            if result.xml_bytes is None and result.pdf_bytes is None:
                raise ValueError(f"Scraper returned no files for {url}")

            if download_dir:
                if result.xml_bytes is not None:
                    xml_path = os.path.join(download_dir, f"web_{lookup_code}.xml")
                    with open(xml_path, "wb") as f:
                        f.write(result.xml_bytes)
                    result.xml_path = xml_path
                if result.pdf_bytes is not None:
                    pdf_path = os.path.join(download_dir, f"web_{lookup_code}.pdf")
                    with open(pdf_path, "wb") as f:
                        f.write(result.pdf_bytes)
                    result.pdf_path = pdf_path

            return result
        finally:
            browser.close()
