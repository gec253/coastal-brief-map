#!/usr/bin/env python3
"""Classify official NCWRC refresh diffs for the weekly review job (Ed t556u).

A run whose only changes are fetch timestamps (fetched_at, attempted_at,
fetched) is "timestamps_only": the workflow records a verification summary
and must not open an issue or pull request or push a review branch.

Real changes (additions, removals, status, coordinates, other fields,
schema/file changes) are "real" and still go to manual review.
"none" means the watched files are unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TIMESTAMP_KEYS = frozenset({"fetched_at", "attempted_at", "fetched"})
WATCHED = (
    "preview/ramp-finder/statewide.json",
    "preview/ramp-finder/ncwrc_snapshot.json",
    "preview/ramp-finder/refresh-report.json",
    "preview/ramp-finder/ncwrc_crosswalk.json",
    "preview/ramp-finder/noaa_tide_stations_nc.json",
)
REPORT_PATH = Path("preview/ramp-finder/refresh-report.json")


def strip_timestamps(obj):
    if isinstance(obj, dict):
        return {k: strip_timestamps(v) for k, v in obj.items() if k not in TIMESTAMP_KEYS}
    if isinstance(obj, list):
        return [strip_timestamps(v) for v in obj]
    return obj


def classify_file_contents(old: str | None, new: str | None) -> str:
    if old is None and new is None:
        return "none"
    if old is None or new is None:
        return "real"
    if old == new:
        return "none"
    try:
        old_obj = json.loads(old)
        new_obj = json.loads(new)
    except json.JSONDecodeError:
        return "real"
    if strip_timestamps(old_obj) == strip_timestamps(new_obj):
        return "timestamps_only"
    return "real"


def classify_pairs(pairs) -> str:
    kinds = [classify_file_contents(old, new) for old, new in pairs]
    if any(k == "real" for k in kinds):
        return "real"
    if any(k == "timestamps_only" for k in kinds):
        return "timestamps_only"
    return "none"


def git_show(path: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def load_pairs(root: Path | None = None) -> list[tuple[str, str | None, str | None]]:
    base = root or Path(".")
    rows = []
    for rel in WATCHED:
        old = git_show(rel)
        new_path = base / rel
        new = new_path.read_text() if new_path.is_file() else None
        rows.append((rel, old, new))
    return rows


def load_report(path: Path | None = None) -> dict:
    p = path or REPORT_PATH
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"error": "refresh-report.json was not valid JSON"}
    return data if isinstance(data, dict) else {"error": "refresh-report.json was not an object"}


def format_summary(kind: str, report: dict | None = None) -> str:
    report = report or {}
    diff = report.get("diff") or {}
    added = diff.get("added") or []
    removed = diff.get("removed") or []
    changed = diff.get("changed") or {}
    counts = report.get("counts") or {}
    total = counts.get("total")
    attempted = report.get("attempted_at") or (report.get("refresh") or {}).get("attempted_at")
    # statewide.json nests attempted_at under meta.refresh; the report file has it at top level.
    if not attempted:
        attempted = "(not recorded)"
    if kind == "timestamps_only":
        ticket = "No review branch, issue, or pull request opened (fetch timestamps only)."
    elif kind == "none":
        ticket = "No review branch, issue, or pull request opened (no file changes)."
    elif kind == "real":
        ticket = "Opening a review ticket (pull request, or an issue if PRs are not permitted)."
    else:
        ticket = f"Unexpected classification: {kind}"
    lines = [
        "## Official NCWRC refresh verification",
        "",
        f"- Classification: `{kind}`",
        f"- Inventory: {total if total is not None else '(unknown)'} sites; "
        f"{len(added)} added, {len(removed)} removed, {len(changed)} changed",
        f"- Attempted at: {attempted}",
        f"- {ticket}",
    ]
    return "\n".join(lines) + "\n"


def write_summary(text: str, summary_path: str | None = None) -> None:
    dest = summary_path or os.environ.get("GITHUB_STEP_SUMMARY")
    if not dest:
        return
    with open(dest, "a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Append a verification summary to GITHUB_STEP_SUMMARY (or --summary).",
    )
    parser.add_argument("--summary", default=None, help="Summary file path (tests / override).")
    parser.add_argument("--report", default=None, help="Path to refresh-report.json.")
    args = parser.parse_args(argv)
    pairs = [(old, new) for _, old, new in load_pairs()]
    kind = classify_pairs(pairs)
    report = load_report(Path(args.report) if args.report else REPORT_PATH)
    if args.write_summary:
        write_summary(format_summary(kind, report), args.summary)
    sys.stdout.write(kind + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
