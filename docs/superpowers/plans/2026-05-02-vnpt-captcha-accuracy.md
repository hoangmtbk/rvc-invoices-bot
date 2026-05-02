# VNPT Captcha Accuracy Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise VNPT captcha pass rate from ~80% to ≥95% via a bypass probe, tiered OCR pipeline (ddddocr → Capsolver → Gemini), and pre-submission digit validation.

**Architecture:** Three independent layers added to `scrapers/vnpt.py`: (1) one-shot bypass probe before the retry loop that short-circuits OCR entirely if the server doesn't validate captcha server-side, (2) `_solve_vnpt_captcha` refactored into a 3-solver pipeline where ddddocr runs on the raw screenshot and Gemini only runs as last resort with Pillow preprocessing, (3) the retry loop validates solver output with `re.fullmatch(r"[0-9]{4}", ...)` before submitting so provably-wrong answers never burn a form attempt.

**Tech Stack:** Python 3.11, ddddocr ≥1.4.11 (new), requests (existing), Gemini 2.5 Flash (existing), Pillow (existing), pytest.

---

## File Map

| File | Changes |
|------|---------|
| `requirements.txt` | Add `ddddocr>=1.4.11` |
| `scrapers/vnpt.py` | Add `_probe_bypass()`, add `_capsolver_solve()`, refactor `_solve_vnpt_captcha()`, update `scrape()` |
| `tests/test_scrapers.py` | Add 6 new tests, update 2 existing tests |

---

### Task 1: Add ddddocr dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add ddddocr to requirements.txt**

Open `requirements.txt` and add the line after `Pillow`:

```
ddddocr>=1.4.11
```

Full updated `requirements.txt`:
```
imap-tools>=1.6.0
google-genai>=0.8.0
Pillow>=10.0.0
ddddocr>=1.4.11
playwright>=1.44.0
playwright-stealth>=1.0.6
schedule>=1.2.2
requests>=2.31.0
minio>=7.2.0
beautifulsoup4>=4.12.0
pandas>=2.1.0
python-dotenv>=1.0.1
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Install and verify**

```bash
pip install ddddocr>=1.4.11
python -c "import ddddocr; ocr = ddddocr.DdddOcr(show_ad=False); print('ddddocr OK')"
```

Expected: prints `ddddocr OK` (may also print a library banner).

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py -v -x
```

Expected: all tests pass (count may vary — just no failures).

- [ ] **Step 4: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add requirements.txt
git commit -m "feat: add ddddocr dependency for VNPT captcha OCR"
```

---

### Task 2: Implement `_probe_bypass()` method + tests

**Files:**
- Modify: `scrapers/vnpt.py` (add method to `VnptScraper`)
- Test: `tests/test_scrapers.py` (add 2 tests)

- [ ] **Step 1: Write failing tests for `_probe_bypass()`**

Add at the end of `tests/test_scrapers.py`:

```python
# ── bypass probe tests ──────────────────────────────────────────────────────

def test_probe_bypass_returns_true_when_submit_succeeds():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    with patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=True):
        assert s._probe_bypass() is True


def test_probe_bypass_returns_false_when_submit_fails():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    with patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=False):
        assert s._probe_bypass() is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_probe_bypass_returns_true_when_submit_succeeds tests/test_scrapers.py::test_probe_bypass_returns_false_when_submit_fails -v
```

Expected: FAIL with `AttributeError: '_probe_bypass'`

- [ ] **Step 3: Implement `_probe_bypass()` in `VnptScraper`**

Add this method to `VnptScraper` in `scrapers/vnpt.py`, after `_fill_lookup_code` (around line 82):

```python
    def _probe_bypass(self) -> bool:
        """Submit with dummy captcha '0000' to detect absent server-side validation."""
        try:
            self._fill_lookup_code()
            self._enter_captcha("0000")
            result = self._submit_and_wait_for_results()
            logger.info("VNPT: bypass probe result=%s", result)
            return result
        except Exception as exc:
            logger.debug("VNPT: bypass probe error: %s", exc)
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_probe_bypass_returns_true_when_submit_succeeds tests/test_scrapers.py::test_probe_bypass_returns_false_when_submit_fails -v
```

Expected: both PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add scrapers/vnpt.py tests/test_scrapers.py
git commit -m "feat: add VnptScraper._probe_bypass() with tests"
```

---

### Task 3: Integrate bypass probe into `scrape()` + patch existing loop tests

**Files:**
- Modify: `scrapers/vnpt.py` (update `scrape()`)
- Test: `tests/test_scrapers.py` (update 2 existing tests)

