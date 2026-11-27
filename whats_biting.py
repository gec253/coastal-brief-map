"""What's Biting? — private, cookie-gated fishing-report preview (Ed t401u).

Server-rendered HTML for /reports and /reports/<region>. No public nav, no sitemap
entry, no homepage changes. Catch descriptions from third parties are never
republished. Fisherman's Post is excluded.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import html
from xml.sax.saxutils import escape as esc

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "whats_biting.json"
CSS_PATH = ROOT / "preview" / "whats-biting" / "reports.css"
ET = ZoneInfo("America/New_York")

REGION_IDS = (
    "crystal-coast",
    "hatteras",
    "falls-lake",
    "jordan-lake",
    "neuse-river",
)

# Calendar-day freshness in America/New_York, measured from the source's own date.
FRESH_MAX = 3
RECENT_MAX = 7
AGING_MAX = 14
OUTLOOK_MAX = timedelta(hours=48)
# If an outlook names an observation time, hide it once those readings are this old.
OBS_STALE_AFTER = timedelta(hours=6)

# Paths this module owns. Used by tests to prove protected surfaces were not edited here.
OWNED_PATHS = (
    "whats_biting.py",
    "data/whats_biting.json",
    "preview/whats-biting/reports.css",
    "tests/test_whats_biting_preview.py",
)

# Public and brief/viewer files that must stay untouched by this work.
PROTECTED_PATHS = (
    "index.html",
    "homepage_boot.py",
    "showcase.js",
    "showcase.css",
    "showcase.py",
    "brief.py",
    "brief.css",
    "brief_preview.py",
    "brief_strings.py",
    "brief-link.js",
    "catch-wall.html",
    "catch-wall-public.js",
    "catch-wall-public.css",
    "catch_wall_public.py",
    "catch_wall_preview.py",
    "dashboard.js",
    "app.js",
    "wave_intro.py",
    "styles.css",
    "folio-chrome.css",
    "radar.html",
    "radar-viewer.js",
    "radar-player.js",
    "wind-lab.html",
    "wind-lab.js",
)


def now_et(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return now_et(value).date()
    return date.fromisoformat(str(value)[:10])


def parse_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return now_et(value)
    s = str(value).strip()
    if len(s) == 10:
        return datetime.fromisoformat(s).replace(tzinfo=ET)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return now_et(dt)


def age_days(as_of: date | None, now: datetime | None = None) -> int | None:
    """Whole calendar days between the source date and today's date in ET."""
    if as_of is None:
        return None
    return (now_et(now).date() - as_of).days


def freshness_label(as_of: date | None, now: datetime | None = None) -> str | None:
    """Return Fresh, Recent, or Aging, or None when the item is older than 14 days or has no date."""
    d = age_days(as_of, now)
    if d is None or d < 0:
        return None
    if d <= FRESH_MAX:
        return "Fresh"
    if d <= RECENT_MAX:
        return "Recent"
    if d <= AGING_MAX:
        return "Aging"
    return None


def is_archived(as_of: date | None, now: datetime | None = None) -> bool:
    """Confirmed items (and dated local-report links) hide after 14 days."""
    d = age_days(as_of, now)
    return d is not None and d > AGING_MAX


def outlook_visible(item: dict, now: datetime | None = None) -> bool:
    """Outlooks expire 48 hours after issuance, or sooner if their observations are stale."""
    current = now_et(now)
    issued = parse_datetime(item.get("as_of") or item.get("issued"))
    if issued is None:
        return False
    if current - issued > OUTLOOK_MAX:
        return False
    if item.get("observations_stale"):
        return False
    obs = parse_datetime(item.get("observations_as_of"))
    if obs is not None and current - obs > OBS_STALE_AFTER:
        return False
    return True


def load(path: Path | None = None) -> dict:
    p = path or DATA_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def css_bytes() -> bytes:
    return CSS_PATH.read_bytes()


