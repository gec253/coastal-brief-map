#!/usr/bin/env python3
"""Compare official NC State Parks closure banners to stored fingerprints.

Prints a short report. Exit 0 if unchanged, 2 if a banner changed or a page
could not be fetched. Never rewrites official statuses. Used by the
Ramp Finder official-data refresh workflow (Ed t552u).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATES = [
    ROOT.parent / "preview" / "ramp-finder" / "notice-fingerprints.json",
    ROOT / "notice-fingerprints.json",
]

UA = "CoastalBrief-notice-check/1.0 (https://thecoastalbrief.com)"
PAGES = {
    "jordan-lake": "https://www.ncparks.gov/state-parks/jordan-lake-state-recreation-area",
    "falls-lake": "https://www.ncparks.gov/state-parks/falls-lake-state-recreation-area",
    "kerr-lake": "https://www.ncparks.gov/state-parks/kerr-lake-state-recreation-area",
}


def banner_text(raw: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"\s+", " ", s)
    low = s.lower()
    a = low.find("skip to main content")
    b = low.find("previous pause play")
    chunk = s[a:b] if a >= 0 and b > a else s[:1500]
    return chunk.strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def main() -> int:
    store = next((p for p in CANDIDATES if p.is_file()), None)
    known = json.loads(store.read_text()) if store else {"pages": {}}
    by_url = known.get("pages") or {}
    changed, errors, report = [], [], []
    for name, url in PAGES.items():
        try:
            text = banner_text(fetch(url))
            sha = hashlib.sha256(text.encode()).hexdigest()
        except Exception as exc:
            errors.append(f"{name}: fetch failed ({exc})")
            report.append(f"- {name}: FETCH FAILED — {exc}")
            continue
        prev = (by_url.get(url) or {}).get("sha256")
        if prev and prev != sha:
            changed.append(name)
            report.append(f"- {name}: CHANGED (was {prev[:12]}…, now {sha[:12]}…)\n  excerpt: {text[:280]}")
        elif not prev:
            changed.append(name)
            report.append(f"- {name}: no stored fingerprint yet. sha256={sha}\n  excerpt: {text[:280]}")
        else:
            report.append(f"- {name}: unchanged ({sha[:12]}…)")
    body = "Official closure-page fingerprint check\n\n" + "\n".join(report) + "\n"
    Path("notice-check-report.md").write_text(body)
    print(body)
    if errors or changed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
