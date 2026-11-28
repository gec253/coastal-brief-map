"""Guards for the official Ramp Finder refresh workflow (Ed t552u).

These tests do not loosen any existing functional, data-integrity, security
or performance assertion. They cover the workflow's permission surface, the
notice-fingerprint checker, and that status/coordinate diffs are reported.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ramps-refresh.yml"


class WorkflowFile(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_permissions_are_minimal_and_job_scoped(self):
        self.assertRegex(self.text, r"(?m)^permissions:\s*\{\}\s*$")
        # Weekly job may write a refresh branch, a PR, and an LKG issue.
        self.assertIn("contents: write", self.text)
        self.assertIn("pull-requests: write", self.text)
        self.assertIn("issues: write", self.text)
        # Daily job is read + issues only (no contents write).
        daily = self.text.split("daily-notices:")[1]
        self.assertIn("contents: read", daily)
        self.assertNotIn("contents: write", daily)
        self.assertNotIn("pull-requests: write", daily)

    def test_no_dangerous_triggers_or_secrets(self):
        self.assertNotIn("pull_request_target", self.text)
        self.assertNotIn("workflow_run", self.text)
        # The built-in GITHUB_TOKEN is the only secret reference allowed.
        others = set(__import__("re").findall(r"secrets\.([A-Z0-9_]+)", self.text)) - {"GITHUB_TOKEN"}
        self.assertEqual(others, set())
        self.assertIn("secrets.GITHUB_TOKEN", self.text)
        self.assertNotIn("gh pr merge", self.text)
        self.assertNotIn("--auto", self.text)
        # The commit message may say "do not auto-merge"; that is not enabling it.
        self.assertNotIn("git push origin main", self.text)
        self.assertNotIn("HEAD:main", self.text)
        self.assertIn('git push -u origin "HEAD:refs/heads/${branch}"', self.text)
        self.assertIn("ramps-refresh/", self.text)

    def test_checkout_is_pinned_to_verified_v4_4_0_sha(self):
        # v4.4.0 lightweight tag -> 11d5960a326750d5838078e36cf38b85af677262
        self.assertEqual(self.text.count("actions/checkout@11d5960a326750d5838078e36cf38b85af677262"), 2)
        self.assertNotIn("actions/checkout@v4", self.text)
        self.assertNotIn("actions/checkout@v5", self.text)

    def test_concurrency_timeouts_and_issue_fallback(self):
        self.assertIn("group: ramps-refresh", self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("timeout-minutes: 15", self.text)
        self.assertIn("timeout-minutes: 10", self.text)
        self.assertIn("Could not open a pull request with GITHUB_TOKEN", self.text)
        self.assertIn("Allow GitHub Actions to create and approve pull requests", self.text)
        self.assertIn("ref: main", self.text)

    def test_untrusted_inputs_are_not_interpolated_into_shells(self):
        # inputs.job / event.inputs.job may appear in job if: conditions only.
        run_blocks = []
        lines = self.text.splitlines()
        in_run = False
        buf = []
        for line in lines:
            if line.strip().startswith("run: |") or line.strip().startswith("run: |-"):
                in_run = True
                buf = []
                continue
            if in_run:
                if line.startswith("      ") and not line.startswith("        "):
                    run_blocks.append("\n".join(buf))
                    in_run = False
                else:
                    buf.append(line)
        if in_run:
            run_blocks.append("\n".join(buf))
        joined = "\n".join(run_blocks)
        self.assertNotIn("${{ inputs.", joined)
        self.assertNotIn("${{ github.event.inputs", joined)
        self.assertNotIn("${{ github.event.pull_request", joined)
        self.assertNotIn("${{ github.event.issue", joined)


class NoticeFingerprints(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_notice_fingerprints", ROOT / "scripts" / "check_notice_fingerprints.py"
        )
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.tmp = Path(tempfile.mkdtemp())
        self.cwd = Path.cwd()
        os.chdir(self.tmp)
        self.store = self.tmp / "notice-fingerprints.json"
        self.pages = {
            "https://www.ncparks.gov/state-parks/jordan-lake-state-recreation-area": "jordan-lake",
            "https://www.ncparks.gov/state-parks/falls-lake-state-recreation-area": "falls-lake",
            "https://www.ncparks.gov/state-parks/kerr-lake-state-recreation-area": "kerr-lake",
        }
        self.html = {
            name: f"<html><body>Skip to main content {name} closed previous pause play rest</body></html>"
            for name in ("jordan-lake", "falls-lake", "kerr-lake")
        }

    def tearDown(self):
        os.chdir(self.cwd)
        import shutil
        shutil.rmtree(self.tmp)

    def _store(self, texts):
        pages = {}
        for url, name in self.pages.items():
            text = self.mod.banner_text(texts[name])
            pages[url] = {"name": name, "sha256": __import__("hashlib").sha256(text.encode()).hexdigest()}
        self.store.write_text(json.dumps({"pages": pages}))

    def _fetch_ok(self, url, timeout=45):
        name = self.pages[url]
        return self.html[name]

    def test_unchanged_exits_zero_and_writes_no_status_files(self):
        self._store(self.html)
        with mock.patch.object(self.mod, "CANDIDATES", [self.store]), \
                mock.patch.object(self.mod, "fetch", side_effect=self._fetch_ok):
            code = self.mod.main()
        self.assertEqual(code, 0)
        report = (self.tmp / "notice-check-report.md").read_text()
        self.assertIn("unchanged", report)
        self.assertNotIn("CHANGED", report)
        # never rewrites official statuses or the stored fingerprint file
        self.assertFalse((self.tmp / "official_notices.json").exists())

    def test_changed_banner_exits_two(self):
        self._store(self.html)
        changed = dict(self.html)
        changed["jordan-lake"] = "<html><body>Skip to main content jordan-lake NOW OPEN previous pause play rest</body></html>"
        def fetch(url, timeout=45):
            return changed[self.pages[url]]
        with mock.patch.object(self.mod, "CANDIDATES", [self.store]), \
                mock.patch.object(self.mod, "fetch", side_effect=fetch):
            code = self.mod.main()
        self.assertEqual(code, 2)
        report = (self.tmp / "notice-check-report.md").read_text()
        self.assertIn("jordan-lake: CHANGED", report)
        self.assertIn("unchanged", report)

    def test_fetch_failure_exits_two_and_does_not_raise(self):
        self._store(self.html)
        def fetch(url, timeout=45):
            if "falls-lake" in url:
                raise TimeoutError("timed out")
            return self.html[self.pages[url]]
        with mock.patch.object(self.mod, "CANDIDATES", [self.store]), \
                mock.patch.object(self.mod, "fetch", side_effect=fetch):
            code = self.mod.main()
        self.assertEqual(code, 2)
        report = (self.tmp / "notice-check-report.md").read_text()
        self.assertIn("falls-lake: FETCH FAILED", report)


class RefreshReportFlags(unittest.TestCase):
    """Status and coordinate field changes are listed in refresh-report.json."""

    def setUp(self):
        import importlib.util, shutil, tempfile
        from test_ramps_statewide_p1 import load_build
        self.b = load_build()
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("OUT", "SNAPSHOT", "CROSSWALK", "REPORT", "NOAA_CACHE"):
            src = getattr(self.b, name)
            dst = self.tmp / src.name
            if src.exists():
                shutil.copy(src, dst)
            setattr(self.b, name, dst)
        snap = json.loads(self.b.SNAPSHOT.read_text())
        self.fields = snap["fields"]
        self.attrs = list(snap["records"].values())
        self.edit = snap["editingInfo"]

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def save(self, attrs):
        p = self.tmp / "resp.json"
        p.write_text(json.dumps({"features": [{"attributes": a} for a in attrs],
                                 "fields": [{"name": f} for f in self.fields],
                                 "editingInfo": self.edit}))
        return str(p)

    def test_status_and_coordinate_changes_are_flagged(self):
        attrs = json.loads(json.dumps(self.attrs))
        attrs[0]["Site_Status"] = "CLOSED TEMPORARILY"
        attrs[1]["Latitude"] = (attrs[1]["Latitude"] or 0) + 0.01
        rc = self.b.main(["--from-file", self.save(attrs), "--checked", "2026-11-28"])
        self.assertEqual(rc, 0)
        rep = json.loads(self.b.REPORT.read_text())
        changed = rep["diff"]["changed"]
        self.assertIn("Site_Status", changed[attrs[0]["GlobalID"]]["fields"])
        self.assertIn("Latitude", changed[attrs[1]["GlobalID"]]["fields"])
        self.assertEqual(rep["diff"]["added"], [])
        self.assertEqual(rep["diff"]["removed"], [])


if __name__ == "__main__":
    unittest.main()
