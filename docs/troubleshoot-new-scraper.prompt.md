---
description: >
  Step-by-step troubleshooting workflow for building and debugging a new
  invoice scraper. Covers everything from email inspection to full end-to-end
  validation, based on lessons learned from the Petrolimex and VNPT scrapers.
---

# New Scraper Troubleshoot Workflow

Use this prompt when asked to **troubleshoot** or **add a new scraper** for a domain not yet in `scrapers/factory.py`.

Inputs — the user provides **one** of:

| Mode        | Required                                        |
|-------------|--------------------------------------------------|
| Email UID   | `uid=<number>` — an IMAP message UID in INBOX    |
| Direct pair | `url=<url>` **and** `lookup_code=<code>`         |

---

## Phase 0 — Decide Input Mode

```
IF uid provided:
    run Phase 1 (email inspection)
ELSE IF url + lookup_code provided:
    skip to Phase 2 (domain check)
```

---

## Phase 1 — Inspect Email by UID

**Goal:** verify the email contains a parseable lookup code and a known portal URL.

```bash
# Inside container (adjusts sys.path to /app automatically)
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/fetch_email_uid.py <uid>
```

Check the output:

| Field | What to look for |
|-------|-----------------|
| `code = ...` | Must not be `None`. If `None` → fix `REGEX_PATTERNS` in `web_extraction_router.py` |
| `best url` | Must resolve to the invoice portal. If `None` → fix `_pick_best_url` or add a URL pattern |
| Attachments | Note filenames — XML/PDF may already be attached, bypassing the scraper entirely |

**If the code has a trailing `*`** (e.g. `VF4S5TMTE*`), the regex capture group must include `\*?` **inside** the parentheses:
```python
re.compile(r"mã tra cứu.*?[\s:]*([A-Z0-9_]+\*?)\r?$", re.IGNORECASE | re.MULTILINE)
```

---

## Phase 2 — Domain Registration

Check whether the domain is already in `scrapers/factory.py`:

```python
# scrapers/factory.py → _get_registry()
"hoadon.petrolimex.com.vn": PetrolimexScraper,
```

If missing, add it. Then create `scrapers/<newsite>.py` from the template in **Phase 3**.

---

## Phase 3 — Inspect the Portal Page (Playwright Codegen / Debug Script)

Create `scripts/debug_<newsite>.py` following this template.  
The script **must be run inside the container** because `playwright` and `.env` are only there.

