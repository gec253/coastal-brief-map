"""Official NWS zone names for private preview brief alert copy.

The visible alerts line and the Captain's Take use these names. Zone codes
stay in the sources panel (#mb-sources) and the #cb-reading-sources JSON.

Names are properties.name exactly as returned by api.weather.gov on
15 Nov 2026 (America/New_York). Fetches were read-only GETs with
User-Agent TheCoastalBrief/1.0 (+https://thecoastalbrief.com; coastal
conditions site). Do not invent or tidy a name.

Coverage: every zone used by the six preview briefs (wilmington,
nags-head, emerald-isle, topsail, neuse-river, jordan-lake), plus Cape
Fear's Harnett, Cumberland and Bladen forecast and county zones.

Display rule, applied only when formatting a list: if the official name
does not already contain "County" and the zone is a county zone, or a
public forecast zone whose official name is a single token (for example
"Wake"), show "{name} County". Qualified forecast names such as
"West Carteret" and marine names are shown exactly. When a forecast
zone and a county zone normalize to the same county, the county is
listed once. Unknown codes fall back to the code, never a guessed name.
"""
from __future__ import annotations

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


def display_name(code: str) -> str:
    """Name shown in alert copy. Unknown codes fall back to the code."""
    raw = (code or "").strip().upper()
    rec = ZONE_NAMES.get(raw)
    if not rec:
        return (code or "").strip() or raw
    name = rec["name"]
    if "county" in name.lower():
        return name
    if rec["type"] == "county" or (rec["type"] == "public" and " " not in name):
        return name + " County"
    return name


def _norm_county(name: str) -> str:
    s = (name or "").strip().lower()
    if s.endswith(" county"):
        s = s[:-7].strip()
    return s


def format_alert_areas(codes) -> str:
    """Plain-English list of official display names.

    De-duplicates a forecast zone and a county zone that name the same
    county. Preserves first-seen order. Unknown codes are kept as codes.
    Returns 'this area' when the list is empty.
    """
    names = []
    seen = set()
    for raw in codes or []:
        code = (raw or "").strip()
        if not code:
            continue
        name = display_name(code)
        key = _norm_county(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    if not names:
        return "this area"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s and %s" % (names[0], names[1])
    return "%s, and %s" % (", ".join(names[:-1]), names[-1])
