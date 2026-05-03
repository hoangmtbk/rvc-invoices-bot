# VNPT Captcha Accuracy Improvement — Design Spec

**Date:** 2026-05-02
**Scope:** `scrapers/vnpt.py`, `requirements.txt`

---

## Problem

`VnptScraper` uses Gemini 2.5 Flash to OCR the VNPT portal's 4-digit distorted captcha. Failure rate is approximately 1 in 5 invoices. Root cause: Gemini is a general-purpose vision model, not optimised for distorted synthetic digits — it confuses visually similar pairs (0↔8, 1↔7, 3↔8, 5↔6).

---

## Goal

Raise first-pass captcha success rate from ~80% to ≥95% with minimal added complexity and zero mandatory external dependencies.

---

## Architecture

Three layered strategies applied in order of cost/complexity:

1. **Bypass probe** — one-shot test at scrape start; eliminates OCR entirely if server doesn't validate captcha server-side.
2. **Tiered OCR pipeline** — replaces single Gemini call with ddddocr (primary) → optional Capsolver → Gemini (fallback).
3. **Pre-submission digit validation** — reject provably-wrong solver output before wasting a form submission.

The retry loop in `scrape()` is unchanged. All changes are internal to the solver layer.

---

## Section 1: Bypass Probe

`VnptScraper.scrape()` gains a `_probe_bypass() -> bool` method called **once** before the captcha retry loop.

**Behaviour:**
- Fills the lookup code field (calls `_fill_lookup_code()`).
- Types `"0000"` into the captcha input (calls `_enter_captcha("0000")`).
- Submits and checks results (calls `_submit_and_wait_for_results()`).
- Returns `True` if the results table appears → server is not validating captcha.
- Returns `False` if jQuery captcha validation error fires → server validates; fall through to OCR loop.

**Integration into `scrape()`:**
```python
if self._probe_bypass():
    logger.info("VNPT: captcha bypass confirmed — skipping OCR loop")
    self._assert_invoice_found()
    xml_bytes, pdf_bytes = self._download_all_files()
    ...
    return ScrapedResult(xml_bytes=xml_bytes, pdf_bytes=pdf_bytes)
# else: fall through to existing captcha retry loop
```

`_probe_bypass` runs before the retry loop. If bypass fails, the loop still runs its full `_MAX_CAPTCHA_RETRIES` attempts — no attempts are consumed.

---

## Section 2: Tiered OCR Pipeline

`_solve_vnpt_captcha(image_path: str) -> str` is refactored into a pipeline of three solvers tried in order until one returns a valid 4-digit string.

### Solver 1 — ddddocr (primary, offline)

```python
import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)
with open(image_path, "rb") as f:
    result = ocr.classification(f.read())
```

- `ddddocr` is a deep-learning OCR library trained specifically on distorted synthetic captchas (popular in the Chinese/Vietnamese automation space).
- Returns a string; if it matches `^[0-9]{4}$`, use it and return.
- If it returns letters, wrong length, or raises, fall through to next solver.
- `ddddocr` added to `requirements.txt`.
- ddddocr receives the **raw captcha screenshot** (before any Pillow processing) — it has its own internal preprocessing tuned for synthetic captchas and performs worse on over-processed images. The Pillow pipeline (greyscale, 4× upscale, sharpen, contrast) is applied only when falling back to Gemini.

### Solver 2 — Capsolver (optional, external)

Activated only when env var `CAPSOLVER_API_KEY` is set.

```python
import httpx, base64, time

def _capsolver(image_path: str) -> str | None:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        "clientKey": os.environ["CAPSOLVER_API_KEY"],
        "task": {"type": "ImageToTextTask", "body": b64},
    }
    resp = httpx.post("https://api.capsolver.com/createTask", json=payload, timeout=15).json()
    task_id = resp.get("taskId")
    if not task_id:
        return None
    for _ in range(10):
        time.sleep(1)
        r = httpx.post("https://api.capsolver.com/getTaskResult",
                       json={"clientKey": os.environ["CAPSOLVER_API_KEY"], "taskId": task_id},
                       timeout=10).json()
        if r.get("status") == "ready":
            return r.get("solution", {}).get("text", "")
    return None
```

- Only imported/called when `CAPSOLVER_API_KEY` is set — no mandatory dependency.
- Result validated as `^[0-9]{4}$` before use.
- `httpx` already in requirements; no new mandatory dependency.

### Solver 3 — Gemini (fallback, existing)

Existing `_get_gemini_client().models.generate_content(...)` call, unchanged. Acts as final fallback when ddddocr and Capsolver both fail or are unavailable.

### Pipeline function signature (unchanged externally):

```python
def _solve_vnpt_captcha(image_path: str) -> str:
    # 1. preprocess image (existing Pillow code)
    # 2. try ddddocr → return if valid
    # 3. try Capsolver if CAPSOLVER_API_KEY set → return if valid
    # 4. fall back to Gemini → return result
```

---

## Section 3: Pre-Submission Digit Validation

After `_screenshot_and_solve_captcha()` returns a solution, validate before submitting:

```python
import re

solution = self._screenshot_and_solve_captcha()
if not solution or not re.fullmatch(r"[0-9]{4}", solution):
    logger.warning("VNPT: solver returned invalid solution '%s', refreshing captcha", solution)
    if attempt < _MAX_CAPTCHA_RETRIES - 1:
        self._refresh_captcha_image()
    continue  # skip submission, retry
```

- Rejects non-4-digit strings (letters, wrong length) before they reach `_enter_captcha`.
- Immediately refreshes the captcha image and retries without burning a form submission.
- The existing `CaptchaRequiredException("VNPT: Gemini returned empty captcha solution")` check at the top of the loop is replaced by this unified check.

---

## Files Changed

| File | Change |
|------|--------|
| `scrapers/vnpt.py` | Add `_probe_bypass()`, refactor `_solve_vnpt_captcha()` into tiered pipeline, add pre-submission validation |
| `requirements.txt` | Add `ddddocr` |

No other files change. `BaseInvoiceScraper`, `EasyInvoiceScraper`, `ViettelScraper`, `PetrolimexScraper` are unaffected.

---

## Testing

- Unit test `_probe_bypass` returns `True` when `_submit_and_wait_for_results` returns `True`.
- Unit test `_probe_bypass` returns `False` when captcha validation error fires.
- Unit test OCR pipeline: ddddocr valid → used; ddddocr invalid → Gemini fallback; Capsolver used when key set.
- Unit test pre-submission validation: non-4-digit solution → refresh called, submission skipped.
- All existing `test_vnpt_*` tests must continue to pass.

---

## Non-Goals

- Not changing the retry count (`_MAX_CAPTCHA_RETRIES = 3`).
- Not modifying any other scraper (EasyInvoice, Viettel, Petrolimex, MISA).
- Not training a custom model.
- Not changing the Capsolver polling loop to async.