```python
#!/usr/bin/env python3
"""Diagnostic: inspect <newsite> invoice portal.

Usage (inside container):
    python /app/scripts/debug_<newsite>.py <lookup_code>
"""
import sys, os, time, re, tempfile
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context
from scrapers.base import capsolver_solve_image

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "TESTCODE"
URL = "https://<newsite-url>"
SHOT_DIR = "/tmp/<newsite>_debug"
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
        txt  = ""
        try: txt = el.inner_text()[:60]
        except: pass
        visible = el.is_visible()
        print(f"  [{i}] tag={tag!r} type={typ!r} id={id_!r} name={name_!r} text={txt!r} visible={visible}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    # ── Step 1: Load page ────────────────────────────────────────────────
    print(f"\n1) Navigating to {URL}")
    page.goto(URL, wait_until="networkidle")
    shot(page, "01_loaded")
    print(f"   Title: {page.title()!r}")

    # ── Step 2: Enumerate interactive elements ───────────────────────────
    dump_elements(page, "input", "All inputs")
    dump_elements(page, "button", "All buttons")
    dump_elements(page, "img", "All images")
    dump_elements(page, "a", "All links")
    dump_elements(page, "form", "All forms")

    # ── Step 3: Fill lookup code ─────────────────────────────────────────
    # TODO: replace selector after inspection above
    CODE_SEL = 'input[type="text"]'  # refine after Step 2
    code_el = page.locator(CODE_SEL).first
    code_el.wait_for(state="visible", timeout=10_000)
    code_el.click(click_count=3)
    code_el.press_sequentially(LOOKUP_CODE, delay=80)
    shot(page, "02_code_filled")
    print(f"\n3) Code field value: {code_el.input_value()!r}")

    # ── Step 4: Solve CAPTCHA (if present) ───────────────────────────────
    CAPTCHA_IMG_SEL = 'img[src*="captch" i], img[src*="Captcha" i]'
    img_loc = page.locator(CAPTCHA_IMG_SEL)
    if img_loc.count() > 0 and img_loc.first.is_visible():
        time.sleep(1)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        img_loc.first.screenshot(path=captcha_path)
        solution = re.sub(r"\s+", "", capsolver_solve_image(captcha_path) or "")
        print(f"\n4) Captcha solution: {solution!r}")
        os.unlink(captcha_path)

        CAPTCHA_INPUT_SEL = 'input[id*="captch" i], input[name*="captch" i]'
        captcha_el = page.locator(CAPTCHA_INPUT_SEL).first
        captcha_el.click(click_count=3)
        captcha_el.press_sequentially(solution, delay=100)
        shot(page, "03_captcha_filled")
    else:
        solution = ""
        print("\n4) No captcha found")

    # ── Step 5: Identify submit button — CRITICAL ────────────────────────
    # WARNING: tab-style <button> elements without type="submit" appear in DOM
    # BEFORE the real submit — always use input[type="submit"] first, never
    # bare 'button' selectors.
    SUBMIT_CANDIDATES = [
        'input[type="submit"]',
        'input[name="submit"]',
        'button[type="submit"]',
        # NEVER add bare 'button' here — it matches tab/navigation buttons
    ]
    print("\n5) Submit candidates:")
    for sel in SUBMIT_CANDIDATES:
        loc = page.locator(sel)
        n = loc.count()
        print(f"   {sel!r}: {n} elements")
        for i in range(n):
            el = loc.nth(i)
            tag = el.evaluate("e => e.tagName").lower()
            print(f"     [{i}] tag={tag!r} type={el.get_attribute('type')!r} id={el.get_attribute('id')!r} visible={el.is_visible()}")

    # ── Step 6: Click submit ─────────────────────────────────────────────
    SUBMIT_SEL = (
        'input[type="submit"], '
        'input[name="submit"], '
        'button[type="submit"]'
    )
    btn = page.locator(SUBMIT_SEL).first
    btn.wait_for(state="visible", timeout=15_000)
    btn.hover()
    time.sleep(0.5)
    btn.click()
    shot(page, "04_clicked_submit")

    # ── Step 7: Wait and inspect result ─────────────────────────────────
    try:
        page.locator('a:has-text("Tải"), a:has-text("Download"), a[href*=".xml"], a[href*=".pdf"]').first.wait_for(state="visible", timeout=20_000)
    except Exception:
        time.sleep(6)
    shot(page, "05_after_submit")

    body = page.evaluate("() => document.body.innerText")
    print(f"\n7) Body after submit (500 chars):\n{body[:500]}")

    # Enumerate download links
    dump_elements(page, 'a[href*=".xml"], a[href*=".pdf"], a:has-text("Tải"), a:has-text("Download")', "Download links")

    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}/")
```

**Run it:**
```bash
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/debug_<newsite>.py <lookup_code>
```

**Copy screenshots out** (optional):
```bash
docker compose cp rvc-invoices-bot:/tmp/<newsite>_debug ./debug_shots/
```

---

## Phase 4 — Identify Selectors

From the debug output, fill in this selector checklist:

| Selector variable       | What to confirm                                                        |
|-------------------------|------------------------------------------------------------------------|
| `_CODE_SEL`             | Matches exactly the lookup code `<input>` — check `id`, `name`        |
| `_CAPTCHA_IMG_SEL`      | Matches the captcha `<img>` — check `src` pattern                     |
| `_CAPTCHA_INPUT_SEL`    | Matches the captcha text `<input>` — check `id` (e.g. `#captch` not `#captcha`) |
| `_SUBMIT_SEL`           | **Must be `input[type="submit"]` first**. Check `tag=INPUT` not `BUTTON` |
| `_DOWNLOAD_LINK_SEL`    | Matches all file download `<a>` or `<button>` links after result loads |

**Submit selector pitfall (Petrolimex lesson):**
The page may have `<button>` elements (tabs, navigation) that appear in DOM order **before** the real submit. A selector like `button` or `#form button` will match them first and do nothing. Always prefer:
```python
_SUBMIT_SEL = (
    '#MyForm input[type="submit"], '
    '#MyForm input[name="submit"], '
    '#MyForm button[type="submit"], '
    'input[type="submit"]'            # global fallback
)
```

