"""Ramp Finder Phase 2, step 1: the compact data file behind the statewide map.

Built only from preview/ramp-finder/statewide.json (the single source of truth), so the
map can never disagree with the /ramps directory. Every one of the records is carried,
including the sites with no verified map location. Status and restriction text are
copied in full, never shortened. Coordinates come only from official sources:
  exact   - the record's official coordinates (NCWRC, NC DEQ DCM or Carteret County feature services)
  approx  - an owner-published access-area GPS point (N.C. State Parks), not the ramp itself
  none    - address only; no pin
Written by scripts/build_ramp_map_data.py and by scripts/build_ramps_statewide.py after a
successful refresh. Served privately at /preview/ramps-statewide/map.json; public /ramps/map.json
exists only when PUBLIC_RAMP_MAP is on.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATEWIDE = ROOT / "preview" / "ramp-finder" / "statewide.json"
OUT = ROOT / "preview" / "ramp-finder" / "map-data.json"

TYPE_LABELS = {"trailer": "Trailer launch", "paddle": "Paddle / carry-in",
               "limited": "Limited access", "needs_review": "Needs review"}
STATUS_LABELS = {"listed_open": "Listed open", "temporarily_closed": "Temporarily closed",
                 "partially_open": "Partly open", "conflicting": "Status unclear",
                 "not_stated": "Status not stated"}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _stated(v) -> bool:
    s = str(v or "").strip().lower()
    return bool(s) and not s.startswith("not stated") and s not in ("<null>", "none", "unknown")


def fee_status(summary: str) -> str:
    s = (summary or "").strip().lower()
    if s.startswith("free"):
        return "free_stated"
    if "camping fees apply" in s:
        return "camping_only"
    if s.startswith("fee") or s.startswith("$"):
        return "fee_applies"
    return "not_stated"


def ada_features(r) -> list:
    out = []
    if str(r.get("ada_paved_walkway")).strip().lower() == "yes":
        out.append("ADA paved walkway")
    n = _int(r.get("trailer_parking_ada"))
    if n:
        out.append("ADA trailer parking (%d)" % n)
    n = _int(r.get("nontrailer_parking_ada"))
    if n:
        out.append("ADA car parking (%d)" % n)
    if str(r.get("ada_dock_handrails")).strip().lower() == "yes":
        out.append("ADA dock handrails")
    return out


def _coords(r):
    d = r.get("directions") or {}
    if d.get("mode") == "coordinates" and d.get("latitude") is not None and d.get("longitude") is not None:
        return d["latitude"], d["longitude"], "exact", r.get("coordinates_source") or ""
    oc = r.get("official_coordinates")
    if oc and oc.get("lat") is not None and oc.get("lon") is not None:
        return oc["lat"], oc["lon"], "approx", oc.get("source_name") or oc.get("label") or ""
    return None, None, "none", ""


def record(r) -> dict:
    la, lo, pr, cs = _coords(r)
    st = r["access_status"]
    ty = r["type_dimension"]
    rx = r.get("restriction_notes") or ""
    docks = (_int(r.get("fixed_docks")) or 0) + (_int(r.get("floating_docks")) or 0)
    return {
        "id": r["id"], "n": r["display_name"], "ci": r.get("city") or "", "co": r.get("county") or "",
        "w": r.get("body_of_water") or "", "a": r.get("area_label") or "",
        "la": la, "lo": lo, "pr": pr, "cs": cs,
        "ty": ty, "tyl": TYPE_LABELS[ty],
        "rx": rx if _stated(rx) else "",
        "st": st["code"], "stl": STATUS_LABELS[st["code"]], "stf": st.get("label") or "",
        "sd": st.get("detail") or "", "sa": str(st.get("as_of") or ""), "ss": st.get("source") or "",
        "ln": _int(r.get("lanes")), "tp": _int(r.get("trailer_parking")),
        "ada": ada_features(r), "rr": str(r.get("restrooms") or "").lower().startswith("yes"),
        "lt": str(r.get("lighting") or "").lower() == "yes", "dk": docks,
        "fee": fee_status((r.get("fees") or {}).get("summary") or ""), "fs": (r.get("fees") or {}).get("summary") or "",
        "ad": (r.get("directions") or {}).get("address") or "",
    }


def build(statewide: dict) -> dict:
    recs = [record(r) for r in statewide["records"]]
    recs.sort(key=lambda o: o["id"])
    meta = {
        "total": len(recs),
        "pins": sum(1 for o in recs if o["pr"] != "none"),
        "exact": sum(1 for o in recs if o["pr"] == "exact"),
        "approx": sum(1 for o in recs if o["pr"] == "approx"),
        "address_only": sum(1 for o in recs if o["pr"] == "none"),
        "checked": statewide["meta"].get("date_checked"),
    }
    return {"meta": meta, "records": recs}


def dumps(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def write(statewide: dict | None = None, out: Path = OUT) -> dict:
    sw = statewide if statewide is not None else json.loads(STATEWIDE.read_text())
    doc = build(sw)
    out.write_text(dumps(doc))
    return doc["meta"]
