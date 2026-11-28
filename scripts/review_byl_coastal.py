"""Phase 3C review of coastal/estuarine instruments for the pilot ramps (Ed t571u). Writes stations/byl_coastal_review.json.

Decisions only (no readings). Every candidate gets a recorded decision and reason. Rules:
- Observed wind: an official station (NOAA CO-OPS meteorological or NWS ASOS/AWOS airport). It must have
  reported wind within 2 h at review time and be within 8 mi of the ramp. The nearest qualifying station
  is accepted and always labelled Related station (the wind at the station, not at the ramp). Ocean-pier
  stations are flagged as more exposed than sound-side water. Citizen (CWOP/APRS) stations are never used.
- Marine zone: NWS sound/river zones (Albemarle, Alligator River, Croatan and Roanoke, Pamlico Sound, Pamlico
  and Pungo, Neuse and Bay) are accepted when the ramp point is inside the zone or within 1.5 km of it (ramps sit
  on the shore, and zone polygons stop at the water). An ocean zone (out to 20 NM) is accepted only when its
  polygon itself contains the ramp point, and then only as "ocean beyond the inlet", never as sound conditions.
- Coastal water temperature and observed water level: a CO-OPS station on the same water within 3 mi.
  Ocean-pier stations are rejected for sound or ICW ramps (different water), and ramps with an unresolved
  water class get none.
- Nautical chart: the largest-scale NOAA chart whose official footprint contains the ramp point, for
  coastal and estuarine ramps only.
"""
import json, math, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "TheCoastalBrief/1.0 (thecoastalbrief.com; station review)"}
WIND_MAX, WATER_MAX, ZONE_KM = 8.0, 3.0, 1.5
SOUND_ZONES = ["AMZ230", "AMZ131", "AMZ231", "AMZ135", "AMZ136", "AMZ137"]
OCEAN_ZONES = ["AMZ150", "AMZ152", "AMZ154", "AMZ156", "AMZ158", "AMZ250", "AMZ252"]


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return polys


def inside(lo, la, poly):
    def inring(r):
        c = False
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / (y2 - y1) + x1:
                c = not c
        return c
    return inring(poly[0]) and not any(inring(h) for h in poly[1:])


def edge_km(lo, la, poly):
    kx, ky = 111.32 * math.cos(la * math.pi / 180), 110.57
    best = 1e9
    for r in poly:
        for (x1, y1), (x2, y2) in zip(r, r[1:]):
            ax, ay, bx, by = (x1 - lo) * kx, (y1 - la) * ky, (x2 - lo) * kx, (y2 - la) * ky
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy or 1)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best
COOPS = {  # official CO-OPS stations in the pilot area; exposure from NOAA station pages
    "8651370": ("Duck", 36.1833, -75.7467, "ocean_pier"), "8652587": ("Oregon Inlet Marina", 35.7957, -75.5482, "sound_inlet"),
    "8654467": ("USCG Station Hatteras", 35.2086, -75.7042, "sound_inlet"), "8656483": ("Beaufort, Duke Marine Lab", 34.7173, -76.6707, "harbor_inlet"),
    "8658120": ("Wilmington", 34.2267, -77.9533, "river"), "8658163": ("Wrightsville Beach", 34.2133, -77.7867, "ocean_pier")}
ASOS = ["KMRH", "KNJM", "KEWN", "KNCA", "KOAJ", "KILM", "KMQI", "KFFA", "KHSE", "KNKT", "KSUT", "KOCW"]


