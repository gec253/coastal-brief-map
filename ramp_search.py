"""Shared Ramp Finder search, used by the /ramps directory and the statewide map (Ed t559u, t560u).

One definition of what a search matches, in Python (server-side directory search) and in JavaScript
(`JS`, inlined into both pages). tests/test_ramp_search.py runs both on every record and query and
requires identical results.

Rules:
- A record is searched by its ramp name (display, official and alias), town, county ("Wake" and
  "Wake County" both work), waterbody and Ramp Finder area ("Wilmington · Wrightsville Beach",
  "Falls Lake"; the catch-all "Elsewhere: ..." areas are not searched). The Neuse segment notes are
  not searched, so "Goldsboro" finds launches in Goldsboro, not every launch whose note mentions it.
- Text is normalized: accents removed, lower case, anything that is not a letter or digit becomes
  a space.
- A record matches when the whole search appears in its text, or when every word typed appears in
  one of its fields (in any order: "Lake Jordan" and "Jordan Lake" both work). Words are not mixed
  across fields, so "Falls Lake" never matches a Lake Hickory ramp in the town of Granite Falls.
  An empty search matches everything.
- Search never depends on filters, regions, stored state or load order. Filters are applied
  separately and are always shown to the user.
"""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return _NON_ALNUM.sub(" ", s).strip()


def _clean(v) -> str:
    v = (v or "").strip() if isinstance(v, str) else ""
    return "" if v.lower() == "not stated" else v


def name_aliases(rec: dict) -> list[str]:
    """Official name and alias when they add words beyond the display name (stored as `al` in map-data.json)."""
    seen = {norm(rec.get("display_name"))}
    out = []
    for v in (_clean(rec.get("official_name")), _clean(rec.get("alias"))):
        if v and norm(v) not in seen:
            seen.add(norm(v)); out.append(v)
    return out


def parts(name, aliases, town, county, water, area) -> list[str]:
    county, area = _clean(county), _clean(area)
    if area.lower().startswith("elsewhere"):
        area = ""
    return [name or "", *aliases, _clean(town), county, (county + " county") if county else "", _clean(water), area]


def haystack(p: list[str]) -> str:
    """Normalized fields joined by " | " (a separator norm() can never produce inside a field)."""
    return " | ".join(x for x in (norm(v) for v in p) if x)


def record_haystack(rec: dict) -> str:
    """Haystack for a statewide.json record."""
    return haystack(parts(rec.get("display_name"), name_aliases(rec), rec.get("city"), rec.get("county"),
                          rec.get("body_of_water"), rec.get("area_label")))


def matches(hay: str, q) -> bool:
    t = norm(q)
    if not t or t in hay:
        return True
    words = t.split()
    return any(all(w in f for w in words) for f in hay.split(" | "))


# The same rules in JavaScript. Kept deliberately tiny; tests check parity with the Python above.
JS = r"""window.CBRampSearch=(function(){
function norm(s){return String(s==null?"":s).normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim();}
function clean(v){v=typeof v==="string"?v.trim():"";return v.toLowerCase()==="not stated"?"":v;}
function parts(name,aliases,town,county,water,area){county=clean(county);area=clean(area);if(area.toLowerCase().indexOf("elsewhere")===0)area="";return [name||""].concat(aliases||[],[clean(town),county,county?county+" county":"",clean(water),area]);}
function haystack(p){return p.map(norm).filter(Boolean).join(" | ");}
function matches(hay,q){var t=norm(q);if(!t||hay.indexOf(t)>-1)return true;var w=t.split(" ");return hay.split(" | ").some(function(f){return w.every(function(x){return f.indexOf(x)>-1;});});}
return {norm:norm,parts:parts,haystack:haystack,matches:matches};})();"""