The two existing retry-loop tests (`test_vnpt_scrape_raises_after_max_captcha_retries` and `test_vnpt_scrape_raises_captcha_after_all_failed_submits`) call `s.scrape()` directly. Once `_probe_bypass()` is called at the top of `scrape()`, we must explicitly mock it out in those tests or they'll exercise probe logic unintentionally.

- [ ] **Step 1: Update `test_vnpt_scrape_raises_after_max_captcha_retries` to patch `_probe_bypass`**

In `tests/test_scrapers.py`, find the existing test and add `patch.object(s, "_probe_bypass", return_value=False)`:

```python
def test_vnpt_scrape_raises_after_max_captcha_retries():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    page.locator.return_value.count.return_value = 0
    page.locator.return_value.first.is_visible.return_value = False

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value=""), \
         pytest.raises(CaptchaRequiredException, match="empty"):
        s.scrape()
```

- [ ] **Step 2: Update `test_vnpt_scrape_raises_captcha_after_all_failed_submits` to patch `_probe_bypass`**

```python
def test_vnpt_scrape_raises_captcha_after_all_failed_submits():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="1234"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=False), \
         patch.object(s, "_refresh_captcha_image"), \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()
```

- [ ] **Step 3: Run updated tests to confirm they still pass before touching `scrape()`**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_vnpt_scrape_raises_after_max_captcha_retries tests/test_scrapers.py::test_vnpt_scrape_raises_captcha_after_all_failed_submits -v
```

Expected: both PASS (probe is now patched out).

- [ ] **Step 4: Add bypass probe integration into `scrape()`**

Replace the current `scrape()` method in `scrapers/vnpt.py` (lines 39–72) with:

```python
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        if self._probe_bypass():
            logger.info("VNPT: captcha bypass confirmed — skipping OCR loop")
            self._assert_invoice_found()
            xml_bytes, pdf_bytes = self._download_all_files()
            if xml_bytes is None and pdf_bytes is None:
                raise InvoiceNotFoundException(
                    f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
                )
            return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

        for attempt in range(_MAX_CAPTCHA_RETRIES):
            self._fill_lookup_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution:
                raise CaptchaRequiredException("VNPT: Gemini returned empty captcha solution")
            logger.info("VNPT attempt %d/%d: captcha='%s'", attempt + 1, _MAX_CAPTCHA_RETRIES, solution)
            self._enter_captcha(solution)

            if self._submit_and_wait_for_results():
                break

            if attempt < _MAX_CAPTCHA_RETRIES - 1:
                logger.warning("VNPT: results table absent after attempt %d, refreshing captcha", attempt + 1)
                self._refresh_captcha_image()
            else:
                raise CaptchaRequiredException(
                    f"VNPT: captcha failed after {_MAX_CAPTCHA_RETRIES} attempts"
                )

        self._assert_invoice_found()

        xml_bytes, pdf_bytes = self._download_all_files()

        if xml_bytes is None and pdf_bytes is None:
            raise InvoiceNotFoundException(
                f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
            )

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 5: Run full test suite**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add scrapers/vnpt.py tests/test_scrapers.py
git commit -m "feat: integrate bypass probe into VnptScraper.scrape()"
```

---

### Task 4: Tiered OCR pipeline

**Files:**
- Modify: `scrapers/vnpt.py` (add `_capsolver_solve()`, refactor `_solve_vnpt_captcha()`)
- Test: `tests/test_scrapers.py` (add 4 new tests)

- [ ] **Step 1: Write failing tests for the tiered pipeline**

Add at the end of `tests/test_scrapers.py`. Note: `import sys` and `import PIL.Image` go at the top of the new block (module-level in the file, valid Python even though not at the very top of the file):

```python
# ── tiered OCR pipeline tests ────────────────────────────────────────────────

import sys
import PIL.Image as _PILImage


def _make_png(tmp_path) -> str:
    """Write a minimal 40x20 greyscale PNG and return its path."""
    p = tmp_path / "cap.png"
    _PILImage.new("L", (40, 20)).save(str(p))
    return str(p)


def test_solve_captcha_uses_ddddocr_when_returns_4_digits(tmp_path):
    # _solve_vnpt_captcha does `import ddddocr` locally at call time;
    # patching sys.modules["ddddocr"] before the call injects our mock.
    img_path = _make_png(tmp_path)
    mock_ddddocr = MagicMock()
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = "5678"
    mock_ddddocr.DdddOcr.return_value = mock_ocr

    with patch.dict(sys.modules, {"ddddocr": mock_ddddocr}):
        result = _solve_vnpt_captcha(img_path)

    assert result == "5678"
    mock_ocr.classification.assert_called_once()


