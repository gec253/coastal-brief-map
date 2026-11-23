"""Folio body entry links for What’s Biting? and Find a Ramp.

These are injected only on the public Hybrid homepage (including region
views). They are 44px text links in the page body, never in the masthead
beside the Map control.
"""
from __future__ import annotations

import html
from xml.sax.saxutils import escape as esc

import launch_flags

# What’s Biting? has pages for these five regions only.
WB_REGIONS = {
    "crystal-coast",
    "hatteras",
    "falls-lake",
    "jordan-lake",
    "neuse-river",
}
# Emerald Isle shares the Crystal Coast reports scope (Bogue Inlet / Emerald Isle).
WB_ALIASES = {
    "emerald-isle": "crystal-coast",
}
# Find a Ramp only where the inventory has coverage (audit / t425u).
RAMP_REGIONS = ("crystal-coast", "falls-lake", "jordan-lake", "neuse-river")


def _rid(region_id: str | None) -> str:
    return (region_id or "").strip() or "crystal-coast"


def whats_biting_entry(region_id: str | None) -> tuple[str, str, str]:
    """Return (href, label, optional note)."""
    rid = _rid(region_id)
    if rid in WB_REGIONS:
        return f"/reports/{rid}", "What’s Biting?", ""
    if rid in WB_ALIASES:
        dest = WB_ALIASES[rid]
        return f"/reports/{dest}", "What’s Biting?", ""
    if rid == "nags-head":
        return "/reports/hatteras", "What’s Biting?", "Hatteras Island reports"
    return "/reports", "What’s Biting?", "Regional reports index"


def ramps_entry(region_id: str | None) -> tuple[str, str] | None:
    rid = _rid(region_id)
    if rid not in RAMP_REGIONS:
        return None
    if rid == "crystal-coast":
        return "/ramps?region=crystal-coast", "Find a Ramp"
    return f"/ramps?region={rid}", "Find a Ramp"


def guides_html(region_id: str | None, *, public_page: bool) -> str:
    """Empty unless this is a public homepage view and at least one stage flag is on."""
    if not public_page:
        return ""
    links = []
    if launch_flags.whats_biting_public():
        href, label, note = whats_biting_entry(region_id)
        note_html = f'<span class="folio-guides-note">{esc(note)}</span>' if note else ""
        links.append(
            f'<a href="{html.escape(href, quote=True)}">{esc(label)}{note_html}</a>'
        )
    if launch_flags.ramps_public():
        entry = ramps_entry(region_id)
        if entry:
            href, label = entry
            links.append(f'<a href="{html.escape(href, quote=True)}">{esc(label)}</a>')
    if not links:
        return ""
    return (
        '<nav class="folio-guides" aria-label="Fishing reports and boat ramps">'
        '<p class="folio-guides-k">Guides</p>'
        f'<div class="folio-guides-l">{"".join(links)}</div>'
        "</nav>"
    )
