"""Default-off public launch flags for What’s Biting?, Ramp Finder, and the map.

A merge of this branch changes nothing public unless an environment flag is
explicitly set to 1, true, on, or yes. Private preview routes stay cookie-gated.
"""
from __future__ import annotations

import os

PUBLIC_WHATS_BITING = "PUBLIC_WHATS_BITING"
PUBLIC_RAMPS = "PUBLIC_RAMPS"
PUBLIC_RAMP_MAP = "PUBLIC_RAMP_MAP"

_TRUE = ("1", "true", "on", "yes")


def flag_on(name: str) -> bool:
    """Opt-in only. Unset, empty, 0, false, or off is off."""
    return (os.environ.get(name) or "").strip().lower() in _TRUE


def whats_biting_public() -> bool:
    return flag_on(PUBLIC_WHATS_BITING)


def ramps_public() -> bool:
    """List and detail pages, and Find a Ramp entry links."""
    return flag_on(PUBLIC_RAMPS)


def ramp_map_public() -> bool:
    return flag_on(PUBLIC_RAMP_MAP)


def ramps_routes_public() -> bool:
    """Public /ramps list and detail become reachable if either ramp flag is on
    so a public map is not left pointing at 404 detail pages."""
    return ramps_public() or ramp_map_public()
