# web_extraction_router.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `web_scraper.py` with `web_extraction_router.py` — a 3-tier fallback module (HTML-attachment Base64 extraction → Vietnamese direct-link download → Playwright domain router) for Branch 4 of the Vietnamese E-invoice pipeline.

**Architecture:** Extend `web_scraper.py` in-place: copy it to `web_extraction_router.py`, add three new public functions (`extract_xml_from_html_attachment`, `extract_direct_link`, `dynamic_web_router`), wrap them with `process_branch_4`, keep all existing Playwright scrapers in the same file, and add `scrape_easyinvoice`. Update `router.py` to import the new module and add an explicit `elif html_att:` branch before the WEB branch.

**Tech Stack:** Python 3.10+, `beautifulsoup4`, `requests`, `playwright.sync_api`, `re`, `base64`, `urllib.parse`

---

## File Map

| File | Action |
|---|---|
| `requirements.txt` | Add `beautifulsoup4>=4.12.0` |
| `web_extraction_router.py` | Create (copy of `web_scraper.py` + all new code) |
| `web_scraper.py` | Delete after Task 7 |
| `router.py` | Update import; add `html_att` detection; add `elif html_att:` branch; update WEB branch |
| `tests/test_web_extraction_router.py` | Rename from `test_web_scraper.py`; update all imports and patch strings; add new tests |
| `tests/test_router.py` | Update two patch strings from `web_scraper` → `web_extraction_router` |

---

## Task 1: Add beautifulsoup4 dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add after `requests>=2.31.0`:
```
beautifulsoup4>=4.12.0
```

- [ ] **Step 2: Verify install**

```bash
cd /home/ai/rvc-invoices-bot
pip install beautifulsoup4
```
Expected: `Successfully installed` (or `already satisfied`).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add beautifulsoup4 dependency for HTML parsing"
```

---

## Task 2: Create web_extraction_router.py and rename test file

**Files:**
- Create: `web_extraction_router.py`
- Create: `tests/test_web_extraction_router.py` (from `test_web_scraper.py`)
- Modify: `tests/test_router.py`

- [ ] **Step 1: Copy web_scraper.py to web_extraction_router.py**

```bash
cp /home/ai/rvc-invoices-bot/web_scraper.py /home/ai/rvc-invoices-bot/web_extraction_router.py
```

- [ ] **Step 2: Copy test file**

```bash
cp /home/ai/rvc-invoices-bot/tests/test_web_scraper.py \
   /home/ai/rvc-invoices-bot/tests/test_web_extraction_router.py
```

- [ ] **Step 3: Update all imports and patch strings in test_web_extraction_router.py**

Replace every occurrence of `web_scraper` with `web_extraction_router` in the new test file:

```bash
sed -i 's/web_scraper/web_extraction_router/g' \
    /home/ai/rvc-invoices-bot/tests/test_web_extraction_router.py
```

- [ ] **Step 4: Update the unsupported-domain test — remove the match pattern**

The new `download_invoice_file` shim (added in Task 6) raises `ValueError("All extraction tiers failed …")` instead of `"Unsupported …"`. Update the test now so it does not break later.

Open `tests/test_web_extraction_router.py` and find `test_download_invoice_file_raises_unsupported_domain`. Change:

```python
# BEFORE
with pytest.raises(ValueError, match="Unsupported"):
    download_invoice_file(body, "")
```

to:

```python
# AFTER
with pytest.raises(ValueError):
    download_invoice_file(body, "")
```

- [ ] **Step 5: Update test_router.py patch strings**

In `tests/test_router.py` lines 92 and 112, change both patch paths:

```python
# BEFORE (line 92)
with patch("router.web_scraper.download_invoice_file", return_value=(b"<HDon/>", "xml")) as mock_web, \

# AFTER
with patch("router.web_extraction_router.process_branch_4", return_value=(b"<HDon/>", "xml")) as mock_web, \
```

```python
# BEFORE (line 112)
with patch("router.web_scraper.download_invoice_file", return_value=(b"%PDF", "pdf")), \