def _notice_map(data: dict) -> dict:
    return dict(data.get("notices") or {})


def region_by_id(data: dict, region_id: str) -> dict | None:
    for r in data.get("regions") or []:
        if r.get("id") == region_id:
            return r
    return None


def visible_reports(region: dict, now: datetime | None = None) -> list[dict]:
    out = []
    for item in region.get("reports") or []:
        as_of = parse_date(item.get("as_of"))
        if is_archived(as_of, now):
            continue
        label = freshness_label(as_of, now)
        row = dict(item)
        row["as_of_date"] = as_of
        row["freshness"] = label
        out.append(row)
    out.sort(key=lambda r: r.get("as_of_date") or date.min, reverse=True)
    return out


def visible_confirmed(region: dict, now: datetime | None = None) -> list[dict]:
    out = []
    for item in region.get("confirmed") or []:
        as_of = parse_date(item.get("as_of"))
        if is_archived(as_of, now):
            continue
        row = dict(item)
        row["as_of_date"] = as_of
        row["freshness"] = freshness_label(as_of, now)
        out.append(row)
    out.sort(key=lambda r: r.get("as_of_date") or date.min, reverse=True)
    return out


def visible_outlooks(region: dict, now: datetime | None = None) -> list[dict]:
    out = []
    for item in region.get("outlooks") or []:
        if not outlook_visible(item, now):
            continue
        row = dict(item)
        row["as_of_dt"] = parse_datetime(item.get("as_of") or item.get("issued"))
        out.append(row)
    return out


def region_notices(data: dict, region: dict) -> list[dict]:
    catalog = _notice_map(data)
    out = []
    for key in region.get("notices") or []:
        n = catalog.get(key)
        if n:
            row = dict(n)
            row["id"] = key
            out.append(row)
    return out


def newest_report_date(reports: list[dict]) -> date | None:
    dates = [r.get("as_of_date") for r in reports if r.get("as_of_date")]
    return max(dates) if dates else None


def verified_species(confirmed: list[dict]) -> list[str]:
    seen, out = set(), []
    for item in confirmed:
        for sp in item.get("species") or []:
            name = str(sp).strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
    return out


def format_date(d: date | None) -> str:
    if d is None:
        return "Date not shown"
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def format_date_short(d: date | None) -> str:
    if d is None:
        return "Date not shown"
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")


def format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "Date not shown"
    local = now_et(dt)
    return local.strftime("%B ") + str(local.day) + local.strftime(", %Y, %-I:%M %p") + " ET"


# --------------------------------------------------------------------------- fixtures (clearly labeled, never the default view)

def freshness_fixture_region(now: datetime | None = None) -> dict:
    """Synthetic region used only with ?fixture=freshness. Every line is labeled as a test fixture."""
    today = now_et(now).date()

    def iso(offset: int) -> str:
        return (today - timedelta(days=offset)).isoformat()

    return {
        "id": "fixture-freshness",
        "name": "Test fixture",
        "short_name": "Freshness demonstration",
        "water_type": "saltwater",
        "scope": "TEST FIXTURE — not a real region and not real catches. For layout and freshness review only.",
        "is_fixture": True,
        "reports": [
            {"source_name": "TEST FIXTURE source (Fresh example)", "source_url": "/reports?fixture=freshness",
             "as_of": iso(1), "scope": "TEST FIXTURE area", "title": "TEST FIXTURE — Fresh local-report link"},
            {"source_name": "TEST FIXTURE source (Recent example)", "source_url": "/reports?fixture=freshness",
             "as_of": iso(5), "scope": "TEST FIXTURE area", "title": "TEST FIXTURE — Recent local-report link"},
            {"source_name": "TEST FIXTURE source (Aging example)", "source_url": "/reports?fixture=freshness",
             "as_of": iso(10), "scope": "TEST FIXTURE area", "title": "TEST FIXTURE — Aging local-report link"},
            {"source_name": "TEST FIXTURE source (archived, should not show)", "source_url": "/reports?fixture=freshness",
             "as_of": iso(16), "scope": "TEST FIXTURE area", "title": "TEST FIXTURE — should be hidden"},
        ],
        "confirmed": [
            {"source_name": "TEST FIXTURE confirmed", "as_of": iso(2), "scope": "TEST FIXTURE area",
             "species": ["TEST FIXTURE species"], "body": "TEST FIXTURE — not a real catch. Example confirmed card only."},
        ],
        "outlooks": [],
        "seasonal": [],
        "notices": [],
    }


