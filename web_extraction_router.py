import base64
import logging
import os
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers import scrape_invoice
from scrapers.result import ScrapedResult

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
    combined = email_body_text + " " + email_body_html
    result = _try_direct_download(_extract_urls(combined))
    if result is not None:
        return result
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
                    return resp.content, "xml"
                if "pdf" in ct or resp.content[:4] == b"%PDF":
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
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
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


def _pick_best_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    from scrapers.factory import _get_registry
    registry_keys = list(_get_registry().keys())
    known = []
    for url in urls:
        try:
            netloc = urlparse(url).netloc.lower()
            for key in registry_keys:
                if netloc == key or netloc.endswith("." + key):
                    known.append(url)
                    break
        except Exception:
            continue
    candidates = known if known else urls
    return max(candidates, key=lambda u: len(urlparse(u).netloc.split(".")))


def process_branch_web(email, download_dir: str) -> ScrapedResult | None:
    email_body_html = email.html or ""
    email_body_text = email.text or ""
    combined = email_body_text + " " + email_body_html

    logger.debug(f"process_branch_web email body text:\n{email_body_text}")
    logger.debug(f"process_branch_web email body html:\n{email_body_html}")

    # Tier 1: direct link (requests, no Playwright)
    direct = extract_direct_link(email_body_html, email_body_text)
    if direct:
        file_bytes, content_type = direct
        uid = getattr(email, "uid", "unknown")
        fname = os.path.join(download_dir, f"direct_{uid}.{content_type}")
        with open(fname, "wb") as f:
            f.write(file_bytes)
        if content_type == "xml":
            return ScrapedResult(xml_bytes=file_bytes, xml_path=fname)
        return ScrapedResult(pdf_bytes=file_bytes, pdf_path=fname)

    # Tier 2: Playwright scraper
    code = _extract_lookup_code(combined)
    lookup_url = _pick_best_url(_extract_urls(combined))
    if not code or not lookup_url:
        logger.warning("process_branch_web: no lookup code or URL found in email body")
        return None

    for attempt in range(2):
        try:
            result = scrape_invoice(lookup_url, code, download_dir)
            logger.info(f"Playwright scrape success: url={lookup_url} code={code}")
            return result
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Playwright attempt 1 failed ({lookup_url}): {e}, retrying in 3s")
                time.sleep(3)
            else:
                logger.error(f"Playwright attempt 2 failed ({lookup_url}): {e}")
                return None
    return None


class _EmailBodyProxy:
    __slots__ = ("text", "html")

    def __init__(self, text: str, html: str) -> None:
        self.text = text
        self.html = html


def download_invoice_file(body_text: str, body_html: str) -> tuple[bytes, str]:
    """Compatibility shim — wraps process_branch_web for callers using the old signature."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = process_branch_web(_EmailBodyProxy(body_text, body_html), tmp)
    if result is None:
        raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
    if result.xml_bytes is not None:
        return result.xml_bytes, "xml"
    if result.pdf_bytes is not None:
        return result.pdf_bytes, "pdf"
    raise ValueError("ScrapedResult has no bytes")
