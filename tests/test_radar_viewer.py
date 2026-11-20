"""Private /radar viewer (Ed t364u): playback state machine, ET/DST formatting, observed vs forecast
separation, fixture isolation from production, radar cache TTL/keys, the preview gate, tap targets."""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import radarview  # noqa: E402

NODE = shutil.which("node")


def node(js):
    r = subprocess.run([NODE, "-e", "const P=require(%r);" % str(ROOT / "radar-player.js") + js], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


FRAMES_JS = """
const base = Date.UTC(2026, 2, 8, 5, 55) / 1000;
const code = (e) => new Date(e * 1000).toISOString().replace(/[-:T]/g, '').slice(0, 12);
const fr = [];
for (let i = 0; i < 30; i++) fr.push({time: code(base - 25 * 60 + i * 300), time_epoch: base - 25 * 60 + i * 300, type: 'observed'});
for (let i = 1; i <= 12; i++) fr.push({time: code(base + 29 * 300 - 25 * 60 + i * 300), time_epoch: base + 29 * 300 - 25 * 60 + i * 300, type: 'nowcast'});
fr.reverse();
"""


@unittest.skipUnless(NODE, "node not installed")
class Player(unittest.TestCase):
    def test_two_hour_observed_window_and_forecast_separate(self):
        r = node(FRAMES_JS + """const p = P.create(fr); const s = p.snapshot();
        const o = p.observed(); console.log(JSON.stringify({s, n: o.length, span: o[o.length-1].epoch - o[0].epoch,
          sorted: o.every((f, i) => !i || f.epoch > o[i-1].epoch), allObs: p.frames().every(f => f.type === 'observed'),
          fcAfter: p.forecast().every(f => f.epoch > o[o.length-1].epoch)}));""")
        self.assertEqual(r["n"], 25)                       # 30 supplied, only the last 2 h kept
        self.assertEqual(r["span"], 7200)
        self.assertTrue(r["sorted"] and r["allObs"] and r["fcAfter"])
        self.assertEqual((r["s"]["status"], r["s"]["index"], r["s"]["forecastOn"], r["s"]["segment"]), ("paused", 24, False, "observed"))

    def test_play_pause_step_seek_scrub_tick(self):
        r = node(FRAMES_JS + """const p = P.create(fr); const out = [];
        out.push(p.play().status); p.seek(0);
        out.push(p.tick().index);                                    // 1
        out.push(p.tick(i => i !== 2).index);                        // next not loaded -> stays 1
        out.push(p.step(1).status, p.snapshot().index);             // step pauses
        out.push(p.step(-1).index, p.step(-1).index, p.step(-1).index);   // clamps at 0
        p.play(); out.push(p.beginScrub().status); p.seek(10); out.push(p.tick().index);   // no tick while scrubbing
        out.push(p.endScrub().status);                               // resumes playing
        p.seek(24); out.push(p.holdMs()); out.push(p.tick().index); // wraps to oldest
        p.pause(); p.beginScrub(); out.push(p.endScrub().status);
        console.log(JSON.stringify(out));""")
        self.assertEqual(r, ["playing", 1, 1, "paused", 2, 1, 0, 0, "scrubbing", 10, "playing", 1600, 0, "paused"])

    def test_forecast_opt_in_labelled_and_never_mixed(self):
        r = node(FRAMES_JS + """const p = P.create(fr); const out = {};
        out.offCount = p.snapshot().count; out.offTypes = [...new Set(p.frames().map(f => f.type))];
        p.setForecast(true); const s = p.snapshot(); out.onCount = s.count; out.boundary = s.boundary;
        out.types = p.frames().map(f => f.type); p.seek(30); out.seg = p.snapshot().segment; out.segOf = [p.segmentOf(24), p.segmentOf(25)];
        p.setForecast(false); out.back = p.snapshot(); console.log(JSON.stringify(out));""")
        self.assertEqual((r["offCount"], r["offTypes"]), (25, ["observed"]))
        self.assertEqual((r["onCount"], r["boundary"]), (37, 25))
        self.assertEqual(r["types"], ["observed"] * 25 + ["forecast"] * 12)        # never interleaved
        self.assertEqual(r["seg"], "forecast"); self.assertEqual(r["segOf"], ["observed", "forecast"])
        self.assertEqual((r["back"]["index"], r["back"]["segment"], r["back"]["count"]), (24, "observed", 25))

    def test_empty_and_no_forecast(self):
        r = node("""const e = P.create([]); const o = P.create([{time:'202603080700',time_epoch:1772953200,type:'observed'}]);
        console.log(JSON.stringify([e.play().status, e.step(1).status, o.setForecast(true).forecastOn]));""")
        self.assertEqual(r, ["empty", "empty", False])

    def test_eastern_time_and_dst(self):
        r = node("""const e = (y,m,d,h,mi) => Date.UTC(y,m-1,d,h,mi)/1000;
        console.log(JSON.stringify([P.etTime(e(2026,3,8,6,55)), P.etTime(e(2026,3,8,7,0)), P.etLong(e(2026,3,8,6,55)), P.etLong(e(2026,3,8,7,0)),
          P.etLong(e(2026,11,1,5,55)), P.etLong(e(2026,11,1,6,0)), P.etTime(e(2026,7,4,16,5)), P.age(1000, 1000-6*60), P.age(1000, 1000-65*60), P.age(1000, 1000),
          P.epochFromCode('202603080700')]));""")
        self.assertEqual(r[:2], ["1:55 AM ET", "3:00 AM ET"])                     # spring forward
        self.assertTrue(r[2].endswith("1:55 AM EST") and r[3].endswith("3:00 AM EDT"))
        self.assertTrue(r[4].endswith("1:55 AM EDT") and r[5].endswith("1:00 AM EST"))   # fall back
        self.assertEqual(r[6], "12:05 PM ET")
        self.assertEqual(r[7:10], ["6 min ago", "1 h 5 min ago", "just now"])
        self.assertEqual(r[10], 1772953200)


class Fixture(unittest.TestCase):
    def test_fixture_only_in_local_test_mode(self):
        with mock.patch.dict(os.environ, {"RADAR_FIXTURE": "1"}, clear=False):
            os.environ.pop("RENDER", None); os.environ.pop("RENDER_SERVICE_ID", None)
            self.assertTrue(radarview.fixture_mode())
        for env in ({"RADAR_FIXTURE": "1", "RENDER": "true"}, {"RADAR_FIXTURE": "1", "RENDER_SERVICE_ID": "srv-x"}, {"RADAR_FIXTURE": ""}):
            with mock.patch.dict(os.environ, env):
                if "RENDER" not in env: os.environ.pop("RENDER", None)
                if "RENDER_SERVICE_ID" not in env: os.environ.pop("RENDER_SERVICE_ID", None)
                self.assertFalse(radarview.fixture_mode(), env)
                self.assertIsNone(radarview.fixture_tile("7", "36", "50", "202603080655"))

    def test_production_without_entitlement_is_honest_never_fixture(self):
        meta = lambda: (200, {"ok": False, "available": False, "reason": "coming_soon", "message": "Radar coming soon"})
        with mock.patch.dict(os.environ, {"RADAR_FIXTURE": "1", "RENDER": "true"}):
            st, p = radarview.view_payload(meta)
        self.assertEqual((st, p["ok"], p["fixture"], p["reason"], p["message"]), (200, False, False, "plan", "Radar unavailable on current data plan"))
        self.assertNotIn("frames", p)
        with mock.patch.dict(os.environ, {"RADAR_FIXTURE": "1", "RENDER": "true"}):
            st, p = radarview.view_payload(lambda: (502, {"ok": False, "reason": "upstream", "message": "Radar is unavailable right now."}))
        self.assertEqual((st, p["fixture"], p["reason"]), (502, False, "upstream"))

    def test_fixture_is_labelled_and_in_the_past(self):
        with mock.patch.dict(os.environ, {"RADAR_FIXTURE": "1"}):
            os.environ.pop("RENDER", None); os.environ.pop("RENDER_SERVICE_ID", None)
            p = radarview.fixture_payload()
            self.assertTrue(radarview.fixture_tile("7", "36", "50", p["frames"][0]["time"]).startswith(b"\x89PNG"))
            self.assertIsNone(radarview.fixture_tile("7", "../..", "50", "202603080655"))
        self.assertTrue(p["fixture"]); self.assertEqual(p["fixture_label"], "TEST DATA — not current radar")
        self.assertIn("Synthetic", p["fixture_source"])
        self.assertTrue(all(f["time_epoch"] < 1774000000 for f in p["frames"]))     # March 2026, never "now"
        self.assertEqual([f["type"] for f in p["frames"]].count("observed"), 25)
        self.assertTrue(p["tile_url"].startswith("/radar/fixture-tile/"))


class Cache(unittest.TestCase):
    def test_ttls_and_tile_cache_key(self):
        import server
        self.assertEqual(server.TTL["radar_json"], 180)
        self.assertEqual(server.TTL["radar_tile"], 7200)
        puts = []
        with mock.patch.object(server, "weatherapi_key", return_value="k"), \
             mock.patch.object(server, "cache_get", return_value=None), \
             mock.patch.object(server, "cache_put", side_effect=lambda *a: puts.append(a)), \
             mock.patch.object(server, "_refresh_radar_mem", return_value={"ok": True}), \
             mock.patch.dict(server._RADAR_MEM, {"tile_url": "https://api.weatherapi.com/v1/radar/tile/{z}/{x}/{y}/{time}.png?sig=SECRET"}), \
             mock.patch.object(server, "fetch_url_quiet", return_value=(200, "image/png", b"\x89PNG")):
            st, ct, body = server.fetch_radar_tile("7", "36", "50", "202611200900")
        self.assertEqual(st, 200)
        self.assertEqual(puts[0][0], "radar-cache://tile/7/36/50/202611200900")   # z/x/y/time, never the signed URL
        self.assertEqual(puts[0][1], "radar_tile")
        self.assertNotIn("SECRET", puts[0][0])


class Routes(unittest.TestCase):
    PATHS = ("/radar", "/radar.css", "/radar/viewer.js", "/radar/player.js", "/api/radar-view", "/radar/fixture-tile/7/36/50.png?t=202603080655")

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_404_without_cookie_even_in_fixture_mode(self):
        key = secrets.token_hex(16)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key, "RADAR_FIXTURE": "1"}), \
             mock.patch.object(self.server, "handle_radar_meta", side_effect=AssertionError("must not fetch")):
            for p in self.PATHS:
                self.assertEqual(self._get(p)[0], 404, p)
                self.assertEqual(self._get(p, "cb_preview=nope")[0], 404, p)
            for p in ("/radar.html", "/radar-viewer.js", "/radar-player.js", "/radar.css.map", "/radarview.py", "/tests/fixtures/radar/fixture.json"):
                self.assertEqual(self._get(p)[0], 404, p)

    def test_cookie_unlocks_private_page_and_plan_state(self):
        key = secrets.token_hex(16)
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(key))
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key, "RADAR_FIXTURE": "", "RENDER": "true"}), \
             mock.patch.object(self.server, "handle_radar_meta", return_value=(200, {"ok": False, "reason": "coming_soon", "message": "Radar coming soon"})):
            st, h, body = self._get("/radar", ck)
            self.assertEqual(st, 200); self.assertIn("noindex", h.get("X-Robots-Tag", "")); self.assertIn(b'data-radar-view="viewer"', body)
            j = json.loads(self._get("/api/radar-view", ck)[2])
            self.assertEqual((j["ok"], j["reason"], j["fixture"]), (False, "plan", False))
            self.assertEqual(self._get("/radar/fixture-tile/7/36/50.png?t=202603080655", ck)[0], 404)   # no fixture in production

    def test_public_radar_api_unchanged(self):
        with mock.patch.object(self.server, "handle_radar_meta", return_value=(200, {"ok": False, "reason": "coming_soon", "message": "Radar coming soon"})):
            j = json.loads(self._get("/api/radar")[2])
        self.assertEqual(j, {"ok": False, "reason": "coming_soon", "message": "Radar coming soon"})


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "radar.html").read_text(); cls.css = (ROOT / "radar.css").read_text(); cls.js = (ROOT / "radar-viewer.js").read_text()

    def test_reuses_wind_design_and_theme_sync(self):
        self.assertIn('href="/wind.css"', self.html)
        self.assertIn('localStorage.getItem("coastalBrief.theme")', self.html)
        self.assertIn('const THEME_STORE = "coastalBrief.theme";', self.js)
        self.assertIn('id="w-theme"', self.html)
        self.assertIn("CBCoast.layer", self.js)

    def test_labels_and_honest_states(self):
        self.assertIn("Radar unavailable on current data plan", self.html + self.js)
        self.assertIn('"Forecast · "', self.js); self.assertIn('"Observed · "', self.js)
        self.assertIn(".r-tag.is-fc", self.css); self.assertIn(".r-stage.is-fc::after", self.css)
        self.assertIn('<input type="checkbox" id="r-fc" disabled>', self.html)          # forecast off by default
        self.assertNotIn("checked", re.search(r'<input type="checkbox" id="r-fc"[^>]*>', self.html).group(0))
        self.assertIn("TEST DATA — not current radar", self.html)
        self.assertIn('class="r-test" id="r-test" hidden', self.html)

    def test_tap_targets_at_least_44px(self):
        wind_css = (ROOT / "wind.css").read_text()
        self.assertIn("min-height: 52px", wind_css)                    # .w-btn reused for prev/play/next
        self.assertRegex(self.css, r"\.r-fc \{[^}]*min-height: 44px")
        self.assertRegex(self.css, r"\.r-tl input\[type=range\] \{[^}]*height: 44px")
        self.assertIn("prefers-reduced-motion", self.js + self.css)

    def test_not_linked_from_public_pages(self):
        for f in ("index.html", "dashboard.js", "app.js", "sprint_home.py", "site_chrome.py"):
            p = ROOT / f
            if p.exists():
                self.assertNotRegex(p.read_text(), r'href="/radar["?#]', f)