def get(url, text=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        b = r.read()
    return b.decode() if text else json.loads(b)


def mi(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(x))


def coops_latest(sid, product):
    try:
        d = get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=%s&date=latest&station=%s&units=english&time_zone=gmt&datum=MLLW&format=json&application=thecoastalbrief" % (product, sid))
        t = datetime.strptime(d["data"][0]["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def main():
    now = datetime.now(timezone.utc)
    sites = [e for e in json.loads((ROOT / "stations/ramp_stations.json").read_text())["sites"] if e["pilot"] and e["water_class"] not in ("reservoir", "natural_lake", "river")]
    recs = {r["id"]: r for r in json.loads((ROOT / "preview/ramp-finder/map-data.json").read_text())["records"]}
    wind_st = []
    for sid, (name, la, lo, exp) in COOPS.items():
        t = coops_latest(sid, "wind")
        wind_st.append({"source": "NOAA CO-OPS", "id": sid, "name": name, "lat": la, "lon": lo, "exposure": exp, "active": bool(t and (now - t).total_seconds() < 7200)})
    for sid in ASOS:
        try:
            m = get("https://api.weather.gov/stations/" + sid)
            feats = get("https://api.weather.gov/stations/%s/observations?limit=6" % sid)["features"]
            o = next((x["properties"] for x in feats if (x["properties"].get("windSpeed") or {}).get("value") is not None), None)
            ok = bool(o) and (now - datetime.fromisoformat(o["timestamp"])).total_seconds() < 7200
            wind_st.append({"source": "NWS ASOS", "id": sid, "name": m["properties"]["name"], "lat": m["geometry"]["coordinates"][1], "lon": m["geometry"]["coordinates"][0], "exposure": "airport", "active": ok})
        except Exception:
            wind_st.append({"source": "NWS ASOS", "id": sid, "name": sid, "lat": None, "lon": None, "exposure": "airport", "active": False})
    water_st = {}
    for sid in COOPS:
        water_st[sid] = {"water_temp": bool(coops_latest(sid, "water_temperature")), "water_level": bool(coops_latest(sid, "water_level"))}
    zones = {z: get("https://api.weather.gov/zones/coastal/" + z) for z in SOUND_ZONES + OCEAN_ZONES}
    out = []
    for e in sites:
        r = recs[e["id"]]
        row = {"id": e["id"], "water_class": e["water_class"], "wind": [], "marine_zone": None, "water": [], "chart": None}
        if r.get("la") is None:
            row["note"] = "No official coordinates: no station, zone or chart can be matched."
            out.append(row); continue
        la, lo = r["la"], r["lo"]
        cands = sorted(((mi(la, lo, s["lat"], s["lon"]), s) for s in wind_st if s["lat"] is not None), key=lambda x: x[0])
        accepted = False
        for d, s in cands:
            if d > 15:
                break
            dec = {"source": s["source"], "id": s["id"], "name": s["name"], "distance_mi": round(d, 1), "exposure": s["exposure"]}
            if not s["active"]:
                dec.update(decision="rejected", reason="No current wind report at review time (inactive or no wind sensor).")
            elif d > WIND_MAX:
                dec.update(decision="rejected", reason="More than %d mi from the ramp." % WIND_MAX)
            elif accepted:
                dec.update(decision="rejected", reason="A nearer reviewed station was accepted.")
            else:
                dec.update(decision="accepted", label="Related station", reason="Official station reporting wind, %.1f mi away; shown as wind at the station, not at the ramp." % d
                           + (" Ocean pier: more exposed than sound-side water." if s["exposure"] == "ocean_pier" else "")
                           + (" Airport anemometer over land." if s["exposure"] == "airport" else ""))
                accepted = True
            row["wind"].append(dec)
        best = None
        for zid in SOUND_ZONES:
            for poly in rings(zones[zid]["geometry"]):
                d = 0.0 if inside(lo, la, poly) else edge_km(lo, la, poly)
                if d <= ZONE_KM and (best is None or d < best[0]):
                    best = (d, zid)
        if best:
            p = zones[best[1]]["properties"]
            row["marine_zone"] = {"decision": "accepted", "id": best[1], "name": p["name"], "kind": "sound_river", "distance_km": round(best[0], 2),
                                  "reason": "NWS marine zone for this sound or river %s." % ("contains the ramp point" if best[0] == 0 else "lies %.1f km from the ramp" % best[0])}
        else:
            oz = [z for z in OCEAN_ZONES if any(inside(lo, la, poly) for poly in rings(zones[z]["geometry"]))]
            if oz:
                p = zones[oz[0]]["properties"]
                row["marine_zone"] = {"decision": "accepted", "id": oz[0], "name": p["name"], "kind": "ocean_beyond_inlet",
                                      "reason": "Ocean zone polygon contains the shoreline point: shown only as ocean conditions beyond the inlet, not for the sound or waterway."}
            else:
                row["marine_zone"] = {"decision": "none", "reason": "No NWS sound or river zone within %.1f km, and no ocean zone contains the point." % ZONE_KM}
        for sid, (name, sla, slo, exp) in COOPS.items():
            d = mi(la, lo, sla, slo)
            if d > 10:
                continue
            for typ in ("water_temp", "water_level"):
                dec = {"source": "NOAA CO-OPS", "id": sid, "name": name, "type": typ, "distance_mi": round(d, 1), "exposure": exp}
                if e["water_class"] == "unresolved":
                    dec.update(decision="rejected", reason="Water class unresolved: water readings withheld.")
                elif not water_st[sid][typ]:
                    dec.update(decision="rejected", reason="Station does not currently report this product.")
                elif d > WATER_MAX:
                    dec.update(decision="rejected", reason="More than %d mi away: different water conditions likely." % WATER_MAX)
                elif exp == "ocean_pier":
                    dec.update(decision="rejected", reason="Ocean pier: ocean water, not the sound or waterway at this ramp.")
                else:
                    dec.update(decision="accepted", reason="Same water within %.1f mi." % d, datum="MLLW" if typ == "water_level" else None)
                row["water"].append(dec)
        try:
            res = get("https://gis.charttools.noaa.gov/arcgis/rest/services/RNC/NOAA_RNC_Footprints/MapServer/identify?geometry=%.5f,%.5f&geometryType=esriGeometryPoint&sr=4326&layers=all&tolerance=0&mapExtent=%.3f,%.3f,%.3f,%.3f&imageDisplay=400,400,96&returnGeometry=false&f=json" % (lo, la, lo - .5, la - .5, lo + .5, la + .5))["results"]
            best = min(res, key=lambda x: int(x["attributes"]["SCALE"]))
            a = best["attributes"]
            row["chart"] = {"chart": a["CHART"], "title": a["TITLE"].title(), "scale": int(a["SCALE"]), "url": "https://www.charts.noaa.gov/OnLineViewer/%s.shtml" % a["CHART"]}
        except Exception:
            row["chart"] = None
        out.append(row)
    doc = {"reviewed_at": now.isoformat(timespec="minutes"), "rules": __doc__.split("Rules:")[1].strip(), "sites": out}
    (ROOT / "stations/byl_coastal_review.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(len(out))


if __name__ == "__main__":
    main()