def test_solve_captcha_falls_back_to_gemini_when_ddddocr_returns_non_digits(tmp_path):
    img_path = _make_png(tmp_path)
    mock_ddddocr = MagicMock()
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = "AB1C"   # letters — invalid
    mock_ddddocr.DdddOcr.return_value = mock_ocr

    mock_response = MagicMock()
    mock_response.text = "1234"

    with patch.dict(sys.modules, {"ddddocr": mock_ddddocr}), \
         patch("scrapers.vnpt._get_gemini_client") as mock_gc:
        mock_gc.return_value.models.generate_content.return_value = mock_response
        result = _solve_vnpt_captcha(img_path)

    assert result == "1234"
    mock_gc.return_value.models.generate_content.assert_called_once()


def test_solve_captcha_falls_back_to_gemini_when_ddddocr_raises(tmp_path):
    img_path = _make_png(tmp_path)
    mock_ddddocr = MagicMock()
    mock_ddddocr.DdddOcr.side_effect = RuntimeError("model load failed")

    mock_response = MagicMock()
    mock_response.text = "9876"

    with patch.dict(sys.modules, {"ddddocr": mock_ddddocr}), \
         patch("scrapers.vnpt._get_gemini_client") as mock_gc:
        mock_gc.return_value.models.generate_content.return_value = mock_response
        result = _solve_vnpt_captcha(img_path)

    assert result == "9876"


def test_solve_captcha_uses_capsolver_when_key_set_and_ddddocr_fails(tmp_path):
    img_path = _make_png(tmp_path)
    mock_ddddocr = MagicMock()
    mock_ddddocr.DdddOcr.side_effect = RuntimeError("model load failed")

    with patch.dict(sys.modules, {"ddddocr": mock_ddddocr}), \
         patch.dict("os.environ", {"CAPSOLVER_API_KEY": "test-key"}), \
         patch("scrapers.vnpt._capsolver_solve", return_value="4321") as mock_cap, \
         patch("scrapers.vnpt._get_gemini_client") as mock_gc:
        result = _solve_vnpt_captcha(img_path)

    assert result == "4321"
    mock_cap.assert_called_once_with(img_path)
    mock_gc.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_solve_captcha_uses_ddddocr_when_returns_4_digits tests/test_scrapers.py::test_solve_captcha_falls_back_to_gemini_when_ddddocr_returns_non_digits tests/test_scrapers.py::test_solve_captcha_falls_back_to_gemini_when_ddddocr_raises tests/test_scrapers.py::test_solve_captcha_uses_capsolver_when_key_set_and_ddddocr_fails -v
```

Expected: FAIL (current `_solve_vnpt_captcha` has no ddddocr / Capsolver logic).

- [ ] **Step 3: Add `_capsolver_solve()` module-level helper to `scrapers/vnpt.py`**

Add this function after `_classify_bytes` (around line 274), before `_solve_vnpt_captcha`:

```python
def _capsolver_solve(image_path: str) -> str | None:
    """Submit captcha image to Capsolver API; return 4-digit string or None."""
    import base64
    import time
    import requests as _requests

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    api_key = os.environ["CAPSOLVER_API_KEY"]
    create_resp = _requests.post(
        "https://api.capsolver.com/createTask",
        json={"clientKey": api_key, "task": {"type": "ImageToTextTask", "body": b64}},
        timeout=15,
    ).json()
    task_id = create_resp.get("taskId")
    if not task_id:
        logger.debug("VNPT: Capsolver createTask returned no taskId: %s", create_resp)
        return None

    for _ in range(10):
        time.sleep(1)
        result_resp = _requests.post(
            "https://api.capsolver.com/getTaskResult",
            json={"clientKey": api_key, "taskId": task_id},
            timeout=10,
        ).json()
        if result_resp.get("status") == "ready":
            return result_resp.get("solution", {}).get("text", "")

    logger.debug("VNPT: Capsolver timed out waiting for task %s", task_id)
    return None