class ServerRendered(unittest.TestCase):
    def test_unavailable_state_rendered_into_page(self):
        html = (ROOT / "radar.html").read_text()
        out = radarview.page_html(html, {"ok": False, "reason": "plan"})
        self.assertIn('<div class="r-unavail" id="r-unavail" role="status">', out)
        self.assertIn('id="r-badge">Radar off<', out)
        self.assertIn('<label class="r-fc" hidden>', out)
        self.assertIn("Radar unavailable on current data plan", out)
        self.assertIn("Radar is unavailable right now</strong>", radarview.page_html(html, {"ok": False, "reason": "upstream"}))
        self.assertEqual(radarview.page_html(html, {"ok": True, "frames": [{"time": "202603080700"}]}), html)


def _real_radar_json(latest_epoch=1795179900):
    """Shape of a real Pro+ /v1/radar.json response (Nov 20, 2026), with a fake signature. No key."""
    import datetime as dt
    code = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime("%Y%m%d%H%M")
    frames = [{"time": code(latest_epoch - (24 - i) * 300), "time_epoch": latest_epoch - (24 - i) * 300, "type": "observed"} for i in range(25)]
    frames += [{"time": code(latest_epoch + i * 300), "time_epoch": latest_epoch + i * 300, "type": "nowcast"} for i in range(1, 13)]
    return {"location": {"lat": 34.724, "lon": -76.648, "tz_id": "America/New_York"}, "radar": {
        "available": True, "covered": True, "tile_size": 256, "min_zoom": 0, "max_zoom": 11,
        "tile_url": "https://api.weatherapi.com/v1/radar/tile/{z}/{x}/{y}.png?t={time}&e=1795187400&k=1&p=5&s=FAKESIG",
        "tile_url_expires_epoch": latest_epoch + 7200,
        "sources": [{"id": "mrms", "name": "NOAA MRMS (United States)", "latest_epoch": latest_epoch, "nowcast_minutes": 60, "bounds": [20.01, -129.99, 54.99, -60.01]}],
        "frames": frames, "legend": [{"from_mm_h": 0.1, "color": "#9be7a1"}, {"from_mm_h": 64.0, "color": "#7e22ce"}],
        "attribution": "Radar: NOAA/NSSL MRMS. Nowcast: WeatherAPI.com."}}


