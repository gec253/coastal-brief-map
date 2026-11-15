"""Official NWS zone names for private preview brief alert copy.

The visible alerts line and the Captain's Take use these names. Zone codes
stay in the sources panel (#mb-sources) and the #cb-reading-sources JSON.

Names are properties.name as returned by api.weather.gov on 15 Nov 2026
(America/New_York). Fetches were read-only GETs with User-Agent
TheCoastalBrief/1.0 (+https://thecoastalbrief.com; coastal conditions
site). Do not invent a name.

Coverage: every zone used by the eight preview briefs (wilmington,
nags-head, emerald-isle, topsail, carolina-kure, corolla-duck,
neuse-river, jordan-lake), plus Cape Fear's Harnett, Cumberland and
Bladen forecast and county zones.

Display rules
-------------
Counties: a bare county is an NWS county zone, or a public forecast
zone whose official name is a single token (for example "Wake"). When
two or more of those resolve in the list, they are grouped as
"{A, B and C} counties" (or "{A and B} counties"). A single county
stays "{Name} County". A forecast zone and a county zone that name
the same county are shown once. Qualified land zones keep their
official name unchanged (for example "West Carteret", "Coastal New
Hanover", "Northern Outer Banks", "Coastal Onslow").

Marine names stay official. The only normalization is casing and
spacing where NWS is inconsistent: standalone "NM" is written "nm".
"out to" and "out" are left as NWS published them; adding or removing
"to" would be rewording.

If every item is a bare county, keep the grouped form ("Wake,
Johnston and Wayne counties", or "Chatham County" for one). Otherwise
separate the items with semicolons, in first-seen order, one per
item. In that mixed case each bare county is its own item as
"{Name} County" (not a grouped "counties" clause). A name that
contains "and" (for example "Croatan and Roanoke Sounds") stays one
item. Grouped county lists still use no Oxford comma. Unknown codes
fall back to the code, never a guessed name.
"""
from __future__ import annotations

import re

# Fetched 15 Nov 2026 from the source URL in each entry.
ZONE_NAMES: dict[str, dict[str, str]] = {
    # Marine / coastal
    "AMZ158": {
        "name": "S of Cape Lookout NC to Surf City NC out to 20 NM",
        "type": "coastal",
        "source": "https://api.weather.gov/zones/marine/AMZ158",
        "fetched": "2026-11-15",
    },
    "AMZ250": {
        "name": "Coastal waters from Surf City to Cape Fear NC out 20 nm",
        "type": "coastal",
        "source": "https://api.weather.gov/zones/marine/AMZ250",
        "fetched": "2026-11-15",
    },
    "AMZ150": {
        "name": "S of Currituck Beach Light NC to Oregon Inlet NC out to 20 NM",
        "type": "coastal",
        "source": "https://api.weather.gov/zones/marine/AMZ150",
        "fetched": "2026-11-15",
    },
    "AMZ231": {
        "name": "Croatan and Roanoke Sounds",
        "type": "coastal",
        "source": "https://api.weather.gov/zones/marine/AMZ231",
        "fetched": "2026-11-15",
    },
    # Land forecast zones
    "NCZ195": {
        "name": "West Carteret",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ195",
        "fetched": "2026-11-15",
    },
    "NCZ108": {
        "name": "Coastal New Hanover",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ108",
        "fetched": "2026-11-15",
    },
    "NCZ203": {
        "name": "Northern Outer Banks",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ203",
        "fetched": "2026-11-15",
    },
    "NCZ102": {
        "name": "Eastern Currituck",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ102",
        "fetched": "2026-11-15",
    },
    "NCZ199": {
        "name": "Coastal Onslow",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ199",
        "fetched": "2026-11-15",
    },
    "NCZ106": {
        "name": "Coastal Pender",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ106",
        "fetched": "2026-11-15",
    },
    "NCZ041": {
        "name": "Wake",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ041",
        "fetched": "2026-11-15",
    },
    "NCZ042": {
        "name": "Johnston",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ042",
        "fetched": "2026-11-15",
    },
    "NCZ078": {
        "name": "Wayne",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ078",
        "fetched": "2026-11-15",
    },
    "NCZ040": {
        "name": "Chatham",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ040",
        "fetched": "2026-11-15",
    },
    "NCZ077": {
        "name": "Harnett",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ077",
        "fetched": "2026-11-15",
    },
    "NCZ088": {
        "name": "Cumberland",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ088",
        "fetched": "2026-11-15",
    },
    "NCZ096": {
        "name": "Bladen",
        "type": "public",
        "source": "https://api.weather.gov/zones/forecast/NCZ096",
        "fetched": "2026-11-15",
    },
    # County zones
    "NCC183": {
        "name": "Wake",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC183",
        "fetched": "2026-11-15",
    },
    "NCC101": {
        "name": "Johnston",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC101",
        "fetched": "2026-11-15",
    },
    "NCC191": {
        "name": "Wayne",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC191",
        "fetched": "2026-11-15",
    },
    "NCC037": {
        "name": "Chatham",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC037",
        "fetched": "2026-11-15",
    },
    "NCC085": {
        "name": "Harnett",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC085",
        "fetched": "2026-11-15",
    },
    "NCC051": {
        "name": "Cumberland",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC051",
        "fetched": "2026-11-15",
    },
    "NCC017": {
        "name": "Bladen",
        "type": "county",
        "source": "https://api.weather.gov/zones/county/NCC017",
        "fetched": "2026-11-15",
    },
}


