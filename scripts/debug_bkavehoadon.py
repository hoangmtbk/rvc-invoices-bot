#!/usr/bin/env python3
"""Diagnostic v2: inspect BKAVeHoadon (ehoadon.vn) invoice portal — iframe flow."""
import sys, os, time
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context

LOOKUP_CODE = sys.argv[1] if len(sys.argv) > 1 else "OSDPQI3MAKB"
URL = f"https://tchd.ehoadon.vn/TCHD?MTC={LOOKUP_CODE}"
SHOT_DIR = "/tmp/bkavehoadon_debug"
os.makedirs(SHOT_DIR, exist_ok=True)

def shot(page, name):
    p = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=p, full_page=True)
    print(f"  [screenshot] {p}")

def dump(ctx, selector, label):
    locs = ctx.locator(selector)
    n = locs.count()
    print(f"\n  {label} ({selector}): {n} elements")
    for i in range(min(n, 20)):
        el = locs.nth(i)
        tag  = el.evaluate("e => e.tagName").lower()
        id_  = el.get_attribute("id") or ""
        cls  = el.get_attribute("class") or ""
        href = el.get_attribute("href") or ""
        onclick = el.get_attribute("onclick") or ""
        txt  = ""
        try: txt = el.inner_text()[:80]
        except: pass
        visible = el.is_visible()
        print(f"    [{i}] {tag} id={id_!r} class={cls!r} href={href!r} onclick={onclick!r} text={txt!r} visible={visible}")

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.on("dialog", lambda d: d.dismiss())

    print(f"\n1) {URL}")
    page.goto(URL, wait_until="networkidle")
    shot(page, "01_loaded")
    print(f"   title={page.title()!r}  url={page.url!r}")

    print("\n2) Waiting for #frameViewInvoice...")
    try:
        page.locator("#frameViewInvoice").wait_for(state="attached", timeout=15_000)
        src = page.locator("#frameViewInvoice").get_attribute("src") or ""
        print(f"   iframe src={src!r}")
    except Exception as e:
        print(f"   NOT found: {e}")

    shot(page, "02_after_wait")

    print("\n3) All frames:")
    for f in page.frames:
        print(f"   name={f.name!r}  url={f.url!r}")

    frame = page.frame(name="frameViewInvoice")
    if frame is None:
        for f in page.frames:
            if "Lookup" in f.url or "lookup" in f.url.lower():
                frame = f; break

    if not frame:
        print("Cannot find frame — stopping")
        shot(page, "03_no_frame")
        browser.close()
        sys.exit(1)

    print(f"\n4) Frame: name={frame.name!r}  url={frame.url!r}")
    try:
        frame.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        time.sleep(4)
    shot(page, "04_frame_loaded")

    body = frame.evaluate("() => document.body.innerText")
    print(f"\n5) iframe body (600 chars):\n{body[:600]}")

    dump(frame, "button", "iframe buttons")
    dump(frame, "a", "iframe links (first 20)")

    print("\n6) Download selectors in iframe:")
    for sel in [
        "button:has-text('Hóa đơn dạng XML')", "a:has-text('Hóa đơn dạng XML')",
        "button:has-text('Hóa đơn dạng PDF')", "a:has-text('Hóa đơn dạng PDF')",
        "button:has-text('XML')", "a:has-text('XML')",
        "button:has-text('PDF')", "a:has-text('PDF')",
        "button:has-text('Tải')", "a:has-text('Tải')",
        "a[href*='xml' i]", "a[href*='pdf' i]",
    ]:
        loc = frame.locator(sel)
        n = loc.count()
        if n:
            print(f"  {sel!r}: {n}")
            for i in range(n):
                el = loc.nth(i)
                try:
                    print(f"    [{i}] text={el.inner_text()!r} visible={el.is_visible()} "
                          f"onclick={el.get_attribute('onclick')!r} href={el.get_attribute('href')!r}")
                except Exception as ex:
                    print(f"    [{i}] err={ex}")

    # ── Step 6c: Hover #btnDownload to reveal hidden download links ──────
    btn_dl = frame.locator("#btnDownload")
    print(f"\n6c) #btnDownload: count={btn_dl.count()}"
          + (f" visible={btn_dl.first.is_visible()}" if btn_dl.count() else ""))
    if btn_dl.count() > 0:
        btn_dl.first.hover()
        time.sleep(0.8)
        shot(page, "06c_after_hover_btnDownload")
        print("    hovered — re-checking visibility:")
        for sel in ["#LinkDownXML", "#LinkDownPDF",
                    "a:has-text('Hóa đơn dạng XML')", "a:has-text('Hóa đơn dạng PDF')"]:
            loc = frame.locator(sel)
            if loc.count():
                print(f"    {sel!r}: visible={loc.first.is_visible()}")
    else:
        print("    #btnDownload not found — skipping hover")

    xml_loc = frame.locator("a:has-text('Hóa đơn dạng XML'), #LinkDownXML")
    if xml_loc.count() > 0 and xml_loc.first.is_visible():
        print("\n7) XML download attempt...")
        try:
            with page.expect_download(timeout=15_000) as dl:
                xml_loc.first.hover(); time.sleep(0.3); xml_loc.first.click()
            path = dl.value.path()
            data = open(path, "rb").read()
            print(f"   OK: filename={dl.value.suggested_filename!r} size={len(data)}B magic={data[:8]!r}")
            shot(page, "07_xml_ok")
        except Exception as e:
            print(f"   FAIL: {e}")
            shot(page, "07_xml_fail")
    else:
        print(f"\n7) 'Hóa đơn dạng XML' not visible (count={xml_loc.count()}) — trying force click")
        xml_force = frame.locator("#LinkDownXML")
        if xml_force.count() > 0:
            try:
                with page.expect_download(timeout=15_000) as dl:
                    xml_force.first.click(force=True)
                data = open(dl.value.path(), "rb").read()
                print(f"   force OK: {dl.value.suggested_filename!r} {len(data)}B magic={data[:8]!r}")
                shot(page, "07_xml_force_ok")
            except Exception as e:
                print(f"   force FAIL: {e}")
                shot(page, "07_xml_force_fail")

    pdf_loc = frame.locator("a:has-text('Hóa đơn dạng PDF'), #LinkDownPDF")
    if pdf_loc.count() > 0 and pdf_loc.first.is_visible():
        print("\n8) PDF download attempt...")
        try:
            with page.expect_download(timeout=15_000) as dl:
                pdf_loc.first.hover(); time.sleep(0.3); pdf_loc.first.click()
            path = dl.value.path()
            data = open(path, "rb").read()
            print(f"   OK: filename={dl.value.suggested_filename!r} size={len(data)}B magic={data[:8]!r}")
            shot(page, "08_pdf_ok")
        except Exception as e:
            print(f"   FAIL: {e}")
            shot(page, "08_pdf_fail")
    else:
        print(f"\n8) 'Hóa đơn dạng PDF' not visible (count={pdf_loc.count()}) — trying force click")
        pdf_force = frame.locator("#LinkDownPDF")
        if pdf_force.count() > 0:
            try:
                with page.expect_download(timeout=15_000) as dl:
                    pdf_force.first.click(force=True)
                data = open(dl.value.path(), "rb").read()
                print(f"   force OK: {dl.value.suggested_filename!r} {len(data)}B magic={data[:8]!r}")
                shot(page, "08_pdf_force_ok")
            except Exception as e:
                print(f"   force FAIL: {e}")
                shot(page, "08_pdf_force_fail")

    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}/")
