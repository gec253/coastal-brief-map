"""Offline checks for applying region.map.zoom on load and region switch."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.js").read_text(encoding="utf-8")
REGIONS = json.loads((ROOT / "data" / "regions.json").read_text(encoding="utf-8"))
SALT = [
    "crystal-coast",
    "hatteras",
    "wilmington",
    "nags-head",
    "emerald-isle",
    "topsail",
]


def _region(rid: str) -> dict:
    return next(r for r in REGIONS["regions"] if r["id"] == rid)


def _expected_zoom(configured: int | None, width: int) -> int:
    z = 8 if configured is None else configured
    return max(1, z - 1) if width <= 700 else z


class RegionMapZoomTests(unittest.TestCase):
    def test_helper_is_used_instead_of_keeping_current_zoom(self) -> None:
        self.assertIn("function regionMapZoom(", APP)
        self.assertIn("regionMapZoom(region)", APP)
        self.assertIn("regionMapZoom(d.region)", APP)
        self.assertIn("regionMapCenter(region)", APP)
        self.assertNotIn(
            "map.setView(d.region.map.center, map.getZoom()",
            APP,
        )
        self.assertIn("!!nextId && prevId !== nextId", APP)
        self.assertIn("cb-boot-conditions", APP)

    def test_public_salt_region_zooms(self) -> None:
        configured = {r["id"]: r["map"]["zoom"] for r in REGIONS["regions"] if r["id"] in SALT}
        self.assertEqual(configured["crystal-coast"], 8)
        self.assertEqual(configured["hatteras"], 8)
        self.assertEqual(configured["wilmington"], 10)
        self.assertEqual(configured["nags-head"], 10)
        self.assertEqual(configured["emerald-isle"], 11)
        self.assertEqual(configured["topsail"], 10)
        cases = []
        for rid, z in configured.items():
            cases.append((rid, z, 1280, z))
            cases.append((rid, z, 700, z - 1))
            cases.append((rid, z, 390, z - 1))
        for rid, z, width, want in cases:
            self.assertEqual(_expected_zoom(z, width), want, f"{rid} at {width}px")

    def test_region_map_zoom_helper_in_node(self) -> None:
        start = APP.index("function regionMapZoom(")
        end = APP.index("function regionMapCenter(")
        helper = APP[start:end].strip()
        cases = [
            ({"map": {"zoom": 10}}, 1280, 10),
            ({"map": {"zoom": 10}}, 700, 9),
            ({"map": {"zoom": 10}}, 390, 9),
            ({"map": {"zoom": 8}}, 1280, 8),
            ({"map": {"zoom": 8}}, 390, 7),
            ({"map": {"zoom": 11}}, 390, 10),
            ({"map": {"zoom": 11}}, 1280, 11),
            ({}, 1280, 8),
            (None, 390, 7),
        ]
        for rid in SALT:
            z = _region(rid)["map"]["zoom"]
            cases.append(({"map": {"zoom": z}}, 1280, _expected_zoom(z, 1280)))
            cases.append(({"map": {"zoom": z}}, 390, _expected_zoom(z, 390)))
        script = "\n".join(
            [
                "const ZOOM = 8;",
                helper,
                "const cases = " + json.dumps(cases) + ";",
                "for (const [region, width, want] of cases) {",
                "  const got = regionMapZoom(region, width);",
                "  if (got !== want) {",
                "    console.error('fail', JSON.stringify({region, width, want, got}));",
                "    process.exit(1);",
                "  }",
                "}",
                "console.log('ok', cases.length);",
            ]
        )
        proc = subprocess.run(
            ["node", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("ok", proc.stdout)

    def test_preview_salt_region_zooms(self) -> None:
        self.assertEqual(_region("carolina-kure")["map"]["zoom"], 11)
        self.assertEqual(_region("corolla-duck")["map"]["zoom"], 10)
        self.assertEqual(_expected_zoom(11, 1280), 11)
        self.assertEqual(_expected_zoom(11, 390), 10)
        self.assertEqual(_expected_zoom(10, 1280), 10)
        self.assertEqual(_expected_zoom(10, 390), 9)


if __name__ == "__main__":
    unittest.main()
