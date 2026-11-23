"""Sunrise, sunset, and moon phase for Morning Brief regions.

Computed locally (no network) from the region's official anchor coordinates
and the America/New_York calendar date of the brief.

Solar times follow the NOAA Solar Calculator equations (U.S. government work,
public domain): https://gml.noaa.gov/grad/solcalc/
Moon illuminated fraction follows Meeus, Astronomical Algorithms, ch. 48
(the standard phase-angle series). Phase name is taken from that fraction
and whether the moon is waxing or waning.

On any failure the result is status "unavailable". Nothing is invented.
Only Crystal Coast, Hatteras, and Falls Lake are supported.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Official brief anchors (data/regions.json). Do not invent other sites.
REGIONS = {
    "crystal-coast": {"label": "Beaufort Inlet", "lat": 34.695, "lon": -76.668},
    "hatteras": {"label": "Cape Hatteras", "lat": 35.2515, "lon": -75.5288},
    "falls-lake": {"label": "Falls Lake Dam", "lat": 35.9411, "lon": -78.5833},
}

# Official sunrise/sunset: sun's upper limb at the horizon, 0.833° refraction.
_ZENITH = 90.833


def _julian_day(y: int, month: int, day: float) -> float:
    if month <= 2:
        y -= 1
        month += 12
    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5


def _julian_cent(jd: float) -> float:
    return (jd - 2451545.0) / 36525.0


def _sind(d):
    return math.sin(math.radians(d))


def _cosd(d):
    return math.cos(math.radians(d))


def _tand(d):
    return math.tan(math.radians(d))


def _geom_mean_long_sun(t):
    return (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360


def _geom_mean_anom_sun(t):
    return 357.52911 + t * (35999.05029 - 0.0001537 * t)


def _eccent_earth(t):
    return 0.016708634 - t * (0.000042037 + 0.0000001267 * t)


def _sun_eq_of_center(t):
    m = _geom_mean_anom_sun(t)
    return (_sind(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
            + _sind(2 * m) * (0.019993 - 0.000101 * t)
            + _sind(3 * m) * 0.000289)


def _sun_true_long(t):
    return _geom_mean_long_sun(t) + _sun_eq_of_center(t)


def _sun_app_long(t):
    l = _sun_true_long(t)
    omega = 125.04 - 1934.136 * t
    return l - 0.00569 - 0.00478 * _sind(omega)


def _mean_obliq_ecliptic(t):
    seconds = 21.448 - t * (46.8150 + t * (0.00059 - t * 0.001813))
    return 23.0 + (26.0 + (seconds / 60.0)) / 60.0


def _obliq_corr(t):
    e0 = _mean_obliq_ecliptic(t)
    omega = 125.04 - 1934.136 * t
    return e0 + 0.00256 * _cosd(omega)


def _sun_declination(t):
    e = _obliq_corr(t)
    l = _sun_app_long(t)
    return math.degrees(math.asin(_sind(e) * _sind(l)))


def _var_y(t):
    e = math.radians(_obliq_corr(t) / 2.0)
    return math.tan(e) ** 2


def _eq_of_time(t):
    l0 = _geom_mean_long_sun(t)
    e = _eccent_earth(t)
    m = _geom_mean_anom_sun(t)
    y = _var_y(t)
    return 4 * math.degrees(
        y * _sind(2 * l0)
        - 2 * e * _sind(m)
        + 4 * e * y * _sind(m) * _cosd(2 * l0)
        - 0.5 * y * y * _sind(4 * l0)
        - 1.25 * e * e * _sind(2 * m)
    )


def _hour_angle_sunrise(lat, dec):
    arg = (_cosd(_ZENITH) / (_cosd(lat) * _cosd(dec))) - _tand(lat) * _tand(dec)
    if arg < -1 or arg > 1:
        return None  # polar day/night
    return math.degrees(math.acos(arg))


def _solar_noon_min(jd, lon, t):
    # minutes from local midnight UTC, NOAA: 720 - 4*lon - eqtime, lon east positive? NOAA uses west positive in some sheets.
    # The NOAA Javascript uses longitude as positive west of Greenwich in a few places and
    # negative-west (standard) in calcSolNoonUTC: 720 - (4 * longitude) - eqTime, with longitude
    # positive east (same sign as our lon).
    return 720 - (4 * lon) - _eq_of_time(t)


def _sunrise_sunset_utc_minutes(rise: bool, jd: float, lat: float, lon: float) -> float | None:
    t = _julian_cent(jd)
    noon = _solar_noon_min(jd, lon, t)
    # first pass
    t2 = _julian_cent(jd + noon / 1440.0)
    dec = _sun_declination(t2)
    ha = _hour_angle_sunrise(lat, dec)
    if ha is None:
        return None
    # 4 * (lon + ha) minutes; rise subtracts ha, set adds
    offset = 4 * (lon + (ha if rise else -ha))
    approx = 720 - offset - _eq_of_time(t2)
    t3 = _julian_cent(jd + approx / 1440.0)
    dec = _sun_declination(t3)
    ha = _hour_angle_sunrise(lat, dec)
    if ha is None:
        return None
    offset = 4 * (lon + (ha if rise else -ha))
    return 720 - offset - _eq_of_time(t3)


def _minutes_to_dt(d: date, minutes_utc: float, tz) -> datetime:
    base = datetime(d.year, d.month, d.day, tzinfo=ZoneInfo("UTC"))
    # minutes may be slightly negative or past 1440 near midnight
    return (base + timedelta(minutes=minutes_utc)).astimezone(tz)


def sun_times(lat: float, lon: float, d: date, tz=ET) -> dict | None:
    """Official sunrise and sunset in tz, or None if they cannot be computed."""
    try:
        lat = float(lat)
        lon = float(lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        jd = _julian_day(d.year, d.month, d.day)
        rise_m = _sunrise_sunset_utc_minutes(True, jd, lat, lon)
        set_m = _sunrise_sunset_utc_minutes(False, jd, lat, lon)
        if rise_m is None or set_m is None:
            return None
        sunrise = _minutes_to_dt(d, rise_m, tz)
        sunset = _minutes_to_dt(d, set_m, tz)
        # Guard: times must fall on this local date or the immediate neighbor (UTC wrap).
        if abs((sunrise.astimezone(tz).date() - d).days) > 1:
            return None
        return {"sunrise": sunrise, "sunset": sunset}
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _jd_datetime(dt: datetime) -> float:
    dt = dt.astimezone(ZoneInfo("UTC"))
    frac = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3.6e9) / 24.0
    return _julian_day(dt.year, dt.month, dt.day) + frac


def moon_illumination(dt: datetime) -> dict | None:
    """Illuminated fraction [0, 1] and waxing/waning at dt, or None on failure."""
    try:
        jd = _jd_datetime(dt)
        t = (jd - 2451545.0) / 36525.0
        # Meeus (48.2)–(48.3), degrees
        d = (297.8501921 + 445267.1114034 * t - 0.0018819 * t * t
             + t ** 3 / 545868.0 - t ** 4 / 113065000.0)
        m = (357.5291092 + 35999.0502909 * t - 0.0001536 * t * t
             + t ** 3 / 24490000.0)
        mp = (134.9633964 + 477198.8675055 * t + 0.0087414 * t * t
              + t ** 3 / 69699.0 - t ** 4 / 14712000.0)
        # Phase angle, Meeus 48.4.
        i = (180 - d
             - 6.289 * _sind(mp)
             + 2.100 * _sind(m)
             - 2.137 * _sind(2 * d - mp)
             - 0.658 * _sind(2 * d)
             - 0.214 * _sind(2 * mp)
             - 0.110 * _sind(d))
        k = (1 + _cosd(i)) / 2.0
        k = min(1.0, max(0.0, k))
        # Waxing if the moon is past new and before full: sin(D) > 0 roughly,
        # or illuminated fraction increasing. Use elongation D.
        waxing = _sind(d) > 0
        return {"fraction": k, "waxing": waxing, "phase_angle": i % 360}
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def phase_name(fraction: float, waxing: bool) -> str:
    """Standard English phase name from illuminated fraction and waxing/waning."""
    k = min(1.0, max(0.0, float(fraction)))
    # 50% ± ~2% is a quarter; near 0/100 is new/full.
    if k <= 0.005:
        return "New Moon"
    if k >= 0.995:
        return "Full Moon"
    if 0.48 <= k <= 0.52:
        return "First Quarter" if waxing else "Last Quarter"
    if waxing:
        return "Waxing Crescent" if k < 0.5 else "Waxing Gibbous"
    return "Waning Crescent" if k < 0.5 else "Waning Gibbous"


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p")


def for_region(region_id: str, on: date, tz=ET) -> dict:
    """Sun and moon for a supported region on a local calendar date.

    Returns a dict with status "ok" or "unavailable". Never raises to the caller
    with invented numbers; a partial failure (sun ok, moon not) is unavailable
    for the failed part only.
    """
    cfg = REGIONS.get(region_id)
    if not cfg or not isinstance(on, date):
        return {"status": "unavailable", "regionId": region_id}
    out = {
        "status": "ok",
        "regionId": region_id,
        "label": cfg["label"],
        "lat": cfg["lat"],
        "lon": cfg["lon"],
        "date": on.isoformat(),
        "tz": "America/New_York",
        "source": "Computed locally from the NOAA Solar Calculator equations and Meeus (Astronomical Algorithms, ch. 48). Not a live USNO fetch.",
        "sunrise": None,
        "sunset": None,
        "sunriseEt": None,
        "sunsetEt": None,
        "moon": None,
    }
    sun = sun_times(cfg["lat"], cfg["lon"], on, tz)
    if sun:
        # Prefer the time that falls on the requested local date.
        rise, sett = sun["sunrise"], sun["sunset"]
        out["sunrise"] = rise.isoformat()
        out["sunset"] = sett.isoformat()
        out["sunriseEt"] = _fmt_time(rise.astimezone(tz))
        out["sunsetEt"] = _fmt_time(sett.astimezone(tz))
    else:
        out["sunrise"] = out["sunset"] = None
    # Moon phase at local noon, which matches a daily "today's phase" reading.
    noon = datetime(on.year, on.month, on.day, 12, 0, tzinfo=tz)
    moon = moon_illumination(noon)
    if moon:
        frac = moon["fraction"]
        name = phase_name(frac, moon["waxing"])
        pct = int(round(frac * 100))
        if pct == 100 and name != "Full Moon":
            pct = 99
        if pct == 0 and name != "New Moon":
            pct = 1
        out["moon"] = {
            "name": name,
            "illuminationPct": pct,
            "fraction": round(frac, 4),
            "waxing": moon["waxing"],
        }
    if not out["sunriseEt"] and not out["moon"]:
        return {"status": "unavailable", "regionId": region_id, "date": on.isoformat()}
    if not out["sunriseEt"] or not out["moon"]:
        out["partial"] = True
    return out


def for_brief(region_id: str, on: date) -> dict:
    """Safe wrapper used when composing a brief."""
    try:
        return for_region(region_id, on, ET)
    except Exception:
        return {"status": "unavailable", "regionId": region_id}