**reCAPTCHA v2 detection:**
If the page loads `https://www.google.com/recaptcha/api.js`, it uses reCAPTCHA v2 — **not** an image captcha. The sitekey is embedded in the iframe URL:
```
https://www.google.com/recaptcha/api2/anchor?ar=1&k=<SITE_KEY>&...
```
Extract it from `page.frames`:
```python
for f in page.frames:
    if "recaptcha/api2/anchor" in f.url:
        import re
        m = re.search(r"[?&]k=([^&]+)", f.url)
        print("sitekey:", m.group(1) if m else "not found")
```
Also confirm `window.___grecaptcha_cfg.clients` exists (used for token injection).

---

## Phase 4b — reCAPTCHA v2 with Capsolver

When the site uses reCAPTCHA v2 (checkbox "Tôi không phải là người máy"), the image-captcha `capsolver_solve_image()` approach does **not** apply. Instead:

### Step 1 — Solve via Capsolver `ReCaptchaV2TaskProxyLess`

```python
import os, time, requests

def _capsolver_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    api_key = os.environ.get("CAPSOLVER_API_KEY", "")
    if not api_key:
        return None
    create = requests.post(
        "https://api.capsolver.com/createTask",
        json={"clientKey": api_key, "task": {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }},
        timeout=15,
    ).json()
    if create.get("errorId", 0) != 0:
        return None
    task_id = create["taskId"]
    for _ in range(60):
        time.sleep(2)
        result = requests.post(
            "https://api.capsolver.com/getTaskResult",
            json={"clientKey": api_key, "taskId": task_id},
            timeout=10,
        ).json()
        if result.get("status") == "ready":
            return result.get("solution", {}).get("gRecaptchaResponse", "")
        if result.get("status") not in ("processing", "idle", None):
            return None
    return None
```

Typical solve time: **10–40 seconds**.

### Step 2 — Find the React/JS success callback

The reCAPTCHA widget registers a callback in `window.___grecaptcha_cfg.clients[0]`.
The path is **always** `clients[0].T.T.callback` (a 1-argument function). Verify in a debug script:

```python
result = page.evaluate("""() => {
    const cfg = window.___grecaptcha_cfg;
    if (!cfg || !cfg.clients) return 'no clients';
    const c = cfg.clients[0];
    const funcs = [];
    function scan(obj, path, depth) {
        if (depth > 5 || !obj || typeof obj !== 'object') return;
        for (const k of Object.keys(obj)) {
            const v = obj[k];
            if (typeof v === 'function')
                funcs.push('FUNC ' + path + '.' + k + ' len=' + v.length);
            else if (v && typeof v === 'object')
                scan(v, path + '.' + k, depth + 1);
        }
    }
    scan(c, 'clients[0]', 0);
    return funcs;
}""")
# Look for: FUNC clients[0].T.T.callback len=1
```

> **Note:** The path letters (`T`, `T`) are minified and may differ across sites/versions, but the pattern is a 1-argument function named `callback` near the sitekey. Verify before hardcoding.

### Step 3 — Inject token via the callback

```python
def _inject_token(self, token: str) -> None:
    self.page.evaluate(
        """(token) => {
            // 1. Set hidden textarea (belt-and-suspenders)
            const ta = document.getElementById('g-recaptcha-response');
            if (ta) { ta.value = token; }
            // 2. Call the reCAPTCHA success callback to trigger React onChange
            try {
                const cfg = window.___grecaptcha_cfg;
                if (cfg && cfg.clients && cfg.clients[0] &&
                        cfg.clients[0].T && cfg.clients[0].T.T) {
                    const cb = cfg.clients[0].T.T.callback;
                    if (typeof cb === 'function') { cb(token); }
                }
            } catch (e) {}
        }""",
        token,
    )
```

After injection, verify the submit button is **no longer disabled**:
```python
disabled = page.locator("button:has-text('Tra cứu hóa đơn')").first.evaluate("e => e.disabled")
assert not disabled, "submit still disabled — callback path wrong"
```

### Step 4 — Scraper structure for reCAPTCHA v2

Unlike image-captcha scrapers (which retry with `page.reload()`), the reCAPTCHA v2 flow must re-navigate on each attempt because the widget state is tied to the page load:

