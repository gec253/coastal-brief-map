"""Drive a Catch Wall page and assert #share-open opens the share dialog."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    url = sys.argv[1]
    want = sys.argv[2] if len(sys.argv) > 2 else "Share your catch"
    chrome = "/usr/bin/google-chrome"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chrome,
            args=["--headless=new", "--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(url, wait_until="networkidle", timeout=30000)
        btn = page.locator("#share-open")
        btn.wait_for(state="visible", timeout=8000)
        label = btn.inner_text().strip()
        btn.click()
        opened = page.evaluate(
            "() => { const d = document.getElementById('share-dlg'); return !!(d && d.open); }"
        )
        browser.close()
        if errors:
            print("pageerror: " + " | ".join(errors), file=sys.stderr)
            return 1
        if label.split("\n")[0].strip() != want:
            print("cta was %r" % label, file=sys.stderr)
            return 1
        if not opened:
            print("dialog did not open", file=sys.stderr)
            return 1
        print("playwright-share-ok")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