def empty_fixture_region() -> dict:
    return {
        "id": "fixture-empty",
        "name": "Test fixture",
        "short_name": "Empty-state demonstration",
        "water_type": "freshwater",
        "scope": "TEST FIXTURE — not a real region. Shows the empty states only.",
        "is_fixture": True,
        "reports": [],
        "confirmed": [],
        "outlooks": [],
        "seasonal": [],
        "notices": [],
    }


# --------------------------------------------------------------------------- HTML

_THEME_BOOT = (
    '<script>(function(){try{var q=new URLSearchParams(location.search).get("theme");'
    'var t=q||localStorage.getItem("coastalBrief.theme");'
    'if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";'
    'document.documentElement.setAttribute("data-theme",t)}catch(e){}})();</script>'
)

_THEME_TOGGLE = """<script>
(function(){
  var btn=document.getElementById("theme-toggle");
  if(!btn) return;
  function cur(){return document.documentElement.getAttribute("data-theme")==="dark"?"dark":"light"}
  function sync(){
    var t=cur();
    btn.setAttribute("aria-pressed", t==="dark"?"true":"false");
    btn.setAttribute("aria-label", t==="dark"?"Switch to light mode":"Switch to dark mode");
    btn.textContent=t==="dark"?"Light mode":"Dark mode";
  }
  sync();
  btn.addEventListener("click", function(){
    var n=cur()==="dark"?"light":"dark";
    document.documentElement.setAttribute("data-theme", n);
    try{localStorage.setItem("coastalBrief.theme",n)}catch(e){}
    sync();
  });
})();
</script>"""


SITE_ORIGIN = "https://thecoastalbrief.com"


def _shell(title: str, body: str, fixture: bool = False, skip: str = "Skip to the reports", *, public: bool = False, canonical: str | None = None) -> str:
    css_text = css_bytes().decode("utf-8")
    robots = "index, follow" if public else "noindex, nofollow"
    canon = f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">\n' if (public and canonical) else ""
    if fixture:
        banner = '<p class="wb-banner">TEST FIXTURE — not real reports or catches</p>\n'
    elif public:
        banner = ""
    else:
        banner = '<p class="wb-banner">Private preview — not public, not indexed</p>\n'
    brand = "/" if public else "/reports"
    nav_label = "Site" if public else "Preview sections"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="{robots}">
{canon}<meta name="theme-color" content="#071C29">
<title>{esc(title)}</title>
<link rel="icon" href="/favicon.ico?v=20261121" sizes="48x48">
<link rel="icon" href="/branding/favicon.svg?v=20261121" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20261121" sizes="180x180">
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-italic-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<style>{css_text}</style>
{_THEME_BOOT}
</head>
<body class="wb-body{" is-fixture" if fixture else ""}">
<a class="skip" href="#main">{esc(skip)}</a>
{banner}<header class="wb-top">
  <div class="wb-top-row">
    <a class="wb-brand" href="{brand}">The Coastal Brief</a>
    <div class="wb-tools">
      <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to dark mode">Dark mode</button>
    </div>
  </div>
  <nav class="wb-nav" aria-label="{nav_label}">
    <a href="/reports" aria-current="page">What’s Biting?</a>
    <a href="/brief?region=crystal-coast">Morning Brief</a>
    <a href="/catch-wall">Catch Wall</a>
  </nav>