```python
for attempt in range(_MAX_RETRIES):
    self.page.goto(_BASE_URL, wait_until="networkidle")
    self._delay(1.0, 2.0)

    self._enter_code()

    token = _capsolver_recaptcha_v2(_SITE_KEY, _BASE_URL)
    if not token:
        if attempt < _MAX_RETRIES - 1:
            continue
        raise CaptchaRequiredException(...)

    self._inject_token(token)
    self._delay(0.3, 0.7)

    btn = self.page.locator(_SUBMIT_SEL).first
    if btn.evaluate("e => e.disabled"):
        if attempt < _MAX_RETRIES - 1:
            continue
        raise CaptchaRequiredException(...)

    btn.hover(); self._delay(0.2, 0.5); btn.click()
    # wait for result modal / download links ...
```

**Real example:** `scrapers/cmcinvoice.py` — CMC Telecom portal (cinvoice.cmctelecom.vn).

---

## Phase 5 — Write the Scraper Class

Create `scrapers/<newsite>.py`:

```python
import logging, os, re, time, random, tempfile
from .base import BaseInvoiceScraper, capsolver_solve_image
from .exceptions import CaptchaRequiredException, InvoiceNotFoundException
from .result import ScrapedResult

logger = logging.getLogger(__name__)

# --- Fill in selectors from Phase 4 ---
_CODE_SEL          = '...'
_CAPTCHA_IMG_SEL   = '...'
_CAPTCHA_INPUT_SEL = '...'
_SUBMIT_SEL        = (
    '... input[type="submit"], '
    '... input[name="submit"], '
    '... button[type="submit"], '
    'input[type="submit"]'
)
_DOWNLOAD_LINK_SEL = '...'
_MAX_RETRIES       = 3


class <NewSite>Scraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        for attempt in range(_MAX_RETRIES):
            self._enter_code()
            solution = self._screenshot_and_solve_captcha()

            # Validate captcha format (adjust regex for this site)
            if not solution or not re.fullmatch(r"[0-9]{4,6}", solution):
                logger.warning("Invalid captcha '%s' on attempt %d", solution, attempt + 1)
                if attempt < _MAX_RETRIES - 1:
                    self.page.reload(wait_until="networkidle")
                continue

            logger.info("Attempt %d/%d: captcha='%s'", attempt + 1, _MAX_RETRIES, solution)
            self._enter_captcha(solution)
            self._click_submit()

            body = self.page.evaluate("() => document.body.innerText").lower()
            # Adjust "not found" keywords for this site's language
            if "không tìm thấy" in body or "không có hóa đơn" in body:
                raise InvoiceNotFoundException(
                    f"<NewSite>: invoice not found for '{self.lookup_code}'"
                )
            if self._downloads_visible():
                break

            logger.warning(
                "<NewSite>: no downloads after attempt %d — body: %s",
                attempt + 1, body[:300],
            )
            if attempt < _MAX_RETRIES - 1:
                self.page.reload(wait_until="networkidle")
        else:
            raise CaptchaRequiredException(
                f"<NewSite>: captcha failed after {_MAX_RETRIES} attempts"
            )

        xml_bytes, pdf_bytes = self._download_all()
        logger.info(
            "<NewSite>: xml=%s pdf=%s",
            f"{len(xml_bytes)}B" if xml_bytes else "none",
            f"{len(pdf_bytes)}B" if pdf_bytes else "none",
        )
        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

    def _enter_code(self) -> None:
        el = self.page.locator(_CODE_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.2)
        el.press_sequentially(self.lookup_code, delay=100)
        self._delay(0.2, 0.5)

    def _screenshot_and_solve_captcha(self) -> str:
        img_loc = self.page.locator(_CAPTCHA_IMG_SEL)
        if img_loc.count() == 0 or not img_loc.first.is_visible():
            return ""
        self._delay(0.5, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            captcha_path = tf.name
        try:
            img_loc.first.screenshot(path=captcha_path)
            result = capsolver_solve_image(captcha_path) or ""
            result = re.sub(r"\s+", "", result)
            logger.info("<NewSite>: captcha = '%s'", result)
            return result
        finally:
            os.unlink(captcha_path)

    def _enter_captcha(self, solution: str) -> None:
        el = self.page.locator(_CAPTCHA_INPUT_SEL).first
        el.wait_for(state="visible", timeout=10_000)
        el.click(click_count=3)
        self._delay(0.1, 0.2)
        el.press_sequentially(solution, delay=random.randint(80, 150))
        self._delay(0.2, 0.5)

    def _click_submit(self) -> None:
        btn = self.page.locator(_SUBMIT_SEL).first
        btn.wait_for(state="visible", timeout=15_000)
        btn.hover()
        self._delay(0.3, 0.8)
        btn.click()
        # Wait actively for results; fall back to fixed sleep
        try:
            self.page.locator(_DOWNLOAD_LINK_SEL).first.wait_for(state="visible", timeout=20_000)
        except Exception:
            time.sleep(6)

    def _downloads_visible(self) -> bool:
        return self.page.locator(_DOWNLOAD_LINK_SEL).count() > 0

    def _download_all(self) -> tuple[bytes | None, bytes | None]:
        xml_bytes: bytes | None = None
        pdf_bytes: bytes | None = None
        links = self.page.locator(_DOWNLOAD_LINK_SEL)
        for i in range(links.count()):
            try:
                with self.page.expect_download(timeout=15_000) as dl:
                    links.nth(i).hover()
                    self._delay(0.2, 0.5)
                    links.nth(i).click()
                path = dl.value.path()
                with open(path, "rb") as f:
                    data = f.read()
                ctype = self._classify_bytes(data)
                if ctype == "xml" and xml_bytes is None:
                    xml_bytes = data
                elif ctype == "pdf" and pdf_bytes is None:
                    pdf_bytes = data
                else:
                    logger.debug("<NewSite>: link[%d] unrecognised type '%s'", i, ctype)
            except Exception as exc:
                logger.debug("<NewSite>: link[%d] download failed: %s", i, exc)
        return xml_bytes, pdf_bytes
```

