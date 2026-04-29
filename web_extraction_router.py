import base64
import logging
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

DIRECT_LINK_RE = re.compile(
    r"(token=|/download|/file|\.xml|\.pdf|/invoice|hoadon|tra-cuu)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)
REGEX_PATTERNS = [
    re.compile(r"mã số[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"mã tra cứu[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"mã nhận hóa đơn[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
    re.compile(r"Mã bí mật[\s:]*([A-Z0-9_]+)", re.IGNORECASE),
]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{60,}={0,2}$")
_VN_DOWNLOAD_TEXT_RE = re.compile(
    r"(Tải XML|Download XML|Xuất XML|Tải PDF|Download PDF)",
    re.IGNORECASE,
)
_HREF_DOWNLOAD_RE = re.compile(
    r"(getXml|exportXml|downloadXml|download)",
    re.IGNORECASE,
)


def extract_xml_from_html_attachment(html_content: str) -> bytes | None:
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Strategy 1: <input type="hidden"> whose id or name contains "xml"
        for tag in soup.find_all("input", {"type": "hidden"}):
            tag_id = (tag.get("id") or "").lower()
            tag_name = (tag.get("name") or "").lower()
            if "xml" in tag_id or "xml" in tag_name:
                value = tag.get("value", "")
                try:
                    decoded = base64.b64decode(value)
                    if decoded.strip().startswith((b"<?xml", b"<")):
                        return decoded
                except Exception:
                    pass

        # Strategy 2: regex sweep — any attribute value that looks like Base64
        for tag in soup.find_all(True):
            for attr_val in tag.attrs.values():
                if not isinstance(attr_val, str):
                    continue
                if _BASE64_RE.match(attr_val.strip()):
                    try:
                        decoded = base64.b64decode(attr_val.strip())
                        if decoded.strip().startswith((b"<?xml", b"<")):
                            return decoded
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"extract_xml_from_html_attachment error: {e}")

    return None


def extract_direct_link(
    email_body_html: str,
    email_body_text: str = "",
) -> tuple[bytes, str] | None:
    # Sub-strategy 1: token/direct links — scan URLs from both bodies
    combined = email_body_text + " " + email_body_html
    result = _try_direct_download(_extract_urls(combined))
    if result is not None:
        return result

    # Sub-strategy 2: Vietnamese-labeled <a> tags — HTML only
    if not email_body_html:
        return None
    try:
        soup = BeautifulSoup(email_body_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not (_VN_DOWNLOAD_TEXT_RE.search(text) or _HREF_DOWNLOAD_RE.search(href)):
                continue
            try:
                resp = requests.get(href, headers={"User-Agent": USER_AGENT}, timeout=30)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "xml" in ct or resp.content.strip().startswith(b"<?xml"):
                    logger.info(f"Vietnamese link XML download: {href}")
                    return resp.content, "xml"
                if "pdf" in ct or resp.content[:4] == b"%PDF":
                    logger.info(f"Vietnamese link PDF download: {href}")
                    return resp.content, "pdf"
            except Exception as e:
                logger.debug(f"Vietnamese link download failed {href}: {e}")
    except Exception as e:
        logger.debug(f"extract_direct_link BeautifulSoup error: {e}")

    return None


def _extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def _extract_lookup_code(text: str) -> str | None:
    for pattern in REGEX_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _try_direct_download(urls: list[str]) -> tuple[bytes, str] | None:
    for url in urls:
        if not DIRECT_LINK_RE.search(url):
            continue
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "xml" in ct or resp.content.strip().startswith(b"<?xml"):
                logger.info(f"Direct XML download: {url}")
                return resp.content, "xml"
            if "pdf" in ct or resp.content[:4] == b"%PDF":
                logger.info(f"Direct PDF download: {url}")
                return resp.content, "pdf"
        except Exception as e:
            logger.debug(f"Direct download failed {url}: {e}")
    return None


def _playwright_download(page, xml_selectors: list[str]) -> bytes:
    with page.expect_download(timeout=30000) as dl:
        for sel in xml_selectors:
            try:
                page.click(sel, timeout=5000)
                break
            except Exception:
                continue
    download = dl.value
    path = download.path()
    with open(path, "rb") as f:
        return f.read()


def scrape_misa(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto("https://www.meinvoice.vn/tra-cuu", wait_until="networkidle", timeout=30000)
        page.fill(
            'input[placeholder*="mã"], input[id*="code"], input[name*="code"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button[type="submit"], button:has-text("Tra cứu"), button:has-text("Tìm kiếm")')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'button:has-text("Tải XML")', 'a[href*=".xml"]'],
        )
        browser.close()
        return data


def scrape_petrolimex(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.fill(
            'input[id*="lookup"], input[name*="lookup"], input[placeholder*="mã"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button[type="submit"], button:has-text("Tra cứu"), input[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*="xml"]', 'button:has-text("XML")'],
        )
        browser.close()
        return data


def scrape_viettel(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(
            "https://vietteltelecom.vn/hoadondientu",
            wait_until="networkidle",
            timeout=30000,
        )
        page.fill(
            'input[placeholder*="bí mật"], input[name*="secret"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button:has-text("Tra cứu"), button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("Tải XML")'],
        )
        browser.close()
        return data


def scrape_vnpt(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(
            "https://vnpt-invoice.com.vn/invoice",
            wait_until="networkidle",
            timeout=30000,
        )
        page.fill(
            'input[placeholder*="mã"], input[id*="invoice"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button:has-text("Tra cứu"), button:has-text("Tìm"), button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'a[href*=".xml"]', 'button:has-text("XML")'],
        )
        browser.close()
        return data


def scrape_generic(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        inputs = page.query_selector_all("input[type='text']")
        if inputs:
            inputs[0].fill(code)
        page.click('button[type="submit"], button:has-text("Tra cứu")')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a[href*="xml"]', 'a:has-text("XML")', 'button:has-text("XML")'],
        )
        browser.close()
        return data


SCRAPERS: dict = {
    "hoadon.petrolimex.com.vn": scrape_petrolimex,
    "vietteltelecom.vn": scrape_viettel,
    "vnpt-invoice.com.vn": scrape_vnpt,
    "www.meinvoice.vn": scrape_misa,
}


def download_invoice_file(body_text: str, body_html: str) -> tuple[bytes, str]:
    combined = (body_text or "") + " " + (body_html or "")
    all_urls = _extract_urls(combined)

    # Stage 1: Try direct token/download link
    result = _try_direct_download(all_urls)
    if result is not None:
        return result

    # Stage 2: Playwright lookup form
    code = _extract_lookup_code(combined)
    portal_url = None
    for url in all_urls:
        domain = urlparse(url).netloc
        if domain in SCRAPERS:
            portal_url = url
            break

    if not code:
        raise ValueError("No lookup code found in email body")

    if not portal_url:
        found_domains = {urlparse(u).netloc for u in all_urls if urlparse(u).netloc}
        unsupported = found_domains - set(SCRAPERS.keys())
        if unsupported:
            raise ValueError(f"Unsupported provider domain(s): {', '.join(unsupported)}")
        raise ValueError("No known portal URL found in email body")

    domain = urlparse(portal_url).netloc
    scraper_fn = SCRAPERS.get(domain, scrape_generic)

    for attempt in range(2):
        try:
            xml_bytes = scraper_fn(portal_url, code)
            logger.info(f"Playwright download success: domain={domain} code={code}")
            return xml_bytes, "xml"
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Playwright attempt 1 failed ({domain}): {e}, retrying in 3s")
                time.sleep(3)
            else:
                raise