</header>
<main id="main" class="wb-main">
{body}
</main>
<p class="wb-sign">Know the Water. Live the Coast.</p>
{_THEME_TOGGLE}
</body>
</html>
"""


def _badge(label: str | None) -> str:
    if not label:
        return ""
    slug = label.lower()
    shown = {"Aging": "Older report"}.get(label, label)   # Ed t534u: same wording as the homepage
    return f'<span class="badge badge-{esc(slug)}">{esc(shown)}</span>'


def _ex_badge() -> str:
    return '<span class="badge badge-fixture">TEST FIXTURE — not a real catch</span>'


def _report_card(item: dict, fixture: bool = False) -> str:
    as_of = format_date(item.get("as_of_date") or parse_date(item.get("as_of")))
    url = item.get("source_url") or ""
    title = item.get("title") or "Local fishing report"
    source = item.get("source_name") or "Source"
    scope = item.get("scope") or ""
    fixture_bit = _ex_badge() if fixture else ""
    link = (
        f'<a class="wb-src" href="{esc(url)}" rel="noopener noreferrer">Open the source’s own report</a>'
        if url.startswith("http")
        else ""
    )
    return f"""<article class="card card-report">
  <div class="card-meta">{_badge(item.get("freshness"))}{fixture_bit}<time>{esc(as_of)}</time></div>
  <h3>{esc(title)}</h3>
  <p class="attr">Source: {esc(source)} · Scope: {esc(scope)}</p>
  {link}
</article>"""


def _confirmed_card(item: dict, fixture: bool = False) -> str:
    as_of = format_date(item.get("as_of_date") or parse_date(item.get("as_of")))
    species = item.get("species") or []
    chips = "".join(f'<span class="chip">{esc(s)}</span>' for s in species)
    fixture_bit = _ex_badge() if fixture else ""
    body = item.get("body") or ""
    source = item.get("source_name") or "Source"
    scope = item.get("scope") or ""
    return f"""<article class="card card-confirmed">
  <div class="card-meta">{_badge(item.get("freshness"))}{fixture_bit}<span class="badge badge-confirmed">Confirmed</span><time>{esc(as_of)}</time></div>
  <h3>Confirmed activity</h3>
  <p class="body">{esc(body)}</p>
  <p class="chips">{chips}</p>
  <p class="attr">Source: {esc(source)} · Scope: {esc(scope)}</p>
</article>"""


def _outlook_card(item: dict) -> str:
    issued = format_dt(item.get("as_of_dt") or parse_datetime(item.get("as_of")))
    title = item.get("title") or "Conditions-based outlook"
    body = item.get("body") or ""
    inputs = item.get("inputs") or "Existing Coastal Brief readings"
    return f"""<article class="card card-outlook">
  <div class="card-meta"><span class="badge badge-outlook">Outlook</span><time>{esc(issued)}</time></div>
  <h3>{esc(title)}</h3>
  <p class="body">{esc(body)}</p>
  <p class="attr">This is an outlook, not a confirmed catch. Inputs: {esc(inputs)}</p>
</article>"""


def _seasonal_card(item: dict) -> str:
    as_of = format_date(parse_date(item.get("as_of")))
    title = item.get("title") or "Seasonal pattern"
    body = item.get("body") or ""
    scope = item.get("scope") or ""
    return f"""<article class="card card-seasonal">
  <div class="card-meta"><span class="badge badge-seasonal">Seasonal</span><time>{esc(as_of)}</time></div>
  <h3>{esc(title)}</h3>
  <p class="body">{esc(body)}</p>
  <p class="attr">Not a catch report. Scope: {esc(scope)}</p>
