"""Visitor feedback for the invited soft launch. Presentation and a small storage interface.

Storage: when the Catch Wall's Supabase backend is configured (SUPABASE_URL plus the
server-side secret key, see photos.backend()), each submission is written as a private
JSON object under feedback/ in the existing private pending bucket (SupabaseFeedbackStore;
approved by Ed on Nov 16, 2026). Otherwise (local dev, tests) it falls back to a local
JSON file (JsonFileStore). Feedback is never publicly readable. Public pages get an
unobtrusive Feedback button; submissions are reviewed inside the existing
password-protected /admin.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = ROOT / "data" / "feedback.json"
MAX_FIELD = 2000
MAX_EMAIL = 120
MAX_PAGE = 200
RATE_PER_HOUR = 5
HONEYPOT = "website"
FIELDS = ("like", "confusing", "missing", "bugs")
FIELD_LABELS = {
    "like": "What do you like?",
    "confusing": "What's confusing?",
    "missing": "What's missing?",
    "bugs": "Bugs or wrong information",
    "email": "Email (optional)",
}
SENT = "Thank you. Your feedback was received."
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PAGE_RE = re.compile(r"^/[\w./?=&%+\-]{0,199}$")


def _esc(s, quote: bool = False) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(
        '"' if quote else "\0", "&quot;" if quote else "\0")


class FeedbackStore(Protocol):
    """Small storage interface. Swap the JSON file for another backend later."""

    def save(self, rec: dict) -> dict: ...
    def list(self) -> list[dict]: ...


class JsonFileStore:
    """Local JSON file. Not for production once a hosted store is chosen."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.environ.get("FEEDBACK_PATH") or DEFAULT_PATH)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError):
            return []
        return list(raw) if isinstance(raw, list) else []

    def save(self, rec: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            items = self._load()
            items.append(rec)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(items, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self.path)
        return rec

    def list(self) -> list[dict]:
        with self._lock:
            items = self._load()
        items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return items


class SupabaseFeedbackStore:
    """One private JSON object per submission under feedback/ in the Catch Wall's private
    pending bucket, using the same server-side Supabase client as photos.py."""

    PREFIX = "feedback"
    MAX_LIST = 200
    CTYPE = "image/webp"

    def __init__(self, backend):
        self.b = backend
        self.bucket = backend.pending

    def _check_private(self) -> None:
        # Never write feedback into a bucket that is publicly readable.
        if self.b.bucket_public(self.bucket) is True:
            raise RuntimeError("feedback bucket is public; refusing to store feedback there")

    def save(self, rec: dict) -> dict:
        self._check_private()
        stamp = (rec.get("created_at") or "").replace("-", "").replace(":", "").replace("+0000", "Z")
        key = "%s/%s-%s.json" % (self.PREFIX, stamp[:15] or "unknown", rec.get("id") or uuid.uuid4())
        # The private pending bucket only accepts image/webp (allowed_mime_types, see
        # docs/PHOTO_UPLOADS_SETUP.md). Rather than change bucket config, the JSON bytes are
        # sent under that declared type; the object stays private and is parsed as JSON on read.
        self.b.put(self.bucket, key, json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                   self.CTYPE)
        return rec

    def list(self) -> list[dict]:
        body = self.b._req(
            "POST", "/storage/v1/object/list/%s" % self.bucket,
            json.dumps({"prefix": self.PREFIX, "limit": self.MAX_LIST, "offset": 0,
                        "sortBy": {"column": "name", "order": "desc"}}).encode(),
            {"Content-Type": "application/json"})[1]
        try:
            names = [o.get("name") for o in json.loads(body or b"[]") if isinstance(o, dict)]
        except ValueError:
            names = []
        items = []
        for name in names:
            if not name or not name.endswith(".json"):
                continue
            try:
                rec = json.loads(self.b.get(self.bucket, "%s/%s" % (self.PREFIX, name)) or b"{}")
            except ValueError:
                continue
            if isinstance(rec, dict):
                items.append(rec)
        items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return items


def _default_store() -> FeedbackStore:
    try:
        import photos
        b = photos.backend()
    except Exception:  # noqa: BLE001 - never let storage discovery break the form
        b = None
    if b is not None and getattr(b, "name", "") == "supabase":
        return SupabaseFeedbackStore(b)
    return JsonFileStore()


_store: FeedbackStore | None = None
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def set_store(store: FeedbackStore | None) -> None:
    """Tests inject a store; None restores the default (Supabase if configured, else JSON)."""
    global _store
    _store = store


def store() -> FeedbackStore:
    return _store if _store is not None else _default_store()


def _trim(s, n: int) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\x00", "")).strip()[:n]


def validate(data: dict) -> tuple[dict | None, str]:
    """Server-side validation. Returns (clean, error). clean is None on failure."""
    if _trim(data.get(HONEYPOT) or "", 200):
        return None, "honeypot"
    out = {k: _trim(data.get(k) or "", MAX_FIELD) for k in FIELDS}
    # keep newlines in the long fields
    for k in FIELDS:
        raw = (data.get(k) or "").replace("\x00", "").strip()
        out[k] = raw[:MAX_FIELD]
    if not any(out[k] for k in FIELDS):
        return None, "Please fill in at least one field."
    email = _trim(data.get("email") or "", MAX_EMAIL)
    if email and not EMAIL_RE.match(email):
        return None, "Enter an email like name@example.com, or leave it blank."
    out["email"] = email
    page = (data.get("page") or "").strip()[:MAX_PAGE]
    if page and not PAGE_RE.match(page.split("#")[0]):
        page = ""
    out["page"] = page or "/"
    return out, ""


def rate_ok(ip: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    ip = (ip or "")[:64] or "unknown"
    with _hits_lock:
        hits = [t for t in _hits.get(ip, []) if now - t < 3600]
        if len(hits) >= RATE_PER_HOUR:
            _hits[ip] = hits
            return False
        hits.append(now)
        _hits[ip] = hits
        return True


def reset_rate() -> None:
    with _hits_lock:
        _hits.clear()


def _ip_tag(ip: str) -> str:
    """Salted hash (same as Catch Wall submissions) so stored feedback holds no raw IPs."""
    try:
        import photos
        return "h:" + photos.ip_hash((ip or "")[:64])
    except Exception:  # noqa: BLE001
        return ""


def submit(data: dict, ip: str, ua: str = "") -> tuple[int, dict]:
    """Validate, rate-limit and store. A filled honeypot looks like success and is dropped."""
    clean, err = validate(data)
    if err == "honeypot":
        return 200, {"ok": True, "message": SENT}
    if err:
        return 400, {"ok": False, "error": err}
    if not rate_ok(ip):
        return 429, {"ok": False, "error": "Please wait before sending more feedback."}
    rec = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ip": _ip_tag(ip),
        "ua": (ua or "")[:200],
        **clean,
    }
    try:
        store().save(rec)
    except Exception as e:  # noqa: BLE001 - OSError, photos.StorageError, private-bucket guard
        import sys
        sys.stderr.write("feedback save failed: %s %s\n" % (type(e).__name__, str(e)[:300]))
        return 503, {"ok": False, "error": "Feedback could not be saved right now."}
    return 200, {"ok": True, "message": SENT, "id": rec["id"]}


def parse_body(content_type: str, body: bytes) -> dict:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if not body:
        return {}
    if ctype == "application/json":
        try:
            obj = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return obj if isinstance(obj, dict) else {}
    if ctype in ("application/x-www-form-urlencoded", "text/plain"):
        q = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        return {k: (v[-1] if v else "") for k, v in q.items()}
    return {}


def admin_list() -> dict:
    items = []
    try:
        rows = store().list()
    except Exception as e:  # noqa: BLE001
        import sys
        sys.stderr.write("feedback list failed: %s %s\n" % (type(e).__name__, str(e)[:300]))
        return {"ok": False, "error": "Feedback storage error.", "items": []}
    for r in rows:
        items.append({k: r.get(k, "") for k in (
            "id", "created_at", "ip", "ua", "page", "email", *FIELDS)})
    return {"ok": True, "items": items}


# --------------------------------------------------------------------------- markup

BUTTON = (
    '<button type="button" class="fb-open" data-feedback-open aria-haspopup="dialog" '
    'aria-controls="fb-dlg">Feedback</button>'
)

FORM_FIELDS = """
<div class="fb-f"><label for="fb-like">What do you like?</label>
<textarea id="fb-like" name="like" rows="3" maxlength="%(max)d"></textarea></div>
<div class="fb-f"><label for="fb-conf">What\u2019s confusing?</label>
<textarea id="fb-conf" name="confusing" rows="3" maxlength="%(max)d"></textarea></div>
<div class="fb-f"><label for="fb-miss">What\u2019s missing?</label>
<textarea id="fb-miss" name="missing" rows="3" maxlength="%(max)d"></textarea></div>
<div class="fb-f"><label for="fb-bugs">Bugs or wrong information</label>
<textarea id="fb-bugs" name="bugs" rows="3" maxlength="%(max)d"></textarea></div>
<div class="fb-f"><label for="fb-email">Email <span class="fb-opt">(optional, only if you want a reply)</span></label>
<input id="fb-email" name="email" type="email" autocomplete="email" inputmode="email" maxlength="%(em)d" aria-describedby="fb-email-err">
<p class="fb-err" id="fb-email-err" hidden>Enter an email like name@example.com, or leave it blank.</p></div>
""" % {"max": MAX_FIELD, "em": MAX_EMAIL}


def _form_inner(page_value: str = "", action: str = "/feedback") -> str:
    return """
<p id="fb-d" class="fb-d">Tell us what works and what doesn\u2019t. Fill in any of the fields \u2014 only one is needed.</p>
<div class="fb-hp" aria-hidden="true">
<label for="fb-website">Company</label>
<input id="fb-website" name="%(hp)s" type="text" tabindex="-1" autocomplete="off"></div>
%(fields)s
<input type="hidden" id="fb-page" name="page" value="%(page)s">
<p class="fb-err" id="fb-form-err" hidden></p>
<div class="fb-act"><button type="submit" class="fb-send">Send feedback</button>
<button type="button" class="fb-cancel" data-feedback-close>Cancel</button></div>
<p class="fb-done" id="fb-done" role="status" aria-live="polite" tabindex="-1" hidden></p>
""" % {"hp": HONEYPOT, "fields": FORM_FIELDS, "page": _esc(page_value, True)}


DIALOG = """<dialog class="fb" id="fb-dlg" aria-labelledby="fb-h" aria-describedby="fb-d">
<form class="fb-form" id="fb-form" method="post" action="/feedback" novalidate>
<div class="fb-head"><h2 id="fb-h" class="fb-h">Send feedback</h2>
<button type="button" class="fb-x" data-feedback-close aria-label="Close feedback form">\u00d7</button></div>
%s
</form></dialog>""" % _form_inner()


JS = r"""(function(){
var d=document.getElementById('fb-dlg');
var f=document.getElementById('fb-form'); if(!f)return;
var done=document.getElementById('fb-done'), opener=null;
var em=document.getElementById('fb-email'), emErr=document.getElementById('fb-email-err');
var formErr=document.getElementById('fb-form-err');
var fields=['fb-like','fb-conf','fb-miss','fb-bugs'].map(function(id){return document.getElementById(id);}).filter(Boolean);
function emailBad(){var v=(em&&em.value||'').trim();return !!v&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);}
function anyField(){return fields.some(function(x){return (x.value||'').trim();});}
function showErr(el,box,bad){if(!box)return;box.hidden=!bad;if(el){if(bad)el.setAttribute('aria-invalid','true');else el.removeAttribute('aria-invalid');}}
function open(e){opener=e.currentTarget;f.reset();if(done){done.hidden=true;done.textContent='';}
  showErr(em,emErr,false);if(formErr){formErr.hidden=true;formErr.textContent='';}
  [].forEach.call(f.querySelectorAll('input,textarea,.fb-send'),function(x){x.disabled=false;});
  var pg=document.getElementById('fb-page'); if(pg) pg.value=location.pathname+location.search;
  if(d&&d.showModal){d.showModal(); (document.getElementById('fb-like')||f.querySelector('textarea,input')).focus();}
  else {location.href='/feedback?from='+encodeURIComponent(location.pathname+location.search);}
}
[].forEach.call(document.querySelectorAll('[data-feedback-open]'),function(b){b.addEventListener('click',open);});
if(d){
  [].forEach.call(d.querySelectorAll('[data-feedback-close]'),function(b){b.addEventListener('click',function(){d.close();});});
  d.addEventListener('close',function(){if(opener&&opener.focus)opener.focus();});
  d.addEventListener('click',function(e){if(e.target===d)d.close();});
  d.addEventListener('keydown',function(e){
    if(e.key==='Escape'){e.preventDefault();d.close();return;}
    if(e.key!=='Tab')return;
    var fs=[].filter.call(d.querySelectorAll('button,input,textarea'),function(x){return !x.disabled&&!x.hidden&&x.closest('.fb-hp')===null&&x.offsetParent!==null;});
    if(!fs.length)return;var a=fs[0],z=fs[fs.length-1];
    if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus();}
    else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus();}});
}
f.addEventListener('submit',function(e){
  e.preventDefault();
  showErr(em,emErr,emailBad());
  if(!anyField()){if(formErr){formErr.hidden=false;formErr.textContent='Please fill in at least one field.';} (fields[0]||em).focus();return;}
  if(emailBad()){em.focus();return;}
  if(formErr){formErr.hidden=true;formErr.textContent='';}
  var body={page:(document.getElementById('fb-page')||{}).value|| (location.pathname+location.search)};
  fields.forEach(function(x){body[x.name]=x.value;});
  if(em) body.email=em.value;
  var hp=document.getElementById('fb-website'); if(hp) body[hp.name]=hp.value;
  var send=f.querySelector('.fb-send'); if(send) send.disabled=true;
  fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(body)})
    .then(function(r){return r.json().then(function(j){j._ok=r.ok;return j;});})
    .then(function(j){
      if(!j.ok){if(send)send.disabled=false;if(formErr){formErr.hidden=false;formErr.textContent=j.error||'Could not send.'; }return;}
      [].forEach.call(f.querySelectorAll('input,textarea,.fb-send'),function(x){x.disabled=true;});
      if(done){done.textContent=j.message||'Thank you. Your feedback was received.';done.hidden=false;done.focus();}
      f.classList.add('is-sent');
    })
    .catch(function(){if(send)send.disabled=false;if(formErr){formErr.hidden=false;formErr.textContent='Could not send right now.';}});
});
})();
"""

CSS = """
/* Visitor feedback */
.fb-open,.fb-fab{appearance:none;display:inline-flex;align-items:center;justify-content:center;min-height:44px;min-width:44px;padding:0 14px;border:1px solid rgba(217,190,134,.7);border-radius:999px;
  background:transparent;color:inherit;font:600 .82rem/1 var(--f-ui,system-ui);letter-spacing:.04em;cursor:pointer;text-decoration:none}
.fb-open:hover,.fb-fab:hover{background:rgba(196,163,106,.18)}
.fb-open:focus-visible,.fb-fab:focus-visible{outline:3px solid #D9BE86;outline-offset:2px}
.ft .fb-open{margin:8px 0 4px;color:#F3EEE3;border-color:rgba(217,190,134,.7)}
.fb-fab{position:fixed;right:max(12px,env(safe-area-inset-right));bottom:max(12px,env(safe-area-inset-bottom));z-index:8;
  background:#071C29;color:#F6F1E7;border-color:rgba(196,163,106,.85);box-shadow:0 8px 20px -12px rgba(4,14,22,.7)}
html[data-page="feedback"] .fb-fab{display:none}
/* Phones: a slim tab on the right edge instead of a 92x44 pill, so it sits over the page gutter and
   not over readings or photos (launch audit item 10). Still always visible; 24x96 tap area. */
@media (max-width:639px){
  .fb-fab{right:0;bottom:max(96px,calc(env(safe-area-inset-bottom) + 84px));min-width:0;min-height:0;width:24px;height:96px;padding:0;
    border-left:0;writing-mode:vertical-rl;transform:rotate(180deg);border-radius:0 8px 8px 0;
    font-size:.72rem;letter-spacing:.08em}
}
.fb{width:min(560px,calc(100vw - 24px));max-height:calc(100dvh - 24px);padding:0;border:1px solid #29506B;border-radius:8px;background:var(--paper,#FFFDF8);color:var(--ink,#102030);
  box-shadow:0 24px 60px -20px rgba(4,14,22,.6)}
.fb::backdrop{background:rgba(4,14,22,.62)}
.fb-form{padding:16px 18px 18px;display:grid;gap:12px;overflow:auto;max-height:calc(100dvh - 24px)}
.fb-head{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:3px double var(--brass,#A7864F);padding-bottom:8px}
.fb-h{font:600 1.35rem/1.15 var(--f-display,Georgia,serif);margin:0}
.fb-x{appearance:none;width:44px;height:44px;border:1px solid var(--line-2,#C9D4D6);border-radius:999px;background:transparent;color:inherit;font:600 1.3rem/1 var(--f-ui,system-ui);cursor:pointer}
.fb-d{font-size:.92rem;color:var(--ink-2,#40596A);margin:0}
.fb-f{display:grid;gap:4px}
.fb-f label{font:700 .86rem/1.2 var(--f-ui,system-ui);color:inherit}
.fb-opt{font-weight:500;color:var(--ink-2,#40596A)}
.fb-f input,.fb-f textarea{width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--line-2,#C9D4D6);border-radius:6px;background:var(--page,#F7F3EA);color:inherit;font:400 1rem/1.4 var(--f-ui,system-ui);box-sizing:border-box}
.fb-f textarea{resize:vertical;min-height:88px}
.fb-f input:focus-visible,.fb-f textarea:focus-visible,.fb-x:focus-visible,.fb-send:focus-visible,.fb-cancel:focus-visible{outline:3px solid var(--brass,#A7864F);outline-offset:2px}
.fb-f [aria-invalid="true"]{border-color:#8E1B12;box-shadow:0 0 0 1px #8E1B12}
.fb-err{font:600 .86rem/1.3 var(--f-ui,system-ui);color:#8E1B12;margin:0}
.fb-hp{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}
.fb-act{display:flex;gap:10px;flex-wrap:wrap}
.fb-send,.fb-cancel{appearance:none;min-height:44px;min-width:96px;padding:0 18px;border-radius:6px;font:700 .95rem/1 var(--f-ui,system-ui);cursor:pointer}
.fb-send{border:1px solid #071C29;background:#0E3A57;color:#FFFDF8}
.fb-send:disabled{opacity:.55;cursor:default}
.fb-cancel{border:1px solid var(--line-2,#C9D4D6);background:transparent;color:inherit}
.fb-done{padding:10px 12px;border-left:4px solid #1F6E66;background:#E8F3EF;color:#102030;font:600 .92rem/1.4 var(--f-ui,system-ui);margin:0}
.fb-done:focus{outline:2px solid var(--brass,#A7864F);outline-offset:2px}
.fb-form.is-sent .fb-f,.fb-form.is-sent .fb-act,.fb-form.is-sent .fb-d{display:none}
.fb-page{max-width:640px;margin:0 auto;padding:20px 16px 48px}
.fb-page .fb-form{padding:0;max-height:none;overflow:visible}
.fb-page .fb-cancel{display:none}
@media (prefers-color-scheme:dark){
  .fb-fab{background:#0A2133;color:#F6F1E7}
  .fb-done{background:#14352C;color:#E8F3EF;border-left-color:#7CB8A4}
  .fb-err{color:#FFB4AB}
}
"""


def embed_html() -> str:
    """Button (footer + fixed), dialog, styles and script. Safe to drop into any public page."""
    fab = ('<button type="button" class="fb-fab" data-feedback-open aria-haspopup="dialog" '
           'aria-controls="fb-dlg">Feedback</button>')
    return BUTTON + fab + DIALOG + "<style id=\"fb-css\">" + CSS.replace("</", "<\\/") + "</style>\n<script>" + JS + "</script>"


def footer_button() -> str:
    return BUTTON


def page_html(sent: bool = False, error: str = "", values: dict | None = None) -> bytes:
    """Standalone /feedback page, including the sent state, with the standard section nav."""
    import site_chrome
    values = values or {}
    if sent:
        body = (
            '<main class="fb-page" id="main"><h1 class="fb-h">Send feedback</h1>'
            '<p class="fb-done" id="fb-done" role="status" tabindex="-1">%s</p>'
            '<p><a class="fb-open" href="/">Back to The Coastal Brief</a></p></main>'
        ) % _esc(SENT)
    else:
        err = ('<p class="fb-err" role="alert">%s</p>' % _esc(error)) if error else ""
        filled = FORM_FIELDS
        for name in (*FIELDS, "email"):
            val = _esc(values.get(name) or "")
            if name == "email":
                filled = filled.replace(
                    'id="fb-email" name="email"',
                    'id="fb-email" name="email" value="%s"' % val, 1)
            else:
                # insert value into the matching textarea
                key = 'name="%s"' % name
                filled = filled.replace(
                    key + " rows",
                    key + " rows", 1)
                filled = re.sub(
                    r'(name="%s" rows="3" maxlength="\d+">)' % name,
                    r"\1" + val, filled, count=1)
        inner = _form_inner(values.get("page") or "/")
        # reuse dialog field markup inside a visible form
        body = (
            '<main class="fb-page" id="main"><h1 class="fb-h" id="fb-h">Send feedback</h1>%s'
            '<form class="fb-form" id="fb-form" method="post" action="/feedback" novalidate>'
            '%s</form></main>'
        ) % (err, inner)
    html = """<!DOCTYPE html>
<html lang="en" data-page="feedback">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>Send feedback \u2014 The Coastal Brief</title>
<meta name="description" content="Send feedback on The Coastal Brief.">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
<style>
:root{--paper:#FFFDF8;--page:#F7F3EA;--ink:#102030;--ink-2:#40596A;--brass:#A7864F;--line-2:#C9D4D6;--f-ui:"Source Sans 3",source-sans-3,system-ui,sans-serif;--f-display:Fraunces,Georgia,serif}
html,body{margin:0;background:var(--page);color:var(--ink);font:16px/1.4 var(--f-ui)}
a.skip{position:absolute;left:-999px}
a.skip:focus{left:12px;top:12px;background:#fff;padding:8px;z-index:10}
%s
%s
</style>
</head>
<body>
<a class="skip" href="#main">Skip to feedback form</a>
%s
%s
<script>%s</script>
</body>
</html>
""" % (site_chrome.NAV_CSS, CSS.replace("</", "<\\/"), site_chrome.nav_html(), body, JS)
    return html.encode("utf-8")