# AFTER
with patch("router.web_extraction_router.process_branch_4", return_value=(b"%PDF", "pdf")), \
```

- [ ] **Step 6: Run existing tests against the new file**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -v
```

Expected: all existing tests pass (the file is currently identical to `web_scraper.py`).

- [ ] **Step 7: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py tests/test_router.py
git commit -m "refactor: copy web_scraper to web_extraction_router, update test imports"
```

---

## Task 3: Add Tier 1 — extract_xml_from_html_attachment

**Files:**
- Modify: `web_extraction_router.py`
- Modify: `tests/test_web_extraction_router.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_extraction_router.py`:

```python
import base64


# ── Tier 1 ──────────────────────────────────────────────────────────────────

VALID_XML_BYTES = b'<?xml version="1.0" encoding="UTF-8"?><Root/>'
VALID_XML_B64 = base64.b64encode(VALID_XML_BYTES).decode()


def test_tier1_extracts_xml_from_hidden_input_by_id():
    from web_extraction_router import extract_xml_from_html_attachment
    html = f'<html><body><input type="hidden" id="xmlData" value="{VALID_XML_B64}"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_extracts_xml_from_hidden_input_by_name():
    from web_extraction_router import extract_xml_from_html_attachment
    html = f'<html><body><input type="hidden" name="xmlContent" value="{VALID_XML_B64}"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_regex_fallback_finds_base64_in_other_attribute():
    from web_extraction_router import extract_xml_from_html_attachment
    # No xml in id/name, but a long base64 value in a data- attribute
    html = f'<html><body><div data-payload="{VALID_XML_B64}"></div></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_returns_none_on_invalid_base64():
    from web_extraction_router import extract_xml_from_html_attachment
    html = '<html><body><input type="hidden" id="xmlData" value="not-valid-base64!!!"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is None


def test_tier1_returns_none_when_no_hidden_inputs():
    from web_extraction_router import extract_xml_from_html_attachment
    html = "<html><body><p>No invoice data here.</p></body></html>"
    result = extract_xml_from_html_attachment(html)
    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier1" -v
```

Expected: `ImportError` or `AttributeError` — `extract_xml_from_html_attachment` does not exist yet.

- [ ] **Step 3: Implement extract_xml_from_html_attachment in web_extraction_router.py**

Add these imports at the top of `web_extraction_router.py` (after existing imports):

```python
import base64
from bs4 import BeautifulSoup
```

Add this constant after the existing constants block (after `USER_AGENT`):

```python
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{60,}={0,2}$")
```

Add this function before `_extract_urls`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier1" -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest tests/test_web_extraction_router.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py
git commit -m "feat: add Tier 1 extract_xml_from_html_attachment"
```

---

## Task 4: Add Tier 2 — extract_direct_link

**Files:**
- Modify: `web_extraction_router.py`
- Modify: `tests/test_web_extraction_router.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_extraction_router.py`:

```python
# ── Tier 2 ──────────────────────────────────────────────────────────────────

def test_tier2_finds_tai_xml_anchor_returns_xml():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/getXml?id=1">Tải XML</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    content, ctype = result
    assert ctype == "xml"
    assert content.startswith(b"<?xml")


def test_tier2_finds_anchor_by_href_keyword():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/exportXml?token=ABC">Xem hóa đơn</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_tier2_finds_tai_pdf_anchor_returns_pdf():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.content = b"%PDF-1.4 fake"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/invoice.pdf">Tải PDF</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    _, ctype = result
    assert ctype == "pdf"


def test_tier2_token_url_in_text_body_caught_by_substrategy1():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    # URL is in plain text (email_body_text), not in HTML
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(
            email_body_html="",
            email_body_text="https://example.com/download?token=XYZ123",
        )
    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_tier2_returns_none_when_no_matching_links():
    from web_extraction_router import extract_direct_link
    html = '<a href="https://example.com/about">About us</a>'
    result = extract_direct_link(html)
    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier2" -v
```