</article>"""


def _notice_card(item: dict) -> str:
    as_of = parse_date(item.get("as_of"))
    label = item.get("as_of_label") or (format_date(as_of) if as_of else "Date not shown")
    url = item.get("source_url") or ""
    link = f'<a class="wb-src" href="{esc(url)}" rel="noopener noreferrer">Official page</a>' if url else ""
    kind = item.get("kind") or "official"
    return f"""<article class="card card-notice">
  <div class="card-meta"><span class="badge badge-official">Official</span><time>{esc(label)}</time></div>
  <h3>{esc(item.get("title") or "Official notice")}</h3>
  <p class="body">{esc(item.get("body") or "")}</p>
  <p class="attr">Source: {esc(item.get("source_name") or "Agency")} · Scope: {esc(item.get("scope") or "")} · {esc(kind)}</p>
  {link}
</article>"""


def _empty(kind: str, message: str) -> str:
    return f'<p class="empty" data-empty="{esc(kind)}">{esc(message)}</p>'


def _glance(region: dict, reports: list, confirmed: list) -> str:
    newest = newest_report_date(reports)
    species = verified_species(confirmed)
    if species:
        sp = ", ".join(species)
    else:
        sp = "None independently confirmed"
    newest_s = format_date(newest) if newest else "No dated local report"
    fresh = freshness_label(newest) if newest else None
    water = "Freshwater" if region.get("water_type") == "freshwater" else "Saltwater"
    return f"""<div class="glance" aria-label="Quick facts">
  <div class="g"><span class="gk">Water</span><span class="gv">{esc(water)}</span></div>
  <div class="g"><span class="gk">Newest report</span><span class="gv">{esc(newest_s)}</span> {_badge(fresh)}</div>
  <div class="g"><span class="gk">Verified species</span><span class="gv">{esc(sp)}</span></div>
</div>"""


def render_region(data: dict, region: dict, now: datetime | None = None, *, public: bool = False) -> str:
    fixture = bool(region.get("is_fixture"))
    reports = visible_reports(region, now)
    confirmed = visible_confirmed(region, now)
    outlooks = visible_outlooks(region, now)
    seasonal = list(region.get("seasonal") or [])
    notices = region_notices(data, region)
    checked = data.get("last_checked")
    checked_s = format_date(parse_date(checked)) if checked else ""

    report_html = (
        "".join(_report_card(r, fixture=fixture) for r in reports)
        if reports
        else _empty("reports", "No dated first-party local reports are on file for this region.")
    )
    if confirmed:
        confirmed_html = "".join(_confirmed_card(c, fixture=fixture) for c in confirmed)
    else:
        confirmed_html = _empty(
            "confirmed",
            "No independently confirmed catch observations for this region. "
            "Dated first-party links, when present, are the source’s own reports — not a Coastal Brief confirmation. "
            "There is no conditions-based outlook.",
        )
    outlook_block = (
        "<h2>Conditions-based outlook</h2>" + "".join(_outlook_card(o) for o in outlooks)
        if outlooks
        else ""
    )
    seasonal_html = "".join(_seasonal_card(s) for s in seasonal) if seasonal else ""
    notice_html = "".join(_notice_card(n) for n in notices) if notices else _empty("notices", "No official notices listed for this region.")

    fixture_head = (
        '<p class="fixture-kicker">TEST FIXTURE — example layout only. These dates and species are not real.</p>'
        if fixture
        else ""
    )
    last_checked = (
        f'<p class="checked">Official notices last checked {esc(checked_s)} · Eastern Time.</p>'
        if checked_s and not fixture
        else ""
    )

    body = f"""
<p class="kicker">What’s Biting?</p>
{fixture_head}
<h1>{esc(region.get("name") or "Region")}</h1>
<p class="sub">{esc(region.get("short_name") or "")}</p>
{_glance(region, reports, confirmed)}
<p class="scope">{esc(region.get("scope") or "")}</p>
{last_checked}

<h2>Latest local reports</h2>
<p class="lead">Dated first-party links. Catch descriptions are not republished.</p>
{report_html}

