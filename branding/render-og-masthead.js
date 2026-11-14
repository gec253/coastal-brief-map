#!/usr/bin/env node
/* Render branding/og-masthead.jpg (1200×630) from og-masthead.html.
 *
 *   node branding/render-og-masthead.js
 *
 * Uses the SIL OFL Fraunces and Source Sans 3 files in /fonts, and the
 * public-domain NOAA Chart 11545 texture in masthead-chart.webp. Requires
 * Chrome and puppeteer-core (override with CHROME and PUPPETEER).
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const puppeteer = require(process.env.PUPPETEER || "/tmp/cb-shot/node_modules/puppeteer-core");
const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
const ROOT = path.resolve(__dirname);
const SRC = path.join(ROOT, "og-masthead.html");
const TMP2X = path.join(ROOT, "og-masthead@2x.png");
const OUT = path.join(ROOT, "og-masthead.jpg");

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 2 });
  await page.goto("file://" + SRC, { waitUntil: "networkidle0", timeout: 30000 });
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await new Promise((r) => setTimeout(r, 400));
  const el = await page.$("#og-card");
  const buf = await el.screenshot({ type: "png" });
  await browser.close();
  fs.writeFileSync(TMP2X, buf);

  const py = `
from pathlib import Path
from PIL import Image
src = Path(${JSON.stringify(TMP2X)})
out = Path(${JSON.stringify(OUT)})
im = Image.open(src).convert("RGB").resize((1200, 630), Image.Resampling.LANCZOS)
im.save(out, "JPEG", quality=90, optimize=True, subsampling=0)
print(out, out.stat().st_size, im.size)
src.unlink()
`;
  const r = spawnSync("python3", ["-c", py], { encoding: "utf8" });
  if (r.status !== 0) {
    console.error(r.stderr);
    process.exit(r.status || 1);
  }
  console.log(r.stdout.trim());
})().catch((e) => { console.error(e); process.exit(1); });