def official_name(code: str) -> str | None:
    """Exact NWS properties.name, or None if the code is not in the map."""
    rec = ZONE_NAMES.get((code or "").strip().upper())
    return rec["name"] if rec else None


def normalize_marine_name(name: str) -> str:
    """Lowercase standalone NM (nautical miles). Leave 'out to' / 'out' as published."""
    return re.sub(r"\bNM\b", "nm", name or "")


def _is_bare_county(rec: dict) -> bool:
    """True for a county zone, or a public forecast zone named only as a county."""
    name = (rec.get("name") or "").strip()
    if rec.get("type") == "county":
        return True
    if rec.get("type") == "public" and " " not in name and "county" not in name.lower():
        return True
    return False


def _county_short(name: str) -> str:
    s = (name or "").strip()
    if s.lower().endswith(" county"):
        s = s[:-7].strip()
    return s


def join_names(items) -> str:
    """Plain-English list with no Oxford comma: 'A and B', 'A, B and C'."""
    names = [n for n in (items or []) if n]
    if not names:
        return "this area"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s and %s" % (names[0], names[1])
    return "%s and %s" % (", ".join(names[:-1]), names[-1])


def county_group(shorts) -> str:
    """One county is 'Chatham County'; two or more are 'Wake, Johnston and Wayne counties'."""
    names = [s for s in (shorts or []) if s]
    if not names:
        return ""
    if len(names) == 1:
        s = names[0]
        return s if s.lower().endswith("county") else s + " County"
    return join_names(names) + " counties"


def display_name(code: str) -> str:
    """Name shown for a single code. Unknown codes fall back to the code."""
    raw = (code or "").strip().upper()
    rec = ZONE_NAMES.get(raw)
    if not rec:
        return (code or "").strip() or raw
    if rec["type"] == "coastal":
        return normalize_marine_name(rec["name"])
    if _is_bare_county(rec):
        return county_group([_county_short(rec["name"])])
    return rec["name"]


def format_alert_areas(codes) -> str:
    """Official display names for a list of alert zones.

    If every item is a bare county, group them: 'Chatham County' or
    'Wake, Johnston and Wayne counties'. Otherwise join items with
    semicolons, keeping first-seen order; each bare county is
    '{Name} County'. Forecast and county codes for the same county
    are de-duplicated. Unknown codes stay as codes. Empty → 'this area'.
    """
    items: list[tuple[str, str]] = []
    seen_county: set[str] = set()
    seen_other: set[str] = set()
    all_county = True
    for raw in codes or []:
        code = (raw or "").strip()
        if not code:
            continue
        rec = ZONE_NAMES.get(code.upper())
        if rec and _is_bare_county(rec):
            short = _county_short(rec["name"])
            key = short.lower()
            if key in seen_county:
                continue
            seen_county.add(key)
            items.append(("county", short))
            continue
        name = display_name(code)
        key = name.lower()
        if key in seen_other:
            continue
        seen_other.add(key)
        items.append(("other", name))
        all_county = False
    if not items:
        return "this area"
    if all_county:
        return county_group([short for _kind, short in items])
    names = []
    for kind, val in items:
        names.append(county_group([val]) if kind == "county" else val)
    return "; ".join(names)