<h2>Confirmed activity</h2>
{confirmed_html}
{outlook_block}

{"" if fixture else _otw_section(region)}

<h2>Official notices</h2>
{notice_html}

{"<h2>Seasonal notes</h2>" + seasonal_html if seasonal_html else ""}
{"" if fixture else '<nav class="region-nav" aria-label="What’s Biting? regions">' + _region_nav(data, region.get("id")) + "</nav>"}
"""
    name = region.get("name") or "Region"
    title = f"{name} — What’s Biting?" if public else f"{name} — What’s Biting? (private preview)"
    rid = region.get("id") or ""
    canonical = f"{SITE_ORIGIN}/reports/{rid}" if rid and not region.get("is_fixture") else (f"{SITE_ORIGIN}/reports" if public else None)
    return _shell(title, body, fixture=fixture, public=public, canonical=canonical)


def _region_nav(data: dict, current: str | None) -> str:
    bits = ['<a href="/reports">All regions</a>']
    for r in data.get("regions") or []:
        rid = r.get("id")
        name = r.get("name") or rid
        here = ' aria-current="page"' if rid == current else ""
        bits.append(f'<a href="/reports/{esc(rid)}"{here}>{esc(name)}</a>')
    return "".join(bits)


def render_index(data: dict, now: datetime | None = None, *, public: bool = False) -> str:
    cards = []
    for r in data.get("regions") or []:
        reports = visible_reports(r, now)
        confirmed = visible_confirmed(r, now)
        newest = newest_report_date(reports)
        water = "Freshwater" if r.get("water_type") == "freshwater" else "Saltwater"
        if newest:
            status = f"Newest local report {format_date(newest)}"
            badge = _badge(freshness_label(newest, now))
        else:
            status = "No dated local reports"
            badge = ""
        species = verified_species(confirmed)
        sp = ", ".join(species) if species else "No verified species"
        cards.append(f"""<a class="index-card" href="/reports/{esc(r.get("id"))}">
  <span class="k">{esc(water)}</span>
  <strong>{esc(r.get("name") or "")}</strong>
  <span class="sub">{esc(r.get("short_name") or "")}</span>
  <span class="status">{esc(status)} {badge}</span>
  <span class="sp">{esc(sp)}</span>
</a>""")
    checked = format_date(parse_date(data.get("last_checked")))
    body = f"""