Expected: `ImportError` or `AttributeError`.

- [ ] **Step 3: Add constants to web_extraction_router.py**

Add after `_BASE64_RE`:

```python
_VN_DOWNLOAD_TEXT_RE = re.compile(
    r"(Tải XML|Download XML|Xuất XML|Tải PDF|Download PDF)",
    re.IGNORECASE,
)
_HREF_DOWNLOAD_RE = re.compile(
    r"(getXml|exportXml|downloadXml|download)",
    re.IGNORECASE,
)
```

- [ ] **Step 4: Implement extract_direct_link in web_extraction_router.py**

Add after `extract_xml_from_html_attachment`:

```python
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
```

- [ ] **Step 5: Run tests**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier2" -v
```

Expected: 5 tests pass.

- [ ] **Step 6: Full suite regression check**

```bash
pytest tests/test_web_extraction_router.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py
git commit -m "feat: add Tier 2 extract_direct_link with Vietnamese link and token-URL support"
```

---

## Task 5: Add scrape_easyinvoice and Tier 3 — dynamic_web_router

**Files:**
- Modify: `web_extraction_router.py`
- Modify: `tests/test_web_extraction_router.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_extraction_router.py`:

```python
# ── Tier 3 ──────────────────────────────────────────────────────────────────

def test_tier3_routes_easyinvoice_subdomain_to_scrape_easyinvoice():
    from web_extraction_router import dynamic_web_router
    xml_bytes = b"<?xml version='1.0'?><HDon/>"
    with patch("web_extraction_router.scrape_easyinvoice", return_value=xml_bytes) as mock_scraper:
        result = dynamic_web_router(
            "https://0310674520hd.easyinvoice.vn/lookup",
            "CODE123",
            "",
        )
    mock_scraper.assert_called_once_with("https://0310674520hd.easyinvoice.vn/lookup", "CODE123")
    assert result == (xml_bytes, "xml")


def test_tier3_routes_meinvoice_to_scrape_misa():
    from web_extraction_router import dynamic_web_router
    xml_bytes = b"<?xml version='1.0'?><HDon/>"
    with patch("web_extraction_router.scrape_misa", return_value=xml_bytes) as mock_scraper:
        result = dynamic_web_router(
            "https://www.meinvoice.vn/tra-cuu",
            "MKKUXJMAG",
            "",
        )
    mock_scraper.assert_called_once()
    assert result == (xml_bytes, "xml")


