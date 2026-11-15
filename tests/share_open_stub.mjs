#!/usr/bin/env node
/* Minimal document stub: load catch-wall-public.js, click #share-open, require dialog.open. */
"use strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = fs.readFileSync(path.join(root, "catch-wall-public.js"), "utf8");

function el(tag, attrs = {}) {
  const listeners = Object.create(null);
  const children = [];
  const node = {
    tagName: String(tag).toUpperCase(),
    id: attrs.id || "",
    name: attrs.name || "",
    type: attrs.type || "",
    value: attrs.value == null ? "" : String(attrs.value),
    checked: Boolean(attrs.checked),
    hidden: Boolean(attrs.hidden),
    disabled: false,
    open: false,
    textContent: attrs.textContent || "",
    innerHTML: "",
    offsetParent: {},
    dataset: Object.create(null),
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    style: {},
    files: { length: 0 },
    parentNode: null,
    children,
    attributes: Object.assign({}, attrs),
    getAttribute(n) {
      if (n in this.attributes) return String(this.attributes[n]);
      if (n === "id") return this.id || null;
      return null;
    },
    setAttribute(n, v) {
      this.attributes[n] = String(v);
      if (n === "id") this.id = String(v);
      if (n === "hidden") this.hidden = true;
      if (n === "open") this.open = true;
    },
    removeAttribute(n) {
      delete this.attributes[n];
      if (n === "hidden") this.hidden = false;
      if (n === "open") this.open = false;
    },
    appendChild(c) {
      c.parentNode = this;
      children.push(c);
      return c;
    },
    addEventListener(t, fn) {
      (listeners[t] = listeners[t] || []).push(fn);
    },
    removeEventListener(t, fn) {
      listeners[t] = (listeners[t] || []).filter((x) => x !== fn);
    },
    dispatchEvent(ev) {
      ev.currentTarget = ev.currentTarget || this;
      ev.target = ev.target || this;
      ev.preventDefault = ev.preventDefault || function () {};
      ev.stopPropagation = ev.stopPropagation || function () {};
      (listeners[ev.type] || []).forEach((fn) => fn(ev));
      return true;
    },
    click() {
      this.dispatchEvent({ type: "click" });
    },
    focus() {
      document.activeElement = this;
    },
    showModal() {
      this.open = true;
      this.attributes.open = "";
    },
    close() {
      this.open = false;
      delete this.attributes.open;
    },
    querySelector(sel) {
      return queryAll(this, sel)[0] || null;
    },
    querySelectorAll(sel) {
      return queryAll(this, sel);
    },
  };
  if (attrs.dataset) Object.assign(node.dataset, attrs.dataset);
  return node;
}

function walk(node, acc) {
  acc.push(node);
  (node.children || []).forEach((c) => walk(c, acc));
  return acc;
}

function parseCompound(sel) {
  // Split a compound like input[name=category][value='fishing']:checked
  const tagM = sel.match(/^([a-zA-Z][\w-]*)/);
  const tag = tagM ? tagM[1].toLowerCase() : null;
  const rest = tagM ? sel.slice(tagM[0].length) : sel;
  const attrs = [];
  const re = /\[([^\]]+)\]/g;
  let m;
  while ((m = re.exec(rest))) attrs.push(m[1]);
  const pseudo = (rest.match(/:([a-zA-Z-]+)\s*$/) || [])[1] || null;
  return { tag, attrs, pseudo };
}

function matchAttr(node, spec) {
  // name=category, value='fishing', value="fishing", data-share, href, tabindex
  const eq = spec.indexOf("=");
  if (eq < 0) {
    if (spec === "data-share") return "data-share" in node.attributes || "share" in node.dataset;
    if (spec === "href") return "href" in node.attributes;
    if (spec === "tabindex") return "tabindex" in node.attributes;
    return node.getAttribute(spec) != null;
  }
  let key = spec.slice(0, eq).trim();
  let val = spec.slice(eq + 1).trim();
  if ((val.startsWith("'") && val.endsWith("'")) || (val.startsWith('"') && val.endsWith('"'))) {
    val = val.slice(1, -1);
  }
  if (key === "name") return node.name === val;
  if (key === "value") return String(node.value) === val;
  if (key === "id") return node.id === val;
  return String(node.getAttribute(key) || "") === val;
}

function matchOne(node, compound) {
  const { tag, attrs, pseudo } = parseCompound(compound.trim());
  if (tag && node.tagName.toLowerCase() !== tag) return false;
  if (attrs.some((a) => !matchAttr(node, a))) return false;
  if (pseudo === "checked" && !node.checked) return false;
  if (pseudo === "not([tabindex='-1'])" || (pseudo && pseudo.startsWith("not"))) {
    if (String(node.getAttribute("tabindex") || "") === "-1") return false;
  }
  return true;
}

function queryAll(root, selector) {
  const list = walk(root, []).slice(1); // descendants
  const groups = selector.split(",").map((s) => s.trim()).filter(Boolean);
  const out = [];
  for (const node of list) {
    for (const g of groups) {
      if (g.startsWith("#")) {
        if (node.id === g.slice(1)) out.push(node);
      } else if (matchOne(node, g)) {
        out.push(node);
      }
    }
  }
  return out;
}