---

## Phase 6 — Register the Scraper

In `scrapers/factory.py`, add one line inside `_get_registry()`:

```python
from .<newsite> import <NewSite>Scraper

"<newsite-domain.vn>": <NewSite>Scraper,
```

---

## Phase 7 — Unit Tests

Add tests to `tests/test_scrapers.py`. Minimum set:

```python
def test_<newsite>_scraper_instantiation(mock_page):
    s = <NewSite>Scraper(mock_page, "https://<domain>/", "CODE123")
    assert s.lookup_code == "CODE123"

def test_<newsite>_scrape_success(mock_page):
    with patch("scrapers.<newsite>.capsolver_solve_image", return_value="1234"), \
         patch.object(<NewSite>Scraper, "_downloads_visible", side_effect=[False, True]), \
         patch.object(<NewSite>Scraper, "_download_all", return_value=(b"<?xml", b"%PDF")):
        s = <NewSite>Scraper(mock_page, "https://<domain>/", "CODE123")
        result = s.scrape()
    assert result.xml_bytes == b"<?xml"
    assert result.pdf_bytes == b"%PDF"

def test_<newsite>_scrape_invalid_captcha_retries(mock_page):
    with patch("scrapers.<newsite>.capsolver_solve_image", return_value="bad"):
        s = <NewSite>Scraper(mock_page, "https://<domain>/", "CODE123")
        with pytest.raises(CaptchaRequiredException):
            s.scrape()
```

Run:
```bash
docker compose exec -T rvc-invoices-bot pytest tests/test_scrapers.py -v -k <newsite>
```

---

## Phase 8 — End-to-End Test

### Mode A — From email UID

```bash
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/e2e_petrolimex.py <uid>
```

> Reuse `e2e_petrolimex.py` as-is — it calls `scrape_invoice(url, code)` which goes
> through `ScraperFactory`, so it will pick up any registered scraper.

### Mode B — Direct URL + code (no email)

The script already exists at `scripts/e2e_direct.py` and supports an optional `--save-db` flag.

```bash
# Download only
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/e2e_direct.py "https://<domain>/" "CODE123"

# Download + save to DB (runs full router flow)
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/e2e_direct.py "https://<domain>/" "CODE123" --save-db
```

**Expected success output:**
```
INFO | e2e_direct | xml=6718B pdf=418416B
INFO | e2e_direct | SUCCESS (pass --save-db to also write to database)
```

---

## Phase 9 — Save to Database (Full Router Flow)

If you have an email UID, run the full router flow:

```bash
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/e2e_petrolimex.py <uid>
```

If testing directly (no email), use `--save-db`:

```bash
docker compose exec -T rvc-invoices-bot \
    python /app/scripts/e2e_direct.py "https://<domain>/" "CODE123" --save-db
```

Expected final line:
```
INFO | e2e_direct | SUCCESS — invoice saved to database
```

---

## Checklist