```

- [ ] **Step 4: Refactor `_solve_vnpt_captcha()` into tiered pipeline**

Replace the current `_solve_vnpt_captcha` function (lines 276–299) with:

```python
def _solve_vnpt_captcha(image_path: str) -> str:
    """
    Tiered captcha solver: ddddocr on raw image → Capsolver (if key set) → Gemini with preprocessing.
    ddddocr receives the raw screenshot; Pillow preprocessing runs only for Gemini.
    """
    # Solver 1: ddddocr on raw screenshot bytes
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        with open(image_path, "rb") as f:
            raw_result = re.sub(r"\s+", "", ocr.classification(f.read()))
        if re.fullmatch(r"[0-9]{4}", raw_result):
            logger.info("VNPT: ddddocr captcha result = '%s'", raw_result)
            return raw_result
        logger.debug("VNPT: ddddocr returned non-4-digit '%s', trying next solver", raw_result)
    except Exception as exc:
        logger.debug("VNPT: ddddocr solver failed: %s", exc)

    # Solver 2: Capsolver (only when CAPSOLVER_API_KEY env var is set)
    if os.environ.get("CAPSOLVER_API_KEY"):
        try:
            cap_result = _capsolver_solve(image_path)
            if cap_result and re.fullmatch(r"[0-9]{4}", re.sub(r"\s+", "", cap_result)):
                result = re.sub(r"\s+", "", cap_result)
                logger.info("VNPT: Capsolver captcha result = '%s'", result)
                return result
            logger.debug("VNPT: Capsolver returned non-4-digit '%s', falling back to Gemini", cap_result)
        except Exception as exc:
            logger.debug("VNPT: Capsolver solver failed: %s", exc)

    # Solver 3: Gemini with Pillow preprocessing (existing logic)
    img = PIL.Image.open(image_path).convert("L")
    w, h = img.size
    img = img.resize((w * 4, h * 4), PIL.Image.LANCZOS)
    img = img.filter(PIL.ImageFilter.SHARPEN)
    img = PIL.ImageEnhance.Contrast(img).enhance(2.5)
    img = img.convert("RGB")

    response = _get_gemini_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "This is a VNPT Vietnam e-invoice portal captcha image showing exactly 4 distorted digits "
            "(digits 0–9 only, no letters). Carefully read each digit left-to-right. "
            "Return ONLY the 4-digit sequence with no spaces, punctuation, or explanation.",
            img,
        ],
    )
    raw = response.text.strip()
    logger.info("VNPT: Gemini raw captcha response = '%s'", raw)
    return re.sub(r"\s+", "", raw)
```

- [ ] **Step 5: Run new OCR pipeline tests**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_solve_captcha_uses_ddddocr_when_returns_4_digits tests/test_scrapers.py::test_solve_captcha_falls_back_to_gemini_when_ddddocr_returns_non_digits tests/test_scrapers.py::test_solve_captcha_falls_back_to_gemini_when_ddddocr_raises tests/test_scrapers.py::test_solve_captcha_uses_capsolver_when_key_set_and_ddddocr_fails -v
```

Expected: all 4 PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add scrapers/vnpt.py tests/test_scrapers.py
git commit -m "feat: tiered OCR pipeline in _solve_vnpt_captcha (ddddocr → Capsolver → Gemini)"
```

---

### Task 5: Pre-submission digit validation

**Files:**
- Modify: `scrapers/vnpt.py` (update retry loop in `scrape()`)
- Test: `tests/test_scrapers.py` (add 1 new test, update 1 existing test)

- [ ] **Step 1: Write failing test for invalid solution skipping submission**

Add at the end of `tests/test_scrapers.py`:

```python
# ── pre-submission validation tests ─────────────────────────────────────────

def test_vnpt_scrape_skips_submit_when_solution_is_not_4_digits():
    """Invalid solver output must refresh captcha and not call _enter_captcha/_submit."""
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="AB1C"), \
         patch.object(s, "_enter_captcha") as mock_enter, \
         patch.object(s, "_submit_and_wait_for_results") as mock_submit, \
         patch.object(s, "_refresh_captcha_image") as mock_refresh, \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()

    mock_enter.assert_not_called()
    mock_submit.assert_not_called()
    # refresh should have been called on first 2 failures (not last)
    assert mock_refresh.call_count == _MAX_CAPTCHA_RETRIES - 1
```

Also add at the top of the test file (if not present): `from scrapers.vnpt import _MAX_CAPTCHA_RETRIES`

Actually `_MAX_CAPTCHA_RETRIES` is module-private. Use the literal `2` (since `_MAX_CAPTCHA_RETRIES - 1 = 2`):

```python
    assert mock_refresh.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_vnpt_scrape_skips_submit_when_solution_is_not_4_digits -v