const byId = Object.create(null);
function add(tag, attrs) {
  const node = el(tag, attrs);
  if (node.id) byId[node.id] = node;
  return node;
}

const documentElement = el("html", {});
documentElement.getAttribute = function (n) {
  if (n === "data-theme") return this._theme || "light";
  return el("html").getAttribute.call(this, n);
};
documentElement.setAttribute = function (n, v) {
  if (n === "data-theme") this._theme = v;
  this.attributes[n] = String(v);
};

const head = el("head");
const body = el("body");
const document = {
  documentElement,
  head,
  body,
  activeElement: body,
  getElementById(id) {
    return byId[id] || null;
  },
  querySelector(sel) {
    if (sel.startsWith("#")) return byId[sel.slice(1)] || null;
    return queryAll(body, sel)[0] || null;
  },
  querySelectorAll(sel) {
    return queryAll(body, sel);
  },
  createElement(tag) {
    return el(tag);
  },
  addEventListener() {},
};

const shareOpen = add("button", { id: "share-open", type: "button" });
const shareSoon = add("p", { id: "share-soon" });
const dlg = add("dialog", { id: "share-dlg" });
const form = add("form", { id: "share-form" });
const catFish = el("input", { type: "radio", name: "category", value: "fishing" });
const catLife = el("input", { type: "radio", name: "category", value: "life" });
const wtSalt = el("input", { type: "radio", name: "water_type", value: "saltwater" });
const wtFresh = el("input", { type: "radio", name: "water_type", value: "freshwater" });
form.appendChild(catFish);
form.appendChild(catLife);
form.appendChild(wtSalt);
form.appendChild(wtFresh);
form.appendChild(add("div", { id: "sh-species-wrap" }));
form.appendChild(add("select", { id: "sh-region" }));
form.appendChild(add("input", { id: "sh-photo", type: "file", name: "photo" }));
form.appendChild(add("div", { id: "sh-drop" }));
form.appendChild(add("div", { id: "sh-preview", hidden: true }));
form.appendChild(add("img", { id: "sh-preview-img" }));
form.appendChild(add("p", { id: "sh-preview-name" }));
form.appendChild(add("p", { id: "sh-error" }));
form.appendChild(add("input", { id: "sh-name", name: "display_name" }));
form.appendChild(add("button", { id: "sh-submit", type: "submit" }));
dlg.appendChild(form);
dlg.appendChild(add("button", { id: "share-close", type: "button" }));
dlg.appendChild(add("div", { id: "share-done", hidden: true }));
dlg.appendChild(add("button", { id: "share-done-close", type: "button" }));

const lb = add("dialog", { id: "lightbox" });
lb.appendChild(add("img", { id: "lb-img" }));
lb.appendChild(add("div", { id: "lb-caption" }));
lb.appendChild(add("div", { id: "lb-count" }));
lb.appendChild(add("button", { id: "lb-prev", type: "button" }));
lb.appendChild(add("button", { id: "lb-next", type: "button" }));
lb.appendChild(add("button", { id: "lb-close", type: "button" }));
const gallery = add("div", { id: "gallery" });
body.appendChild(add("button", { id: "theme-toggle", type: "button" }));
body.appendChild(shareOpen);
body.appendChild(shareSoon);
body.appendChild(dlg);
body.appendChild(lb);
body.appendChild(gallery);

const window = {
  __CW_BOOT: { view: "catch", water: "all", photos: [] },
  document,
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  addEventListener() {},
  turnstile: undefined,
};
const localStorage = window.localStorage;

async function fetchImpl(url) {
  if (String(url).includes("/api/photos/config")) {
    return {
      ok: true,
      json: async () => ({
        uploads: true,
        regions: [{ id: "neuse", name: "Neuse River" }],
        turnstileSiteKey: "",
      }),
    };
  }
  return { ok: false, json: async () => ({}) };
}

const sandbox = {
  window,
  document,
  localStorage,
  fetch: fetchImpl,
  console,
  setTimeout,
  clearTimeout,
  Node: function Node() {},
};
sandbox.globalThis = sandbox;
sandbox.self = window;
sandbox.window.document = document;

const fn = new Function(
  "window",
  "document",
  "localStorage",
  "fetch",
  "console",
  "setTimeout",
  "clearTimeout",
  "globalThis",
  src + "\n//# sourceURL=catch-wall-public.js",
);
fn(
  window,
  document,
  localStorage,
  fetchImpl,
  console,
  setTimeout,
  clearTimeout,
  sandbox,
);

await new Promise((r) => setTimeout(r, 20));

if (shareOpen.hidden) {
  throw new Error("expected #share-open to become visible after config");
}

let threw = null;
try {
  shareOpen.click();
} catch (e) {
  threw = e;
}
if (threw) {
  console.error("click threw:", threw && threw.stack ? threw.stack : threw);
  process.exit(1);
}
if (!dlg.open) {
  console.error("dialog did not open; open=", dlg.open);
  process.exit(1);
}
console.log("share-open-ok");