- [ ] `fetch_email_uid.py <uid>` → code and URL extracted correctly
- [ ] If code uses non-alphanumeric chars (e.g. `CTEL.…`) → verify `_extract_code_from_table()` picks it up (not `REGEX_PATTERNS`)
- [ ] Domain added to `scrapers/factory.py`
- [ ] `debug_<newsite>.py` run — all selectors verified in output
- [ ] **Image captcha sites:** `_SUBMIT_SEL` confirmed to match `tag=INPUT type="submit"` (not `BUTTON`)
- [ ] **reCAPTCHA v2 sites:** sitekey extracted from anchor-iframe URL; `clients[0].T.T.callback` path confirmed in debug script; submit button enabled after `_inject_token()`
- [ ] Scraper class created in `scrapers/<newsite>.py`
- [ ] `pytest -k <newsite>` — all tests pass
- [ ] E2E script downloads XML + PDF
- [ ] Router saves invoice to DB

---

## Known Pitfalls (from Petrolimex + VNPT debugging)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Capsolver `ImageToTextTask` is synchronous | Solution returned in `createTask` response — `solution.text` is empty string if you poll `getTaskResult` without checking `createTask` first | Check `create_resp["status"] == "ready"` before polling |
| DOM-order button trap | Selector `button` matches a tab/nav button before the real submit; click does nothing; no downloads appear | Use `input[type="submit"]` first; confirm `tag=INPUT` in debug output |
| Captcha input ID typo | Form has `id="captch"` not `id="captcha"` | Always dump all inputs in Phase 3 and verify `id` |
| Lookup code asterisk stripped | Regex `([A-Z0-9]+)\*?` strips `*` — code `VF4S5TMTE*` becomes `VF4S5TMTE` | Move `\*?` inside group: `([A-Z0-9]+\*?)` |
| False positive "captcha wrong" detection | Body text contains captcha label text even on first load | Never check body text for captcha-error keywords; only check for "invoice not found" |
| `_MAX_RETRIES` set to 1 by mistake | Scraper gives up after first failed captcha | Always set `_MAX_RETRIES = 3` |
| `triple_click()` removed in Playwright 1.59 | `AttributeError: triple_click` | Use `click(click_count=3)` |
| `wait_until="networkidle"` too strict | Timeout on pages with background polling | Use `"domcontentloaded"` for initial load + explicit `wait_for(state="visible")` on key elements |
| `expect_page` timeout — modal masquerading as popup | `ajxCall4Portal()` and similar JS functions open an **overlay modal on the same page**, not a new browser tab — `context.expect_page()` never fires | Inspect the button's `onclick` attribute in the debug script. If it calls a JS function rather than `window.open()`, assume same-page modal. Click the button, then `wait_for(state="visible")` on the modal content on the **current page**, then `expect_download` from the same page. |
| Regex too broad — matches wrong field | `mã số` pattern matched "Mã số thuế" (tax code) before "Mã tra cứu hóa đơn" (lookup code) → wrong value extracted | Make patterns as specific as possible: use `mã số tra cứu` or the full label text, not a short prefix that appears in multiple fields. Test with `fetch_email_uid.py`. |
| `router._process_pair` crashes with `email=None` | `AttributeError: 'NoneType' has no attribute 'subject'` when called from `e2e_direct.py` | Guard with `subject = (email.subject or "") if email is not None else ""` |
| Lookup code uses a non-alphanumeric prefix (e.g. `CTEL.…`) | `REGEX_PATTERNS` patterns only capture `[A-Z0-9_]+` — the dot separator causes mismatch; `fetch_email_uid.py` returns `code = None` | Use `_extract_code_from_table()` (table-aware BeautifulSoup scan) instead of adding a custom regex. The code is always the sibling `<td>` of the "Mã tra cứu" label cell. See below. |
| `_extract_code_from_table` returns wrong cell (layout wrapper) | The function picks up the text of a sibling layout cell (e.g. QR caption or "Mẫu số:") instead of the actual code | Use `recursive=False` on `find_all("td")` **and** skip any cell that itself contains a nested `<td>` (`if td.find("td"): continue`). This ensures only leaf cells match. |
| **Slow server — result-wait timeout too short (VNPT)** | Submit succeeds but the results page takes ~60s to render (server-side, not client). A 15s `wait_for_selector` times out, the scraper wrongly concludes "captcha failed", then touches the page **while the POST navigation is still in flight** → `Page.evaluate: Execution context was destroyed, most likely because of a navigation` | Wait generously for the result row (VNPT: `_RESULT_TIMEOUT_MS = 90_000`). Measure the real server time first (open the portal in a browser and watch how long the results take). Give the throwaway bypass probe its own **short** timeout so it still fails fast. |
| **Retry on a navigated page fails (VNPT)** | After the first submit (or the bypass probe) the page navigates to the results URL (`/HomeNoLogin/SearchByFkey`). Its form/captcha state is stale: the captcha `<img>` is gone (solver returns `''`) and re-submitting from there never yields results. In-place captcha refresh (`img.src = base + '?t=' + Date.now()`) does **not** fix this. | **Reload a fresh form at the top of every attempt** (`page.goto(url)` + wait for the code input) — a full page load is the only reliable reset. Same principle as the reCAPTCHA-v2 "re-navigate each attempt" rule. Drop the in-place captcha-refresh helper. |
| Bypass probe corrupts subsequent attempts | `_probe_bypass()` submits a dummy `0000` captcha to detect absent server-side validation; that submit navigates the page away, breaking the real attempts that follow | Keep the probe but ensure the retry loop reloads a clean form before each attempt (see above). The probe result is almost always `False` for VNPT — it never bypasses. |

