"""Community photo submissions (Catch Wall + Coastal Life), behind a feature flag.

Everything here is OFF unless PHOTO_UPLOADS_ENABLED=1 *and* a storage backend is
configured. With the flag off, no endpoint in this module accepts input: the
submit and admin routes return 404 and /api/photos/config reports uploads off.

Storage: Supabase Storage (private "pending" bucket, public "approved" bucket)
plus a Postgres table, reached with plain HTTPS (urllib); no SDK. The
service-role key is read from the environment on the server only and is never
sent to a browser. A local "fake" backend (files in a temp folder) exists only
for local testing and refuses to run on Render.

Image work uses Pillow (+ pillow-heif for iPhone HEIC). They are imported
lazily so the rest of the site keeps running on the standard library alone.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MAX_BYTES = 15 * 1024 * 1024          # upload size cap (about 15 MB)
MAX_PIXELS = 50_000_000               # decompression-bomb cap (50 MP; iPhone 48 MP fits)
MIN_SIDE = 320                        # reject tiny images
SIZES = (400, 800, 1600)              # WebP widths for srcset
THUMB = 240                           # admin/thumbnail width
CATEGORIES = ("fishing", "life")
STATUSES = ("pending", "approved", "rejected", "removed")
TEXT_LIMITS = {"display_name": 40, "species": 60, "location": 60, "caption": 280}
SESSION_COOKIE = "cb_admin"
SESSION_TTL = 8 * 3600


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def flag_on() -> bool:
    return _env("PHOTO_UPLOADS_ENABLED").lower() in ("1", "true", "yes", "on")


def on_render() -> bool:
    return bool(os.environ.get("RENDER"))


# ---------------------------------------------------------------- storage
class StorageError(Exception):
    pass


class SupabaseBackend:
    """Supabase Storage + PostgREST over HTTPS with the service-role key."""

    name = "supabase"

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self._key = key
        self.pending = _env("SUPABASE_PENDING_BUCKET", "photos-pending")
        self.approved = _env("SUPABASE_APPROVED_BUCKET", "photos-approved")
        self.table = _env("SUPABASE_TABLE", "photo_submissions")

    def _req(self, method, path, body=None, headers=None, timeout=20):
        # New sb_secret_ keys are not JWTs: send them on apikey only.
        # Legacy service_role JWTs (eyJ...) also go on Authorization.
        h = {"apikey": self._key}
        if self._key.startswith("eyJ"):
            h["Authorization"] = "Bearer " + self._key
        h.update(headers or {})
        req = Request(self.url + path, data=body, method=method, headers=h)
        try:
            with urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            raise StorageError("%s %s -> %s %s" % (method, path.split("?")[0], e.code, detail))
        except URLError as e:
            raise StorageError("%s %s -> %s" % (method, path.split("?")[0], e.reason))

    # objects
    def put(self, bucket, key, data, ctype):
        self._req("POST", "/storage/v1/object/%s/%s" % (bucket, quote(key)), data,
                  {"Content-Type": ctype, "x-upsert": "true", "Cache-Control": "31536000"})

    def get(self, bucket, key):
        return self._req("GET", "/storage/v1/object/%s/%s" % (bucket, quote(key)))[1]

    def delete(self, bucket, keys):
        if keys:
            self._req("DELETE", "/storage/v1/object/%s" % bucket,
                      json.dumps({"prefixes": list(keys)}).encode(), {"Content-Type": "application/json"})

    def public_url(self, key):
        return "%s/storage/v1/object/public/%s/%s" % (self.url, self.approved, quote(key))

    # rows
    def insert(self, row):
        self._req("POST", "/rest/v1/%s" % self.table, json.dumps(row).encode(),
                  {"Content-Type": "application/json", "Prefer": "return=minimal"})

    def select(self, status=None, category=None, featured=None, limit=200, row_id=None):
        q = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if status:
            q["status"] = "eq." + status
        if category:
            q["category"] = "eq." + category
        if featured is not None:
            q["featured"] = "eq." + ("true" if featured else "false")
        if row_id:
            q["id"] = "eq." + row_id
        return json.loads(self._req("GET", "/rest/v1/%s?%s" % (self.table, urlencode(q)))[1] or b"[]")

    def update(self, row_id, fields):
        self._req("PATCH", "/rest/v1/%s?id=eq.%s" % (self.table, quote(row_id)), json.dumps(fields).encode(),
                  {"Content-Type": "application/json", "Prefer": "return=minimal"})


class FakeBackend:
    """Local test double: same interface, files in PHOTO_FAKE_DIR. Never on Render."""

    name = "fake"

    def __init__(self, root: str):
        self.root = Path(root)
        self.pending, self.approved = "pending", "approved"
        (self.root / "pending").mkdir(parents=True, exist_ok=True)
        (self.root / "approved").mkdir(parents=True, exist_ok=True)
        self.db = self.root / "rows.json"
        self._lock = threading.Lock()

    def _path(self, bucket, key):
        p = (self.root / bucket / key).resolve()
        if not str(p).startswith(str((self.root / bucket).resolve())):
            raise StorageError("bad key")
        return p

    def put(self, bucket, key, data, ctype):
        p = self._path(bucket, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, bucket, key):
        p = self._path(bucket, key)
        if not p.is_file():
            raise StorageError("missing object")
        return p.read_bytes()

    def delete(self, bucket, keys):
        for k in keys:
            p = self._path(bucket, k)
            if p.is_file():
                p.unlink()

    def public_url(self, key):
        return "/fake-storage/approved/" + quote(key)

    def _rows(self):
        return json.loads(self.db.read_text()) if self.db.is_file() else []

    def insert(self, row):
        with self._lock:
            rows = self._rows()
            row = dict(row)
            row.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            rows.append(row)
            self.db.write_text(json.dumps(rows))

    def select(self, status=None, category=None, featured=None, limit=200, row_id=None):
        rows = [r for r in self._rows()
                if (not status or r.get("status") == status)
                and (not category or r.get("category") == category)
                and (featured is None or bool(r.get("featured")) == featured)
                and (not row_id or r.get("id") == row_id)]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def update(self, row_id, fields):
        with self._lock:
            rows = self._rows()
            for r in rows:
                if r.get("id") == row_id:
                    r.update(fields)
            self.db.write_text(json.dumps(rows))


_backend = None
_backend_lock = threading.Lock()


def backend():
    global _backend
    with _backend_lock:
        if _backend is not None:
            return _backend or None
        kind = _env("PHOTO_BACKEND", "supabase").lower()
        if kind == "fake":
            root = _env("PHOTO_FAKE_DIR")
            _backend = FakeBackend(root) if (root and not on_render()) else False
        else:
            url, key = _env("SUPABASE_URL"), _env("SUPABASE_SECRET_KEY") or _env("SUPABASE_SERVICE_ROLE_KEY")
            _backend = SupabaseBackend(url, key) if (url.startswith("https://") and key) else False
        return _backend or None


def turnstile_site_key() -> str:
    return _env("TURNSTILE_SITE_KEY")


_PIL_OK = None


def pillow_ok() -> bool:
    global _PIL_OK
    if _PIL_OK is None:
        try:
            import PIL.Image  # noqa: F401
            _PIL_OK = True
        except ImportError:
            _PIL_OK = False
    return _PIL_OK


def uploads_active() -> bool:
    """Public submissions are accepted only when every safeguard is configured."""
    b = backend()
    if not flag_on() or not b or not pillow_ok():
        return False
    if b.name == "fake":
        return True  # local testing only (FakeBackend refuses to run on Render)
    return bool(_env("TURNSTILE_SECRET_KEY") and turnstile_site_key())


def admin_configured() -> bool:
    return flag_on() and bool(backend()) and bool(_env("PHOTO_ADMIN_PASSWORD_HASH")) and len(_env("PHOTO_SESSION_SECRET")) >= 32


def public_config() -> dict:
    on = uploads_active()
    return {"uploads": on, "turnstileSiteKey": turnstile_site_key() if on else "",
            "maxBytes": MAX_BYTES, "categories": list(CATEGORIES)}


# ---------------------------------------------------------------- rate limits
class RateLimiter:
    def __init__(self):
        self._hits: dict = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_s]
            ok = len(hits) < limit
            if ok:
                hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 5000:  # bound memory
                for k in list(self._hits)[:1000]:
                    self._hits.pop(k, None)
            return ok


LIMITS = RateLimiter()


def ip_hash(ip: str) -> str:
    salt = _env("PHOTO_SESSION_SECRET", "local")
    return hashlib.sha256((salt + "|" + (ip or "")).encode()).hexdigest()[:24]


# ---------------------------------------------------------------- turnstile
def verify_turnstile(token: str, ip: str) -> bool:
    b = backend()
    if b and b.name == "fake" and not _env("TURNSTILE_SECRET_KEY"):
        return token == "local-test-pass"
    secret = _env("TURNSTILE_SECRET_KEY")
    if not secret or not token or len(token) > 2048:
        return False
    body = urlencode({"secret": secret, "response": token, "remoteip": ip or ""}).encode()
    req = Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=body, method="POST",
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=10) as r:
            return bool(json.loads(r.read()).get("success"))
    except Exception:
        return False


# ---------------------------------------------------------------- multipart
def parse_multipart(content_type: str, body: bytes) -> dict:
    """Return {field: str} and {'_file': (filename, bytes)}; stdlib email parser."""
    if not content_type.lower().startswith("multipart/form-data") or "boundary=" not in content_type:
        raise ValueError("Expected a multipart form.")
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ValueError("Could not read the form.")
    out: dict = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is not None:
            if name == "photo" and "_file" not in out:
                out["_file"] = (filename, payload)
        else:
            out[name] = payload.decode("utf-8", "replace")
    return out


# ---------------------------------------------------------------- images
_SIGS = {
    "jpeg": lambda b: b[:3] == b"\xff\xd8\xff",
    "png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
    "heif": lambda b: b[4:8] == b"ftyp" and b[8:12] in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis", b"avif"),
}


def sniff(data: bytes):
    for kind, test in _SIGS.items():
        if len(data) > 16 and test(data):
            return kind
    return None


class ImageRejected(ValueError):
    pass


def process_image(data: bytes) -> dict:
    """Validate and re-encode. Returns {'w','h','files':{name: bytes}}.
    Output is rebuilt from pixels only, so EXIF/GPS/XMP never survive."""
    if len(data) > MAX_BYTES:
        raise ImageRejected("That file is larger than 15 MB.")
    kind = sniff(data)
    if not kind:
        raise ImageRejected("That file is not a JPEG, PNG, WebP, or HEIC photo.")
    from PIL import Image, ImageOps  # lazy: optional dependency
    if kind == "heif":
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise ImageRejected("HEIC photos are not supported on this server yet. Please send a JPEG.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            w0, h0 = probe.size
            fmt = (probe.format or "").upper()
            if w0 * h0 > MAX_PIXELS:
                raise ImageRejected("That photo has too many pixels.")
            probe.verify()
        im = Image.open(io.BytesIO(data))
        if getattr(im, "n_frames", 1) > 1 and fmt not in ("HEIF", "HEIC", "MPO", "JPEG"):
            raise ImageRejected("Animated images are not accepted.")
        im.load()
    except ImageRejected:
        raise
    except Image.DecompressionBombError:
        raise ImageRejected("That photo has too many pixels.")
    except Exception:
        raise ImageRejected("That photo could not be read. Please try a different file.")
    if fmt not in ("JPEG", "PNG", "WEBP", "HEIF", "HEIC", "MPO", "AVIF"):
        raise ImageRejected("Unsupported image format.")
    im = ImageOps.exif_transpose(im)  # apply camera orientation, then drop metadata
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    clean = Image.frombytes("RGB", im.size, im.tobytes())  # pixels only; no info/exif/icc carried over
    w, h = clean.size
    if min(w, h) < MIN_SIDE:
        raise ImageRejected("That photo is too small. Please send one at least %d pixels on each side." % MIN_SIDE)
    files = {}
    for width in SIZES + (THUMB,):
        tw = min(width, w)
        th = max(1, round(h * tw / w))
        out = io.BytesIO()
        clean.resize((tw, th), Image.LANCZOS).save(out, "WEBP", quality=80 if width >= 800 else 76, method=4)
        files["thumb" if width == THUMB else str(width)] = out.getvalue()
    return {"w": w, "h": h, "files": files}


# ---------------------------------------------------------------- text
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value, field):
    v = _CTRL.sub("", str(value or "")).strip()
    v = re.sub(r"\s+", " ", v)
    return v[: TEXT_LIMITS[field]]


# ---------------------------------------------------------------- submissions
def handle_submit(content_type: str, body: bytes, ip: str):
    """Returns (status, payload)."""
    if not uploads_active():
        return 404, {"ok": False, "error": "Not found."}
    if not LIMITS.allow("sub-h:" + ip, 5, 3600) or not LIMITS.allow("sub-d:" + ip, 15, 86400):
        return 429, {"ok": False, "error": "Too many submissions from this connection. Please try again later."}
    if not LIMITS.allow("sub-global", 300, 86400):
        return 503, {"ok": False, "error": "Submissions are paused for today. Please try again tomorrow."}
    try:
        form = parse_multipart(content_type, body)
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}
    if form.get("website"):  # honeypot field, hidden from people
        return 400, {"ok": False, "error": "Could not accept that submission."}
    if form.get("consent") not in ("yes", "on", "true", "1"):
        return 400, {"ok": False, "error": "Please confirm you own the photo or have permission to share it."}
    category = (form.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        return 400, {"ok": False, "error": "Please choose Fishing or Coastal Life."}
    if not verify_turnstile(form.get("cf-turnstile-response", ""), ip):
        return 400, {"ok": False, "error": "The spam check did not pass. Please try again."}
    if "_file" not in form or not form["_file"][1]:
        return 400, {"ok": False, "error": "Please choose a photo."}
    try:
        img = process_image(form["_file"][1])
    except ImageRejected as e:
        return 400, {"ok": False, "error": str(e)}
    b = backend()
    pid = str(uuid.uuid4())
    try:
        for name, blob in img["files"].items():
            b.put(b.pending, "%s/%s.webp" % (pid, name), blob, "image/webp")
        b.insert({
            "id": pid, "status": "pending", "category": category,
            "display_name": clean_text(form.get("display_name"), "display_name") or None,
            "species": (clean_text(form.get("species"), "species") or None) if category == "fishing" else None,
            "location": clean_text(form.get("location"), "location") or None,
            "caption": clean_text(form.get("caption"), "caption") or None,
            "width": img["w"], "height": img["h"], "featured": False,
            "consent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip_hash": ip_hash(ip),
        })
    except StorageError as e:
        import sys
        sys.stderr.write("photo submit storage error: %s\n" % e)
        try:
            b.delete(b.pending, ["%s/%s.webp" % (pid, n) for n in img["files"]])
        except Exception:
            pass
        return 502, {"ok": False, "error": "The photo could not be saved right now. Please try again later."}
    return 200, {"ok": True, "status": "pending",
                 "message": "Thanks. Your photo is waiting for review and will appear once it is approved."}


def _public_row(r, b):
    key = lambda n: "%s/%s.webp" % (r["id"], n)
    return {
        "id": r["id"], "category": r.get("category"),
        "w": r.get("width"), "h": r.get("height"),
        "src": {str(s): b.public_url(key(s)) for s in SIZES},
        "thumb": b.public_url(key("thumb")),
        "name": r.get("display_name") or "", "species": r.get("species") or "",
        "location": r.get("location") or "", "caption": r.get("caption") or "",
        "featured": bool(r.get("featured")),
    }


_pub_cache: dict = {}


def public_photos(view: str, featured_only: bool = False):
    b = backend()
    if not b:
        return {"ok": True, "photos": [], "configured": False}
    cat = {"catch": "fishing", "fishing": "fishing", "life": "life"}.get(view)
    ck = (cat, featured_only)
    hit = _pub_cache.get(ck)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        rows = b.select(status="approved", category=cat, featured=True if featured_only else None, limit=300)
        out = {"ok": True, "configured": True, "photos": [_public_row(r, b) for r in rows]}
    except StorageError:
        out = {"ok": False, "photos": [], "error": "Photos are unavailable right now."}
    _pub_cache[ck] = (time.time(), out)
    return out


def _bust_cache():
    _pub_cache.clear()


# ---------------------------------------------------------------- admin auth
def hash_password(pw: str, salt: bytes | None = None) -> str:
    """scrypt$<salt b64>$<hash b64>. Run `python photos.py hash` to make one."""
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def check_password(pw: str, stored: str) -> bool:
    try:
        algo, s, h = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(h))
    except Exception:
        return False


def _sign(payload: str) -> str:
    return hmac.new(_env("PHOTO_SESSION_SECRET").encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session() -> tuple[str, str]:
    exp = str(int(time.time()) + SESSION_TTL)
    csrf = secrets.token_urlsafe(18)
    payload = exp + "." + csrf
    return payload + "." + _sign(payload), csrf


def read_session(cookie_header: str):
    """Returns the CSRF token for a valid session, else None."""
    if not admin_configured():
        return None
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == SESSION_COOKIE and v.count(".") == 2:
            exp, csrf, sig = v.split(".")
            if hmac.compare_digest(sig, _sign(exp + "." + csrf)) and exp.isdigit() and int(exp) > time.time():
                return csrf
    return None


def session_cookie(value: str, clear: bool = False) -> str:
    secure = "" if (backend() and backend().name == "fake") else " Secure;"
    if clear:
        return "%s=; Path=/; Max-Age=0; HttpOnly;%s SameSite=Strict" % (SESSION_COOKIE, secure)
    return "%s=%s; Path=/; Max-Age=%d; HttpOnly;%s SameSite=Strict" % (SESSION_COOKIE, value, SESSION_TTL, secure)


def admin_login(body: bytes, ip: str):
    if not admin_configured():
        return 404, {"ok": False}, None
    if not LIMITS.allow("login:" + ip, 6, 900):
        return 429, {"ok": False, "error": "Too many attempts. Wait 15 minutes."}, None
    try:
        pw = json.loads(body or b"{}").get("password", "")
    except Exception:
        pw = ""
    if not isinstance(pw, str) or not pw or not check_password(pw, _env("PHOTO_ADMIN_PASSWORD_HASH")):
        time.sleep(0.5)
        return 401, {"ok": False, "error": "Wrong password."}, None
    value, csrf = make_session()
    return 200, {"ok": True, "csrf": csrf}, session_cookie(value)


def admin_list(status: str):
    b = backend()
    status = status if status in STATUSES else "pending"
    rows = b.select(status=status, limit=200)
    out = []
    for r in rows:
        item = {k: r.get(k) for k in ("id", "status", "category", "display_name", "species", "location",
                                      "caption", "width", "height", "featured", "created_at", "reviewed_at")}
        if r.get("status") == "approved":
            item["thumb"] = b.public_url("%s/thumb.webp" % r["id"])
            item["preview"] = b.public_url("%s/800.webp" % r["id"])
        elif r.get("status") == "pending":
            item["thumb"] = "/api/admin/image/%s/thumb" % r["id"]
            item["preview"] = "/api/admin/image/%s/800" % r["id"]
        out.append(item)
    return {"ok": True, "status": status, "items": out}


_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def admin_image(pid: str, size: str):
    """Pending images are streamed through the server for a signed-in admin only."""
    if not _ID.match(pid or "") or size not in ("thumb", "400", "800", "1600"):
        return None
    try:
        return backend().get(backend().pending, "%s/%s.webp" % (pid, size))
    except StorageError:
        return None


def _names():
    return ["thumb"] + [str(s) for s in SIZES]


def admin_action(body: bytes):
    b = backend()
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return 400, {"ok": False, "error": "Bad request."}
    pid, action = req.get("id", ""), req.get("action", "")
    if not _ID.match(pid):
        return 400, {"ok": False, "error": "Bad id."}
    rows = b.select(row_id=pid, limit=1)
    if not rows:
        return 404, {"ok": False, "error": "Not found."}
    row = rows[0]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    keys = ["%s/%s.webp" % (pid, n) for n in _names()]
    try:
        if action == "edit":
            fields = {}
            if "category" in req:
                if req["category"] not in CATEGORIES:
                    return 400, {"ok": False, "error": "Bad category."}
                fields["category"] = req["category"]
            for f in ("caption", "species", "display_name", "location"):
                if f in req:
                    fields[f] = clean_text(req[f], f) or None
            if fields.get("category", row.get("category")) != "fishing":
                fields["species"] = None
            if "featured" in req:
                fields["featured"] = bool(req["featured"]) and row.get("status") == "approved"
            b.update(pid, fields)
        elif action == "approve":
            if row.get("status") != "pending":
                return 409, {"ok": False, "error": "Only pending photos can be approved."}
            for k in keys:  # copy pending -> public bucket, then delete the private copy
                b.put(b.approved, k, b.get(b.pending, k), "image/webp")
            b.update(pid, {"status": "approved", "reviewed_at": now})
            b.delete(b.pending, keys)
        elif action == "reject":
            if row.get("status") != "pending":
                return 409, {"ok": False, "error": "Only pending photos can be rejected."}
            b.delete(b.pending, keys)
            b.update(pid, {"status": "rejected", "reviewed_at": now, "featured": False})
        elif action == "remove":
            if row.get("status") != "approved":
                return 409, {"ok": False, "error": "Only published photos can be removed."}
            b.update(pid, {"status": "removed", "reviewed_at": now, "featured": False})
            b.delete(b.approved, keys)
        else:
            return 400, {"ok": False, "error": "Unknown action."}
    except StorageError as e:
        import sys
        sys.stderr.write("photo admin storage error: %s\n" % e)
        return 502, {"ok": False, "error": "Storage error. Nothing was published; try again."}
    _bust_cache()
    return 200, {"ok": True}


if __name__ == "__main__":
    import getpass
    import sys
    if sys.argv[1:] == ["hash"]:
        pw = getpass.getpass("New admin password (16+ characters): ")
        if len(pw) < 16:
            sys.exit("Use at least 16 characters.")
        if pw != getpass.getpass("Repeat: "):
            sys.exit("Passwords did not match.")
        print(hash_password(pw))
    elif sys.argv[1:] == ["secret"]:
        print(secrets.token_urlsafe(48))
    elif sys.argv[1:] == ["check"]:
        # Setup self-test: reads env, never prints keys. Writes and deletes one tiny test object.
        b = backend()
        print("flag PHOTO_UPLOADS_ENABLED:", "on" if flag_on() else "off")
        print("backend:", b.name if b else "NOT CONFIGURED (SUPABASE_URL / SUPABASE_SECRET_KEY)")
        print("turnstile keys:", "set" if (_env("TURNSTILE_SITE_KEY") and _env("TURNSTILE_SECRET_KEY")) else "MISSING")
        print("admin password hash:", "set" if _env("PHOTO_ADMIN_PASSWORD_HASH").startswith("scrypt$") else "MISSING")
        print("session secret:", "set" if len(_env("PHOTO_SESSION_SECRET")) >= 32 else "MISSING or too short")
        try:
            import PIL  # noqa: F401
            print("Pillow: installed")
        except ImportError:
            print("Pillow: MISSING (build command must install requirements-photos.txt)")
        if b:
            try:
                b.select(limit=1)
                print("table: reachable")
                key = "_selftest/%s.webp" % uuid.uuid4()
                b.put(b.pending, key, b"selftest", "image/webp")
                ok = b.get(b.pending, key) == b"selftest"
                b.delete(b.pending, [key])
                print("pending bucket write/read/delete:", "ok" if ok else "MISMATCH")
                try:
                    with urlopen(Request(b.url + "/storage/v1/object/public/%s/%s" % (b.pending, key)), timeout=10) as r:
                        print("WARNING: pending bucket answered a public URL with", r.status)
                except HTTPError as e:
                    print("pending bucket is private: public URL refused (%s)" % e.code)
            except StorageError as e:
                print("storage error:", str(e)[:200])
        print("uploads active:", uploads_active(), "| admin page:", admin_configured())
    else:
        print("usage: python photos.py hash | secret | check")
