# Design: web_extraction_router.py (replaces web_scraper.py)

**Date:** 2026-04-28  
**Status:** Approved  

---

## Overview

Replace `web_scraper.py` with `web_extraction_router.py` — a 3-tier fallback module for the WEB branch (Branch 4) of the Vietnamese E-invoice email pipeline. The new module extends the existing file in-place (Approach 3), preserving all working Playwright scrapers and adding Tier 1 (Base64 HTML attachment), an improved Tier 2 (Vietnamese-labeled links + token links + PDF support), and a cleaner Tier 3 (domain router with safe fallback).

---

## Decisions Made

| Question | Decision |
|---|---|
| Existing scrapers (Petrolimex, Viettel, VNPT) | Kept in same file — same pattern as MISA/EasyInvoice |
| Return type of `process_branch_4` | `tuple[bytes, str] \| None` — same contract as existing `download_invoice_file` |
| HTML attachment detection location | `router.py` explicit `elif html_att:` branch (Tier 1 called directly) |
| Approach | Extend `web_scraper.py` in-place, rename to `web_extraction_router.py` |

---

## File Changes

| File | Action |
|---|---|
| `web_scraper.py` | Extended and renamed → `web_extraction_router.py` |
| `router.py` | Add `elif html_att:` branch; update import and WEB-branch call |
| `tests/test_web_scraper.py` | Renamed → `test_web_extraction_router.py`; imports updated |
| `requirements.txt` | Add `beautifulsoup4` |

---

## Architecture

### Tier 1 — `extract_xml_from_html_attachment(html_content: str) -> bytes | None`

Called from `router.py`'s new `elif html_att:` branch. Not called inside `process_branch_4`.

Strategy:
1. Parse HTML with BeautifulSoup.
2. Find `<input type="hidden">` whose `id` or `name` contains `"xml"` (case-insensitive). Decode `value` attribute from Base64.
3. Fallback: regex sweep all attributes for values matching Base64 pattern (length > 100, valid charset). Try each candidate.
4. Validate decoded bytes start with `b"<?xml"` or `b"<"`. Return bytes or `None`.

---

### Tier 2 — `extract_direct_link(email_body_html: str) -> tuple[bytes, str] | None`

Called first inside `process_branch_4`. Handles both XML and PDF.

Sub-strategies in order:
1. **Token/direct links**: run existing `_try_direct_download()` against all URLs extracted from the HTML body. Detects XML (`<?xml` magic bytes or `xml` Content-Type) and PDF (`%PDF` magic bytes or `pdf` Content-Type). Returns `(bytes, "xml")` or `(bytes, "pdf")`.
2. **Vietnamese-labeled `<a>` tags**: BeautifulSoup finds anchors whose visible text matches `Tải XML`, `Download XML`, `Tải PDF`, `Download PDF`, `Xuất XML`, or whose `href` contains `getXml`, `exportXml`, `downloadXml`, `download`. GETs each candidate and applies the same XML/PDF content detection.

Returns `tuple[bytes, str] | None`.

---

### Tier 3 — `dynamic_web_router(lookup_url: str, lookup_code: str, email_body: str) -> tuple[bytes, str] | None`

Called from `process_branch_4` when Tier 2 returns `None`.

Routing logic (domain parsed from `lookup_url`):
- domain contains `"easyinvoice"` → `scrape_easyinvoice(url, code)`
- domain in `SCRAPERS` dict (exact: `www.meinvoice.vn`, `hoadon.petrolimex.com.vn`, `vietteltelecom.vn`, `vnpt-invoice.com.vn`) → existing scraper
- no match → `logger.warning("Unsupported provider domain: {domain}. Pushed to manual review list")` → return `None` (no exception raised)

Always returns `(bytes, "xml")` on success (Playwright intercepts `.xml` downloads).

---

### New scraper — `scrape_easyinvoice(url: str, code: str) -> bytes`

Playwright headless. Same pattern as existing scrapers:
- Navigate to `url`
- Fill code input: `input[placeholder*="mã"], input[id*="lookup"], input[type="text"]:first-of-type`
- Click submit: `button[type="submit"], button:has-text("Tra cứu")`
- Intercept download via `_playwright_download()`

EasyInvoice uses dynamic subdomains (e.g. `0310674520hd.easyinvoice.vn`) — routing uses `"easyinvoice" in domain` substring check, not exact match.

---

### Main wrapper — `process_branch_4(email_obj) -> tuple[bytes, str] | None`

```
email_body_html = email_obj.html or ""
email_body_text = email_obj.text or ""
combined = email_body_text + " " + email_body_html

logger.debug(f"process_branch_4 email body text:\n{email_body_text}")
logger.debug(f"process_branch_4 email body html:\n{email_body_html}")

# Tier 2
result = extract_direct_link(email_body_html)
if result:
    return result

# Tier 3
code = _extract_lookup_code(combined)
urls = _extract_urls(combined)
lookup_url = first URL from urls (any domain)
if code and lookup_url:
    result = dynamic_web_router(lookup_url, code, combined)
    if result:
        return result

return None
```

Debug logs are emitted at `logging.DEBUG` level — they appear only when the logger's effective level is DEBUG, so no runtime cost in production.

### Compatibility shim

`download_invoice_file(body_text, body_html)` is kept as a thin wrapper that constructs a minimal email-like object and calls `process_branch_4`, so any code or tests referencing the old name continue to work during transition.

---

## router.py Changes

### 1. Import
```python
import web_extraction_router   # replaces: import web_scraper
```

### 2. HTML attachment detection (alongside existing attachment lookups)
```python
html_att = _find_attachment(email, ".html")
```

### 3. New elif branch (inserted before the else/WEB branch)
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

### 4. WEB branch call update
```python
result = web_extraction_router.process_branch_4(email)
if result is None:
    raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
file_bytes, content_type = result
# replaces: web_scraper.download_invoice_file(email.text or "", email.html or "")
```

The `if content_type == "xml" / else` logic below is unchanged.

---

## Test Strategy

**File:** `tests/test_web_scraper.py` → `tests/test_web_extraction_router.py`  
All existing tests kept. Import paths updated to `web_extraction_router`.

### New tests

**Tier 1 — `extract_xml_from_html_attachment`**
- Hidden input `id="xmlData"` with valid Base64 XML → returns bytes starting with `<?xml`
- Hidden input `name="xmlContent"` → same
- Regex fallback (no matching id/name, long Base64 attribute) → returns bytes
- Invalid Base64 → returns `None`
- No hidden inputs → returns `None`

**Tier 2 — `extract_direct_link`**
- `<a>` text `Tải XML` → `(bytes, "xml")`
- `<a>` href contains `getXml` → `(bytes, "xml")`
- `<a>` text `Tải PDF` → `(bytes, "pdf")`
- Token URL in body (no `<a>`) → `_try_direct_download` catches it → `(bytes, "xml")`
- No matching links → `None`

**Tier 3 — `dynamic_web_router`**
- Domain `0310674520hd.easyinvoice.vn` → routes to `scrape_easyinvoice` (mocked)
- Domain `www.meinvoice.vn` → routes to `scrape_misa` (mocked)
- Unknown domain → logs warning, returns `None`, no exception raised

**`process_branch_4`**
- Tier 2 succeeds → returns immediately, Tier 3 not called
- Tier 2 fails, Tier 3 succeeds → returns from Tier 3
- Both fail → returns `None`

---

## Dependencies

- `beautifulsoup4` — add to `requirements.txt`
- All other deps already present (`requests`, `playwright`, `re`, `base64`, `urllib.parse`)