```

Expected: FAIL — current code raises `CaptchaRequiredException("VNPT: Gemini returned empty captcha solution")` which doesn't match "3 attempts", or calls `_enter_captcha` when it should not.

- [ ] **Step 3: Update `test_vnpt_scrape_raises_after_max_captcha_retries` to match new error message**

The current test expects `match="empty"`. After the validation change, returning `""` from the solver hits the unified validation guard (not 4 digits), loops 3 times via `continue`, and the `for...else` raises "captcha failed after 3 attempts". Update the match:

```python
def test_vnpt_scrape_raises_after_max_captcha_retries():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    page.locator.return_value.count.return_value = 0
    page.locator.return_value.first.is_visible.return_value = False

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value=""), \
         patch.object(s, "_refresh_captcha_image"), \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()
```

- [ ] **Step 4: Replace the retry loop in `scrape()` with unified validation + `for...else`**

In `scrapers/vnpt.py`, replace the `for attempt in range(_MAX_CAPTCHA_RETRIES):` block (and only that block, leaving the bypass block and the post-loop code untouched) with:

```python
        for attempt in range(_MAX_CAPTCHA_RETRIES):
            self._fill_lookup_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution or not re.fullmatch(r"[0-9]{4}", solution):
                logger.warning(
                    "VNPT: solver returned invalid solution '%s', refreshing captcha", solution
                )
                if attempt < _MAX_CAPTCHA_RETRIES - 1:
                    self._refresh_captcha_image()
                continue
            logger.info("VNPT attempt %d/%d: captcha='%s'", attempt + 1, _MAX_CAPTCHA_RETRIES, solution)
            self._enter_captcha(solution)

            if self._submit_and_wait_for_results():
                break

            if attempt < _MAX_CAPTCHA_RETRIES - 1:
                logger.warning(
                    "VNPT: results table absent after attempt %d, refreshing captcha", attempt + 1
                )
                self._refresh_captcha_image()
        else:
            raise CaptchaRequiredException(
                f"VNPT: captcha failed after {_MAX_CAPTCHA_RETRIES} attempts"
            )
```

The full updated `scrape()` after this change:

```python
    def scrape(self) -> ScrapedResult:
        self._setup_dialogs()
        self.page.goto(self.url, wait_until="networkidle")
        self._scroll()

        if self._probe_bypass():
            logger.info("VNPT: captcha bypass confirmed — skipping OCR loop")
            self._assert_invoice_found()
            xml_bytes, pdf_bytes = self._download_all_files()
            if xml_bytes is None and pdf_bytes is None:
                raise InvoiceNotFoundException(
                    f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
                )
            return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)

        for attempt in range(_MAX_CAPTCHA_RETRIES):
            self._fill_lookup_code()
            solution = self._screenshot_and_solve_captcha()
            if not solution or not re.fullmatch(r"[0-9]{4}", solution):
                logger.warning(
                    "VNPT: solver returned invalid solution '%s', refreshing captcha", solution
                )
                if attempt < _MAX_CAPTCHA_RETRIES - 1:
                    self._refresh_captcha_image()
                continue
            logger.info("VNPT attempt %d/%d: captcha='%s'", attempt + 1, _MAX_CAPTCHA_RETRIES, solution)
            self._enter_captcha(solution)

            if self._submit_and_wait_for_results():
                break

            if attempt < _MAX_CAPTCHA_RETRIES - 1:
                logger.warning(
                    "VNPT: results table absent after attempt %d, refreshing captcha", attempt + 1
                )
                self._refresh_captcha_image()
        else:
            raise CaptchaRequiredException(
                f"VNPT: captcha failed after {_MAX_CAPTCHA_RETRIES} attempts"
            )

        self._assert_invoice_found()

        xml_bytes, pdf_bytes = self._download_all_files()

        if xml_bytes is None and pdf_bytes is None:
            raise InvoiceNotFoundException(
                f"VNPT: no downloadable files found for lookup code '{self.lookup_code}'"
            )

        return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
```

- [ ] **Step 5: Run new validation test**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py::test_vnpt_scrape_skips_submit_when_solution_is_not_4_digits -v
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd /home/ai/rvc-invoices-bot && pytest tests/test_scrapers.py -v
```

Expected: all tests pass. Verify count is at least 33 (27 existing + 6 new).

- [ ] **Step 7: Commit**

```bash
cd /home/ai/rvc-invoices-bot
git add scrapers/vnpt.py tests/test_scrapers.py
git commit -m "feat: pre-submission digit validation in VnptScraper.scrape()"
```