<p class="kicker">North Carolina fishing reports</p>
<h1>What’s Biting?</h1>
<p class="scope">Dated first-party links and official notices. Catch descriptions are not republished.{"" if public else " Private preview — not a public page."}</p>
<p class="checked">Sources last checked {esc(checked)} · Eastern Time.</p>
<div class="index-grid">
{''.join(cards)}
</div>
"""
    title = "What’s Biting?" if public else "What’s Biting? — private preview"
    return _shell(title, body, public=public, canonical=f"{SITE_ORIGIN}/reports")



def format_reviewed_line(article: dict) -> str:
    """Publication date is hidden until published_at is set at release time.

    No fallback label such as "pending approval" is shown. reviewed stays visible
    when present.
    """
    parts = []
    published_at = parse_date(article.get("published_at"))
    if published_at:
        parts.append(f"Published {format_date_short(published_at)}")
    reviewed = format_date_short(parse_date(article.get("reviewed")))
    if reviewed:
        parts.append(f"Reviewed {reviewed}")
    return " · ".join(parts)


def region_articles(region: dict | None) -> list[dict]:
    if not region:
        return []
    return list(region.get("articles") or [])


def article_by_slug(region: dict | None, slug: str) -> dict | None:
    for item in region_articles(region):
        if item.get("slug") == slug:
            return item
    return None


def _italic_markup(text: str) -> str:
    """Escape text, then turn matched *pairs* into <em>."""
    parts = (text or "").split("*")
    out = []
    for i, part in enumerate(parts):
        escaped = esc(part)
        out.append(f"<em>{escaped}</em>" if i % 2 else escaped)
    return "".join(out)


def _blocks_html(blocks: list | None) -> str:
    out = []
    for block in blocks or []:
        typ = block.get("type")
        if typ == "p":
            if block.get("parts"):
                bits = []
                for part in block.get("parts") or []:
                    chunk = esc(part.get("text") or "")
                    url = part.get("url") or ""
                    if url:
                        bits.append(
                            f'<a href="{esc(url)}" rel="noopener noreferrer">{chunk}</a>'
                        )
                    else:
                        bits.append(chunk)
                out.append(f"<p>{''.join(bits)}</p>")
            else:
                out.append(f"<p>{esc(block.get('text') or '')}</p>")
        elif typ == "ul":
            items = "".join(f"<li>{esc(item)}</li>" for item in (block.get("items") or []))
            out.append(f"<ul>{items}</ul>")
        elif typ == "ol":
            items = []
            for item in block.get("items") or []:
                if isinstance(item, dict):
                    label = esc(item.get("label") or "")
                    url = item.get("url") or ""
                    items.append(
                        f'<li>{label} <a href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a></li>'
                    )
                else:
                    items.append(f"<li>{esc(item)}</li>")
            out.append(f"<ol>{''.join(items)}</ol>")
    return "\n".join(out)


def _otw_card(region: dict, article: dict) -> str:
    rid = region.get("id") or ""
    slug = article.get("slug") or ""
    href = f"/reports/{esc(rid)}/{esc(slug)}"
    headline = article.get("headline") or ""
    dek = article.get("dek") or ""
    dates = format_reviewed_line(article)
    return f"""<a class="otw-card" href="{href}">
  <p class="kicker">On the Water</p>
  <h3>{esc(headline)}</h3>
  <p class="dek">{esc(dek)}</p>
  <p class="dates">{esc(dates)}</p>
</a>"""


def _otw_section(region: dict) -> str:
    articles = region_articles(region)
    if not articles:
        return ""
    cards = "".join(_otw_card(region, article) for article in articles)
    return f"""<section class="otw" aria-labelledby="otw-heading">
<h2 id="otw-heading">On the Water</h2>
<p class="lead">Background and science. These are not dated fishing reports.</p>
{cards}
</section>
"""


def _sources_html(sources: list | None) -> str:
    items = []
    for src in sources or []:
        cite = _italic_markup(src.get("cite") or "")
        links = []
        for url in src.get("urls") or []:
            links.append(f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>')
        joined = (" · ").join(links)
        space = " " if joined else ""
        items.append(f"<li>{cite}{space}{joined}</li>")
    return f'<ol class="sources">{"".join(items)}</ol>'


def render_article(data: dict, region: dict, article: dict, *, public: bool = False) -> str:
    rid = region.get("id") or ""
    rname = region.get("name") or rid
    headline = article.get("headline") or "On the Water"
    dek = article.get("dek") or ""
    dates = format_reviewed_line(article)
    sections = []
    for section in article.get("sections") or []:
        heading = section.get("heading") or ""
        sections.append(f"<h2>{esc(heading)}</h2>\n{_blocks_html(section.get('blocks'))}")
    body_sections = "\n".join(sections)
    rules = article.get("rules") or {}
    rules_html = f"""<aside class="rules" aria-labelledby="rules-heading">
<h2 id="rules-heading">Rules to check</h2>
<p class="rules-kicker">{esc(rules.get("kicker") or "")}</p>
<p>{esc(rules.get("intro") or "")}</p>
{_blocks_html(rules.get("blocks"))}
</aside>
"""
    fact = article.get("fact_types") or ""
    fact_html = f'<p class="fact-types">{esc(fact)}</p>' if fact else ""
    body = f"""