def test_tier3_unknown_domain_logs_warning_returns_none(caplog):
    from web_extraction_router import dynamic_web_router
    import logging
    with caplog.at_level(logging.WARNING, logger="web_extraction_router"):
        result = dynamic_web_router(
            "https://unknown-portal.vn/invoice",
            "ABC123",
            "",
        )
    assert result is None
    assert "Unsupported provider domain" in caplog.text
    assert "unknown-portal.vn" in caplog.text
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier3" -v
```

Expected: `ImportError` or `AttributeError`.

- [ ] **Step 3: Implement scrape_easyinvoice in web_extraction_router.py**

Add after `scrape_misa` (before `scrape_petrolimex`):

```python
def scrape_easyinvoice(url: str, code: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.fill(
            'input[placeholder*="mã"], input[id*="lookup"], input[type="text"]:first-of-type',
            code,
        )
        page.click('button[type="submit"], button:has-text("Tra cứu")')
        page.wait_for_load_state("networkidle", timeout=20000)
        data = _playwright_download(
            page,
            ['a:has-text("XML")', 'button:has-text("Tải XML")', 'a[href*=".xml"]'],
        )
        browser.close()
        return data
```

- [ ] **Step 4: Implement dynamic_web_router in web_extraction_router.py**

Add after `scrape_generic` and `SCRAPERS` dict (the existing dict stays unchanged):

```python
def dynamic_web_router(
    lookup_url: str,
    lookup_code: str,
    email_body: str,
) -> tuple[bytes, str] | None:
    domain = urlparse(lookup_url).netloc

    if "easyinvoice" in domain:
        scraper_fn = scrape_easyinvoice
    elif domain in SCRAPERS:
        scraper_fn = SCRAPERS[domain]
    else:
        logger.warning(
            f"Unsupported provider domain: {domain}. Pushed to manual review list"
        )
        return None

    for attempt in range(2):
        try:
            xml_bytes = scraper_fn(lookup_url, lookup_code)
            logger.info(f"Playwright download success: domain={domain} code={lookup_code}")
            return xml_bytes, "xml"
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Playwright attempt 1 failed ({domain}): {e}, retrying in 3s")
                time.sleep(3)
            else:
                logger.error(f"Playwright attempt 2 failed ({domain}): {e}")
                return None

    return None
```

- [ ] **Step 5: Run tests**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "tier3" -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Full suite regression check**

```bash
pytest tests/test_web_extraction_router.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py
git commit -m "feat: add scrape_easyinvoice and Tier 3 dynamic_web_router"
```

---

## Task 6: Add process_branch_4 and download_invoice_file shim

**Files:**
- Modify: `web_extraction_router.py`
- Modify: `tests/test_web_extraction_router.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_extraction_router.py`:

```python
# ── process_branch_4 ─────────────────────────────────────────────────────────

def test_process_branch4_tier2_success_skips_tier3():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = '<a href="https://example.com/getXml?id=1">Tải XML</a>'
    email.text = ""

    xml_resp = MagicMock()
    xml_resp.headers = {"Content-Type": "application/xml"}
    xml_resp.content = b"<?xml version='1.0'?><HDon/>"
    xml_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=xml_resp), \
         patch("web_extraction_router.dynamic_web_router") as mock_t3:
        result = process_branch_4(email)

    assert result is not None
    assert result[1] == "xml"
    mock_t3.assert_not_called()


def test_process_branch4_tier2_fails_tier3_succeeds():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = ""
    email.text = "mã tra cứu: MKKUXJMAG\nhttps://www.meinvoice.vn/tra-cuu"

    with patch("web_extraction_router.extract_direct_link", return_value=None), \
         patch("web_extraction_router.dynamic_web_router",
               return_value=(b"<?xml?><HDon/>", "xml")) as mock_t3:
        result = process_branch_4(email)

    assert result == (b"<?xml?><HDon/>", "xml")
    mock_t3.assert_called_once()


def test_process_branch4_both_tiers_fail_returns_none():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = ""
    email.text = "Nothing useful here."

    with patch("web_extraction_router.extract_direct_link", return_value=None), \
         patch("web_extraction_router.dynamic_web_router", return_value=None):
        result = process_branch_4(email)

    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "process_branch4" -v
```

Expected: `ImportError` or `AttributeError`.

- [ ] **Step 3: Implement process_branch_4 and the shim in web_extraction_router.py**

Add at the bottom of `web_extraction_router.py`, replacing the existing `download_invoice_file` function entirely:

```python
class _EmailBodyProxy:
    __slots__ = ("text", "html")

    def __init__(self, text: str, html: str) -> None:
        self.text = text
        self.html = html


def process_branch_4(email_obj) -> tuple[bytes, str] | None:
    email_body_html = email_obj.html or ""
    email_body_text = email_obj.text or ""
    combined = email_body_text + " " + email_body_html

    logger.debug(f"process_branch_4 email body text:\n{email_body_text}")
    logger.debug(f"process_branch_4 email body html:\n{email_body_html}")

    # Tier 2: direct links (token URLs + Vietnamese-labeled anchors)
    result = extract_direct_link(email_body_html, email_body_text)
    if result:
        return result

    # Tier 3: domain-based Playwright router
    code = _extract_lookup_code(combined)
    urls = _extract_urls(combined)
    lookup_url = urls[0] if urls else None
    if code and lookup_url:
        result = dynamic_web_router(lookup_url, code, combined)
        if result:
            return result

    return None


