#!/usr/bin/env python3
"""Fetch a specific email by UID and dump its subject, text body, HTML body,
lookup code extraction result, and attachment list.

Usage (from repo root):
    python scripts/fetch_email_uid.py 111
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from imap_tools import MailBox, AND, UidRange
from config import IMAP_SERVER, IMAP_PORT, IMAP_USER, IMAP_PASSWORD
from web_extraction_router import _extract_lookup_code, _extract_urls, _pick_best_url

TARGET_UID = sys.argv[1] if len(sys.argv) > 1 else "111"

print(f"Connecting to {IMAP_SERVER}:{IMAP_PORT} as {IMAP_USER} ...")
with MailBox(IMAP_SERVER, port=IMAP_PORT).login(IMAP_USER, IMAP_PASSWORD, initial_folder="INBOX") as mb:
    msgs = list(mb.fetch(AND(uid=UidRange(TARGET_UID, TARGET_UID)), mark_seen=False))

if not msgs:
    print(f"No email found with uid={TARGET_UID}")
    sys.exit(1)

msg = msgs[0]
print(f"\n{'='*60}")
print(f"UID:       {msg.uid}")
print(f"Subject:   {msg.subject}")
print(f"From:      {msg.from_}")
print(f"Date:      {msg.date}")
print(f"{'='*60}")

text = msg.text or ""
html = msg.html or ""
combined = text + " " + html

print(f"\n--- TEXT BODY ({len(text)} chars) ---")
print(text[:3000] or "(empty)")

print(f"\n--- EXTRACTED LOOKUP CODE ---")
code = _extract_lookup_code(combined)
print(f"  code = {code!r}")

print(f"\n--- EXTRACTED URLS ---")
urls = _extract_urls(combined)
for u in urls:
    print(f"  {u}")

print(f"\n--- BEST URL ---")
best = _pick_best_url(urls)
print(f"  {best!r}")

print(f"\n--- ATTACHMENTS ---")
for att in msg.attachments:
    print(f"  {att.filename!r}  ({len(att.payload)} bytes)")

print(f"\n--- HTML BODY (first 2000 chars) ---")
print(html[:2000] or "(empty)")