<p class="crumb"><a href="/reports">What’s Biting?</a> / <a href="/reports/{esc(rid)}">{esc(rname)}</a></p>
<p class="kicker">On the Water</p>
<h1>{esc(headline)}</h1>
<p class="article-dek">{esc(dek)}</p>
{f'<p class="article-meta">{esc(dates)}</p>' if dates else ""}
<div class="article-body">
<p>{esc(article.get("lead") or "")}</p>
{body_sections}
</div>
{rules_html}
<h2>Sources</h2>
{_sources_html(article.get("sources"))}
{fact_html}
<nav class="region-nav" aria-label="What’s Biting? regions">{_region_nav(data, rid)}</nav>
"""
    title = f"{headline} — What’s Biting?" if public else f"{headline} — What’s Biting? (private preview)"
    slug = article.get("slug") or ""
    canonical = f"{SITE_ORIGIN}/reports/{rid}/{slug}" if rid and slug else None
    return _shell(title, body, skip="Skip to the article", public=public, canonical=canonical)


def resolve_request(path: str, query: dict[str, list[str]] | None = None, now: datetime | None = None, data: dict | None = None, *, public: bool = False, allow_fixtures: bool = False) -> tuple[int, str, str]:
    """Return (status, content_type, body) for a /reports path.

    Fixtures are served only when allow_fixtures is true, which the server
    grants solely on cookie-gated /preview/reports paths (and tests). Public
    /reports routes never honor ?fixture=.
    """
    data = data or load()
    q = query or {}
    fixture = (q.get("fixture") or [""])[0].strip().lower() if allow_fixtures else ""
    raw = path.rstrip("/") or "/reports"
    if raw in ("/reports", "/preview/reports"):
        if fixture == "freshness":
            region = freshness_fixture_region(now)
            return 200, "text/html; charset=utf-8", render_region(data, region, now, public=False)
        if fixture == "empty":
            region = empty_fixture_region()
            return 200, "text/html; charset=utf-8", render_region(data, region, now, public=False)
        return 200, "text/html; charset=utf-8", render_index(data, now, public=public)
    if raw in ("/reports.css", "/preview/reports.css"):
        return 200, "text/css; charset=utf-8", css_bytes().decode("utf-8")
    prefix = "/reports/"
    alt = "/preview/reports/"
    if raw.startswith(prefix) or raw.startswith(alt):
        rid = raw[len(prefix):] if raw.startswith(prefix) else raw[len(alt):]
        rid = rid.strip("/")
        if fixture == "freshness":
            return 200, "text/html; charset=utf-8", render_region(data, freshness_fixture_region(now), now, public=False)
        if fixture == "empty":
            return 200, "text/html; charset=utf-8", render_region(data, empty_fixture_region(), now, public=False)
        parts = [p for p in rid.split("/") if p]
        if len(parts) == 1:
            region = region_by_id(data, parts[0])
            if not region:
                return 404, "text/plain; charset=utf-8", "not found"
            return 200, "text/html; charset=utf-8", render_region(data, region, now, public=public)
        if len(parts) == 2:
            region = region_by_id(data, parts[0])
            article = article_by_slug(region, parts[1]) if region else None
            if not region or not article:
                return 404, "text/plain; charset=utf-8", "not found"
            return 200, "text/html; charset=utf-8", render_article(data, region, article, public=public)
        return 404, "text/plain; charset=utf-8", "not found"
    return 404, "text/plain; charset=utf-8", "not found"


def sitemap_paths() -> list[str]:
    """Public URL paths to add to sitemap.xml when PUBLIC_WHATS_BITING is on."""
    paths = ["/reports"]
    data = load()
    for r in data.get("regions") or []:
        rid = r.get("id")
        if not rid:
            continue
        paths.append(f"/reports/{rid}")
        for article in r.get("articles") or []:
            slug = article.get("slug")
            if slug:
                paths.append(f"/reports/{rid}/{slug}")
    return paths