def download_invoice_file(body_text: str, body_html: str) -> tuple[bytes, str]:
    """Compatibility shim — wraps process_branch_4 for callers using the old signature."""
    result = process_branch_4(_EmailBodyProxy(body_text, body_html))
    if result is None:
        raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
    return result
```

- [ ] **Step 4: Run new tests**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_web_extraction_router.py -k "process_branch4" -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Full suite regression check**

```bash
pytest tests/test_web_extraction_router.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add web_extraction_router.py tests/test_web_extraction_router.py
git commit -m "feat: add process_branch_4 wrapper and download_invoice_file compatibility shim"
```

---

## Task 7: Update router.py, delete web_scraper.py

**Files:**
- Modify: `router.py`
- Delete: `web_scraper.py`
- Delete: `tests/test_web_scraper.py`

- [ ] **Step 1: Update the import in router.py**

In `router.py` line 11, change:
```python
# BEFORE
import web_scraper
```
to:
```python
# AFTER
import web_extraction_router
```

- [ ] **Step 2: Add html_att detection in router.py**

In `router.py` inside `process_email`, find the block where attachments are detected (lines 31–33). Add `html_att`:

```python
        xml_att = _find_attachment(email, ".xml")
        zip_att = _find_attachment(email, ".zip")
        pdf_att = _find_attachment(email, ".pdf")
        html_att = _find_attachment(email, ".html")   # add this line
```

- [ ] **Step 3: Add elif html_att: branch in router.py**

After the `elif pdf_att:` block (before `else:`), insert:

```python
        elif html_att:
            branch = "HTML"
            logger.info(f"Branch HTML | uid={email.uid} | subject='{subject}'")
            html_content = html_att.payload.decode("utf-8", errors="replace")
            xml_bytes = web_extraction_router.extract_xml_from_html_attachment(html_content)
            if xml_bytes is None:
                raise ValueError("No Base64 XML found in HTML attachment")
            data = data_extractor.parse_xml(xml_bytes)
```

- [ ] **Step 4: Update the WEB branch in router.py**

Find the `else:` block (WEB branch). Replace:

```python
            file_bytes, content_type = web_scraper.download_invoice_file(
                email.text or "", email.html or ""
            )
```

with:

```python
            result = web_extraction_router.process_branch_4(email)
            if result is None:
                raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
            file_bytes, content_type = result
```

- [ ] **Step 5: Run router tests**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/test_router.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (test_web_scraper.py is still present but its imports will fail — confirm no references to it remain before deleting).

- [ ] **Step 7: Delete old files**

```bash
rm /home/ai/rvc-invoices-bot/web_scraper.py
rm /home/ai/rvc-invoices-bot/tests/test_web_scraper.py
```

- [ ] **Step 8: Run full test suite again to confirm clean state**

```bash
cd /home/ai/rvc-invoices-bot
pytest tests/ -v
```

Expected: all tests pass with no import errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: update router.py for web_extraction_router, add HTML branch, remove web_scraper.py"
```

---

## Self-Review Checklist

- [x] **Tier 1** (`extract_xml_from_html_attachment`) — Task 3 ✓
- [x] **Tier 2** (`extract_direct_link`) — Task 4 ✓; handles both XML and PDF; scans text + HTML for token URLs
- [x] **Tier 3** (`dynamic_web_router`) — Task 5 ✓; EasyInvoice substring check; safe fallback with warning log
- [x] **scrape_easyinvoice** — Task 5 ✓
- [x] **process_branch_4** — Task 6 ✓; debug logs for both bodies; returns `tuple[bytes, str] | None`
- [x] **download_invoice_file shim** — Task 6 ✓; raises ValueError when None returned
- [x] **router.py HTML branch** — Task 7 ✓; ValueError when Tier 1 returns None
- [x] **router.py WEB branch None guard** — Task 7 ✓
- [x] **test_router.py patches updated** — Task 2 ✓
- [x] **beautifulsoup4 in requirements** — Task 1 ✓
- [x] **web_scraper.py deleted** — Task 7 ✓
