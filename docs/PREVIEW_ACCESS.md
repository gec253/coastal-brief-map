# Private preview access

Lets Ed (or anyone he gives the key to) see the flagged previews on a phone while the public gets 404.

- Set `PREVIEW_KEY` on Render (Environment tab of the web service; at least 24 characters). The key is never
  in the repo. Without it, everything below returns 404.
- Open `https://thecoastalbrief.com/preview?key=<PREVIEW_KEY>` once in the phone's browser. The server checks
  the key, sets an HttpOnly, Secure, SameSite=Lax cookie `cb_preview` (an HMAC of the key, 60 days), and
  redirects to `/preview` so the key does not stay in the address bar.
- `/preview` then lists: `/lake` (Falls Lake), `/brief?region=crystal-coast|hatteras|falls-lake`,
  `/lab/wind`, `/lab/tiles`. All are `noindex`, `no-store`, and not linked from the public site. The region
  picker still says "Coming soon" for freshwater.
- `/preview?lock=1` removes the cookie. Changing `PREVIEW_KEY` on Render locks out every browser at once.
- A wrong key gets the same 404 as a missing page.
