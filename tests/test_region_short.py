"""Short form for long region names in the compact folio (fixture only; no live catalog changes)."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "long-regions.json"
NAV = ROOT / "region-nav.js"


class RegionShortName(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        script = r"""
const fs = require("fs");
const vm = require("vm");
const ctx = { window: {}, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), ctx);
const Nav = ctx.window.CoastalRegionNav;
const fix = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const rows = (fix.regions || []).concat(fix.existing || []);
const out = rows.map((r) => ({ id: r.id, short: Nav.shortName(r), full: Nav.fullName(r), expectShort: r.expectShort }));
process.stdout.write(JSON.stringify(out));
"""
        r = subprocess.run(
            ["node", "-e", script, str(NAV), str(FIXTURE)],
            check=True, capture_output=True, text=True,
        )
        cls.rows = json.loads(r.stdout)

    def test_fixture_is_not_in_the_live_catalog(self):
        catalog_js = NAV.read_text()
        for rec in self.fixture["regions"]:
            self.assertNotIn(rec["id"], catalog_js)
            self.assertNotIn(rec["name"], catalog_js)

    def test_short_form_from_fixture_and_existing_names(self):
        self.assertGreaterEqual(len(self.rows), 5)
        for row in self.rows:
            self.assertEqual(row["short"], row["expectShort"], row["id"])
            self.assertTrue(row["full"])