### VNPT scraper — full working flow (debugged via uid=2082, Jul 2026)

`scrapers/vnpt.py` reference flow, confirmed against `vttphcm-tt78.vnpt-invoice.com.vn`:

1. `_load_fresh_form()` → `page.goto(url, wait_until="domcontentloaded")` + wait for `input#strFkey`.
2. `_probe_bypass()` — dummy `0000` submit with a **short** timeout (`_PROBE_TIMEOUT_MS = 12_000`). Returns `False` here (captcha is enforced).
3. Retry loop (`_MAX_CAPTCHA_RETRIES = 3`), **reloading a fresh form each attempt**:
   - fill code → screenshot `#text img` → Capsolver → `_enter_captcha` into `#text #captch`.
   - submit `button:has-text("Tìm kiếm")` with `no_wait_after=True`, then `wait_for_selector(result_row | validation_error, timeout=90_000)`. The server can take ~60s.
   - a wrong captcha simply re-renders without a result row → the 90s wait expires → reload and retry (a correct captcha on attempt 2/3 succeeds).
4. Results land in a `table.table-main` (headers `STT · Tên hóa đơn · Mẫu số · … · Tải file · … · Tải biên bản`). Download: XML via `Xem` → same-page modal → `Tải hóa đơn Zip` → unzip; PDF via the `/downloadPDF?...` href.

> Debug script: `scripts/debug_vnpt.py <code> [url]` — submits once and dumps post-submit URL, tables, validation nodes, and screenshots to `/tmp/vnpt_debug/`. Run it with the source mounted so it picks up local edits:
> ```bash
> docker compose run --rm -v "$PWD/scrapers:/app/scrapers" rvc-invoices-bot \
>     python /app/scripts/debug_vnpt.py <code>
> ```
> Note: `docker compose run` uses the **baked image** — mount `-v "$PWD/scrapers:/app/scrapers"` (and `/app/scripts`) to test edits without rebuilding.

### Lookup code not captured by `REGEX_PATTERNS` — use table scan

When the email body embeds the code in an HTML table like:
```html
<tr>
  <td><b>Mã tra cứu:</b></td>
  <td><b>CTEL.50A742E6A1F81205E0630E01040AB7A2</b></td>
</tr>
```
`REGEX_PATTERNS` won't match because the label and value are in separate cells (different lines after `get_text()`), and the code may contain characters outside `[A-Z0-9_]`.

**The fix is already in `_extract_lookup_code`** via `_extract_code_from_table()`:
```python
# web_extraction_router.py
_LOOKUP_LABEL_RE = re.compile(r"mã\s+tra\s+cứu", re.IGNORECASE)

def _extract_code_from_table(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False)   # direct children only
        for i, td in enumerate(cells):
            if td.find("td"):   # skip layout wrapper cells
                continue
            if _LOOKUP_LABEL_RE.search(td.get_text()):
                if i + 1 < len(cells):
                    next_td = cells[i + 1]
                    if next_td.find("td"):  # skip if value cell is also a wrapper
                        continue
                    code = next_td.get_text(strip=True)
                    if code:
                        return code
    return None
```
This handles any code format without touching `REGEX_PATTERNS`.
