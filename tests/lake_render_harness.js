// Renders lake.js against a fixture /api/freshwater payload with a tiny DOM stub
// and prints every touched element's state as JSON. Fixture data only.
// usage: node lake_render_harness.js <lake.js> <fixture.json> <regionId>
const fs = require("fs");
const vm = require("vm");
const [src, fixPath, rid] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(fixPath, "utf8"))[rid];
const els = {};
function el(id) {
  if (!els[id]) {
    const cls = new Set();
    els[id] = {
      id, textContent: "", innerHTML: "", hidden: false, style: {}, dataset: { title: id }, attrs: {},
      classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), toggle: (c, on) => (on === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : on ? cls.add(c) : cls.delete(c)), _s: cls },
      _className: "", get className() { return this._className; }, set className(v) { this._className = v; },
      setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; }, getAttribute(k) { return this.attrs[k] || null; },
      addEventListener() {},
    };
  }
  return els[id];
}
const document = { getElementById: el, querySelectorAll: () => [], documentElement: el("__html") };
const ctx = {
  document, console, URL, URLSearchParams, Intl, Date, Math, JSON, String, Number, Promise, Error,
  location: { search: "?region=" + rid, href: "https://example.test/lake?region=" + rid },
  localStorage: { getItem: () => null, setItem() {} },
  fetch: () => Promise.resolve({ json: () => Promise.resolve(payload) }),
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
process.on("beforeExit", () => {
  const out = {};
  for (const id of Object.keys(els).sort()) {
    const e = els[id];
    out[id] = { text: e.textContent, html: e.innerHTML, cls: e.className, list: [...e.classList._s].sort(), hidden: e.hidden, style: e.style, attrs: e.attrs };
  }
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
});
