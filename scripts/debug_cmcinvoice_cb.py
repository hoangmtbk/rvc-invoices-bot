#!/usr/bin/env python3
"""Find reCAPTCHA callback in CMC invoice page."""
import sys, os, time
sys.path.insert(0, "/app")
from dotenv import load_dotenv; load_dotenv("/app/.env")

from playwright.sync_api import sync_playwright
from scrapers.browser import build_stealth_context

with sync_playwright() as pw:
    browser, context = build_stealth_context(pw)
    page = context.new_page()
    page.goto("https://cinvoice.cmctelecom.vn/", wait_until="networkidle")
    time.sleep(3)

    # Find all function properties in clients[0]
    result = page.evaluate("""() => {
        const cfg = window.___grecaptcha_cfg;
        if (!cfg || !cfg.clients) return ['no clients'];
        const c = cfg.clients[0];
        if (!c) return ['no client 0'];
        const funcs = [];
        function scan(obj, path, depth) {
            if (depth > 5) return;
            if (!obj || typeof obj !== 'object') return;
            for (const k of Object.keys(obj)) {
                const v = obj[k];
                if (typeof v === 'function') {
                    funcs.push('FUNC ' + path + '.' + k + ' len=' + v.length + ' name=' + (v.name||'?') + ' src=' + v.toString().substring(0, 100));
                } else if (v && typeof v === 'object') {
                    scan(v, path + '.' + k, depth + 1);
                }
            }
        }
        scan(c, 'clients[0]', 0);
        return funcs;
    }""")
    for line in result:
        print(line)

    # Also check onloadcallback
    result2 = page.evaluate("""() => {
        return typeof window.onloadcallback + ' :: ' + (typeof window.onloadcallback === 'function' ? window.onloadcallback.toString().substring(0,300) : 'n/a');
    }""")
    print("onloadcallback:", result2)

    browser.close()
