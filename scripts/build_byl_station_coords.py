"""Locations of every station a pilot Before You Launch page can use (Phase 3C locator maps).
Official metadata only (USGS site service, NOAA CO-OPS metadata, NWS station records); no readings.
Writes stations/byl_station_coords.json."""
import json, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
UA = {"User-Agent": "TheCoastalBrief/1.0 (thecoastalbrief.com; station metadata)"}


def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
        return r.read().decode()


def main():
    import byl_data as B
    sites = B.load_sites()
    cz = B.load_coastal()
    usgs, coops, asos = set(), set(), set()
    for sid, e in sites.items():
        for c in e["stations"]:
            if c["publishable"]:
                (usgs if c["source"] == "USGS" else coops if c["source"] in ("NOAA", "NOAA CO-OPS", "CO-OPS") or c["type"] == "tide_predictions" else set()).add(c["id"])
        for x in B.accepted((cz.get(sid) or {}).get("wind")) + B.accepted((cz.get(sid) or {}).get("water")):
            (coops if x["source"] == "NOAA CO-OPS" else asos).add(x["id"])
    out = {}
    rdb = get("https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=" + ",".join(sorted(usgs)))
    hdr = None
    for line in rdb.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split("\t")
        if hdr is None:
            hdr = f; continue
        if f[0] == "5s":
            continue
        r = dict(zip(hdr, f))
        out[r["site_no"]] = {"source": "USGS", "name": r["station_nm"].title(), "lat": round(float(r["dec_lat_va"]), 5), "lon": round(float(r["dec_long_va"]), 5)}
    for sid in sorted(coops):
        m = json.loads(get("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/%s.json" % sid))["stations"][0]
        out[sid] = {"source": "NOAA CO-OPS", "name": m["name"], "lat": round(m["lat"], 5), "lon": round(m["lng"], 5)}
    for sid in sorted(asos):
        m = json.loads(get("https://api.weather.gov/stations/" + sid))
        out[sid] = {"source": "NWS ASOS", "name": m["properties"]["name"], "lat": round(m["geometry"]["coordinates"][1], 5), "lon": round(m["geometry"]["coordinates"][0], 5)}
    (ROOT / "stations/byl_station_coords.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(len(out), sorted(usgs - set(out)), sorted(coops - set(out)), sorted(asos - set(out)))


if __name__ == "__main__":
    main()
