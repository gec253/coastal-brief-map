# Private preview access

Lets Ed (or anyone he gives the key to) see still-private labs on a phone, and keeps those pages
available if a public kill switch is on. The Morning Brief and freshwater lake/river pages are public
on their own and do not need this cookie.

- Set `PREVIEW_KEY` on Render (Environment tab of the web service; at least 24 characters). The key is never
  in the repo. Without it, `/preview` and the labs return 404 (the public brief and lake pages stay up).
- Open `https://thecoastalbrief.com/preview?key=<PREVIEW_KEY>` once in the phone's browser. The server checks
  the key, sets an HttpOnly, Secure, SameSite=Lax cookie `cb_preview` (an HMAC of the key, 60 days), and
  redirects to `/preview` so the key does not stay in the address bar.
- `/preview` lists the public lake and brief pages as shortcuts, plus the not-yet-public Wilmington
  and Nags Head dashboards (`/?region=wilmington`, `/?region=nags-head`) and `/lab/wind` and `/lab/tiles`,
  which stay private (`noindex`, `no-store`, not linked from the public site). The public homepage
  region dropdown is unchanged. With the cookie, those two saltwater regions also appear in the
  dashboard picker and their `/api/conditions` responses return 200; without it they 404.
- `/preview?lock=1` removes the cookie. Changing `PREVIEW_KEY` on Render locks out every browser at once.
- A wrong key gets the same 404 as a missing page.