class RealMode(unittest.TestCase):
    """Pro+ real data (Ed t365u), with mocked upstream responses: no key, no network."""
    def _refresh(self, server, body, now):
        calls = []
        def fake_fetch(url, tries=3):
            calls.append(url); return 200, "application/json", json.dumps(body).encode()
        with mock.patch.object(server, "weatherapi_key", return_value="TESTKEY"), \
             mock.patch.object(server, "fetch_url_quiet", side_effect=fake_fetch), \
             mock.patch.object(server, "record_radar_upstream"), mock.patch.object(server, "record_radar_cache_hit"), \
             mock.patch.object(server.time, "time", return_value=now):
            return server._refresh_radar_mem(), calls

    def test_real_payload_cache_ttl_and_no_secret_to_client(self):
        import server
        server._RADAR_MEM.clear()
        body = _real_radar_json(); t = 1795180200
        p, calls = self._refresh(server, body, t)
        self.assertTrue(p["ok"]); self.assertEqual(len(calls), 1)
        self.assertEqual(p["tile_url"], "/api/radar/tile/{z}/{x}/{y}.png?t={time}")
        self.assertNotIn("FAKESIG", json.dumps(p)); self.assertNotIn("TESTKEY", json.dumps(p))
        self.assertEqual([f["type"] for f in p["frames"]].count("observed"), 25)
        _, calls = self._refresh(server, body, t + 179)          # inside the 180 s TTL: cached, no call
        self.assertEqual(calls, [])
        _, calls = self._refresh(server, _real_radar_json(1795180200), t + 181)   # expired: one new call
        self.assertEqual(len(calls), 1)
        self.assertEqual(server._RADAR_MEM["client"]["frames"][24]["time_epoch"], 1795180200)
        server._RADAR_MEM.clear()

    def test_view_payload_real_mode_never_fixture(self):
        import server
        server._RADAR_MEM.clear()
        p, _ = self._refresh(server, _real_radar_json(), 1795180200)
        for env in ({"RENDER": "true", "RADAR_FIXTURE": "1"}, {"RADAR_FIXTURE": ""}):
            with mock.patch.dict(os.environ, env):
                if "RENDER" not in env: os.environ.pop("RENDER", None); os.environ.pop("RENDER_SERVICE_ID", None)
                st, v = radarview.view_payload(lambda: (200, p))
            self.assertEqual((st, v["ok"], v["fixture"], v["max_native_zoom"]), (200, True, False, 7))
            self.assertNotIn("fixture", v["tile_url"]); self.assertNotIn("fixture_label", v)
            self.assertEqual(v["attribution"], "Radar: NOAA/NSSL MRMS via WeatherAPI.com")
        europe = dict(p, sources=p["sources"] + [{"id": "other", "bounds": [25.0, -80.0, 45.0, -60.0]}], attribution="Radar: NOAA/NSSL MRMS; EUMETNET OPERA (CC BY 4.0).")
        with mock.patch.dict(os.environ, {"RENDER": "true"}):
            self.assertEqual(radarview.view_payload(lambda: (200, europe))[1]["attribution"], "Radar: NOAA/NSSL MRMS; EUMETNET OPERA (CC BY 4.0).")
        server._RADAR_MEM.clear()

    def test_2009_still_maps_to_plan_message(self):
        import server
        server._RADAR_MEM.clear()
        with mock.patch.object(server, "weatherapi_key", return_value="TESTKEY"), \
             mock.patch.object(server, "fetch_url_quiet", return_value=(400, "application/json", b'{"error":{"code":2009,"message":"x"}}')), \
             mock.patch.object(server, "record_radar_upstream"):
            st, v = radarview.view_payload(server.handle_radar_meta)
        self.assertEqual((st, v["reason"], v["message"]), (200, "plan", "Radar unavailable on current data plan"))

    @unittest.skipUnless(NODE, "node not installed")
    def test_player_update_keeps_state_and_follows_latest(self):
        r = node(FRAMES_JS + """const p = P.create(fr); p.play(); const out = [];
        const later = fr.map(f => ({time: f.time, time_epoch: f.time_epoch, type: f.type}));
        const obs = later.filter(f => f.type === 'observed').sort((a, b) => a.time_epoch - b.time_epoch);
        const ne = obs[obs.length-1].time_epoch + 300; later.push({time: code(ne), time_epoch: ne, type: 'observed'});
        let s = p.update(later); out.push(s.status, s.index, s.frame.time === code(ne), s.observedCount);
        p.pause(); p.seek(3); const keep = p.snapshot().frame.time; s = p.update(later); out.push(s.frame.time === keep, s.status);
        p.setForecast(true); s = p.update(later.filter(f => f.type === 'observed')); out.push(s.forecastOn, s.forecastCount);
        s = p.update([]); out.push(s.status); console.log(JSON.stringify(out));""")
        self.assertEqual(r, ["playing", 24, True, 25, True, "paused", False, 0, "empty"])

    def test_viewer_refreshes_on_cache_ttl_and_shows_age(self):
        js = (ROOT / "radar-viewer.js").read_text()
        self.assertIn("setInterval(refresh, 180000)", js)
        self.assertIn("player.update(m.frames)", js)
        self.assertIn("if (fixture || document.hidden) return;", js)


if __name__ == "__main__":
    unittest.main()
