"""Professional missing-data strings for private preview briefs only.

Live brief.py (Crystal Coast / Hatteras / Falls Lake) does not import this
module. Proposed wording is pending any edits from Design.
"""
from __future__ import annotations

HEADING_NOT_AVAILABLE = "Not available at issue time"
HEADING_NOT_MEASURED = "Not measured in this area"
PLACEHOLDER = "Not available"

STAGE_NOTE = (
    "Stage is the water height at the gauge, measured from its own reference point. "
    "It is not water depth."
)

TIDE_PREDICTIONS_UNAVAILABLE = "Tide predictions: Not available from NOAA CO-OPS at issue time."
ALERTS_CHECK_FAILED = (
    "Alerts: Could not be checked at issue time. See weather.gov for current alerts."
)


def not_available(label: str) -> str:
    return "%s: Not available at issue time." % label


def not_reported(label: str, agency: str, station_id: str, time: str | None = None) -> str:
    who = " ".join(p for p in (agency, station_id) if p).strip() or "The station"
    if time:
        return "%s: Not reported. %s has not reported since %s." % (label, who, time)
    return "%s: Not reported. %s has not reported." % (label, who)


def not_used(label: str, time: str, hours) -> str:
    n = str(hours).rstrip("0").rstrip(".") if isinstance(hours, float) else str(hours)
    return "%s: Not used. The last report, at %s, is older than the %s-hour limit." % (label, time, n)


def nws_forecast_unavailable(label: str) -> str:
    return "%s: NWS forecast not available at issue time." % label


def observed_water_level_not_measured(station: str) -> str:
    return "Observed water level: Not measured here. Tide times are NOAA predictions for %s." % station


def not_measured(label: str) -> str:
    return "%s: Not measured. No official sensor in this area." % label


def stage_only(label: str) -> str:
    return "%s: Not published. USGS reports stage only at this gauge." % label


def alerts_none(areas: str) -> str:
    return "Alerts: No active NWS alerts for %s." % areas


def heading_for_case(case: int) -> str:
    """Section heading: cases 1–5 and 9 vs cases 6–8."""
    if case in (6, 7, 8):
        return HEADING_NOT_MEASURED
    return HEADING_NOT_AVAILABLE
