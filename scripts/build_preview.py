"""Byg en selvstændig demo-side (én HTML-fil uden server).

Siden er den rigtige brugerflade (madplan/static/index.html). Kald til /api/*
bliver besvaret i browseren med demo-data, som er beregnet af den samme
Python-kode som appen.

Brug:  python scripts/build_preview.py UD.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from madplan.demo import DemoClient
from madplan.history import analyze
from madplan.planner import PREFERENCES, _pick, _product_from_stat, main_preferences, score_recipe
from madplan.recipes import RECIPES

ROOT = Path(__file__).resolve().parents[1]


def build_data() -> dict:
    client = DemoClient()
    profile = analyze(client.get_orders())
    mp = main_preferences(profile)

    recipes = []
    for r in RECIPES:
        score, reasons = score_recipe(r, profile, mp)
        d = r.to_dict()
        d["reasons"] = reasons
        d["base"] = round(score, 4)
        recipes.append(d)

    matches = {}
    for r in RECIPES:
        for ing in r.ingredients:
            key = ing.name.lower().strip()
            if key in matches:
                continue
            stat = profile.best_match(ing.name)
            if stat:
                matches[key] = {"product": _product_from_stat(stat), "source": "history",
                                "note": f"Du har købt den {stat.orders} gange"}
            else:
                p = _pick(client.search(ing.name, limit=5))
                matches[key] = {"product": p.to_dict() if p else None, "source": "search" if p else "none",
                                "note": "Fundet ved søgning" if p else "Ingen vare fundet – søg selv"}

    basics = []
    for s in profile.basics():
        last = f" · sidst for {s.days_since_last} dage siden" if s.days_since_last is not None else ""
        basics.append({"name": s.name, "product": _product_from_stat(s), "quantity": s.typical_qty,
                       "checked": s.due >= 0.8, "due": s.due,
                       "note": f"I {s.orders} af {profile.order_count} ordrer{last}"})

    return {
        "status": {"logged_in": True, "demo": True, "username": "demo",
                   "preferences": {k: v[0] for k, v in PREFERENCES.items()}, "recipe_count": len(RECIPES)},
        "profile": profile.to_dict(),
        "recipes": recipes,
        "matches": matches,
        "basics": basics,
    }


MOCK_JS = r"""
(() => {
const D = window.__MADPLAN_DEMO__;
const cart = new Map();
const json = (data, status = 200) => Promise.resolve(new Response(JSON.stringify(data),
  { status, headers: { "Content-Type": "application/json" } }));
const PREFS = {
  "vegetar": (r) => r.main === "vegetar",
  "ingen-svin": (r) => r.main !== "svin",
  "hurtig": (r) => r.minutes > 0 && r.minutes <= 30,
  "børnevenlig": (r) => r.tags.includes("børnevenlig"),
};
function suggest({ count = 5, prefs = [], exclude = [] }) {
  let c = D.recipes.filter((r) => !exclude.includes(r.id));
  prefs.forEach((k) => { if (PREFS[k]) c = c.filter(PREFS[k]); });
  const scored = c.map((r) => [r.base + Math.random() * 0.25, r]);
  const used = {}; const out = [];
  while (scored.length && out.length < count) {
    let bi = 0, bv = -1e9;
    scored.forEach(([s, r], i) => { const v = s - 0.3 * (used[r.main] || 0); if (v > bv) { bv = v; bi = i; } });
    const [, r] = scored.splice(bi, 1)[0];
    used[r.main] = (used[r.main] || 0) + 1; out.push(r);
  }
  return { recipes: out };
}
const SIZE_RE = /(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|gr|l|ltr|dl|cl|ml|stk)(?![a-zæøå])/i;
const UF = { g: ["g", 1], gr: ["g", 1], kg: ["g", 1000], ml: ["ml", 1], cl: ["ml", 10], dl: ["ml", 100], l: ["ml", 1000], ltr: ["ml", 1000], stk: ["stk", 1] };
const COUNT = new Set(["dåse", "dåser", "pk", "pakke", "pakker", "pose", "poser", "bdt", "bundt", "glas", "flaske"]);
function parseSize(t) { const m = SIZE_RE.exec(t || ""); if (!m) return null;
  const [b, f] = UF[m[3].toLowerCase()]; return [parseFloat(m[2].replace(",", ".")) * f * (m[1] ? +m[1] : 1), b]; }
function toBase(a, u) { if (a == null) return null; u = (u || "").toLowerCase().replace(/\.$/, "");
  if (UF[u]) return [a * UF[u][1], UF[u][0]]; if (u === "") return [a, "stk"]; return null; }
function qty(a, u, size) { u = (u || "").toLowerCase().replace(/\.$/, "");
  if (COUNT.has(u) && a) return Math.max(1, Math.min(12, Math.ceil(a)));
  const n = toBase(a, u), s = parseSize(size);
  if (!n || !s || n[1] !== s[1] || s[0] <= 0) return 1;
  return Math.max(1, Math.min(12, Math.ceil(n[0] / s[0] - 0.05))); }
function fmt(a, u) { if (a == null) return ""; const r = Math.round(a * 10) / 10;
  return `${String(r).replace(".", ",")} ${u}`.trim(); }
function shoppingList({ recipe_ids, persons = 4 }) {
  const items = {};
  recipe_ids.map((id) => D.recipes.find((r) => r.id === id)).filter(Boolean).forEach((r) => {
    const f = persons / (r.servings || 4);
    r.ingredients.forEach((g) => {
      const k = g.name.toLowerCase().trim(); const a = g.amount != null ? g.amount * f : null;
      const it = items[k];
      if (!it) { items[k] = { name: g.name, amount: a, unit: g.unit, pantry: g.pantry, recipes: [r.title] }; return; }
      if (!it.recipes.includes(r.title)) it.recipes.push(r.title);
      it.pantry = it.pantry && g.pantry;
      if (a != null && it.amount != null && it.unit === g.unit) it.amount += a;
      else if (a != null && it.unit !== g.unit) { const x = toBase(it.amount, it.unit), y = toBase(a, g.unit);
        if (x && y && x[1] === y[1]) { it.amount = x[0] + y[0]; it.unit = x[1]; } }
    });
  });
  const list = Object.values(items).map((it) => {
    const m = D.matches[it.name.toLowerCase().trim()] || { product: null, source: "none", note: "Ingen vare fundet – søg selv" };
    const p = m.product ? { ...m.product } : null;
    const o = { ...it, amount_text: fmt(it.amount, it.unit), product: p, source: m.source, note: m.note };
    o.quantity = qty(it.amount, it.unit, p ? p.unit_size : "");
    o.checked = !!p && !it.pantry;
    if (it.pantry && p) o.note = "Har du den i skabet? " + o.note.toLowerCase();
    return o;
  });
  const used = new Set(list.filter((i) => i.product).map((i) => i.product.id));
  list.sort((a, b) => (a.pantry - b.pantry) || a.name.localeCompare(b.name, "da"));
  return { items: list, basics: D.basics.filter((b) => !used.has(b.product.id)).map((b) => ({ ...b, product: { ...b.product } })) };
}
function hash(s) { let h = 2166136261; for (const ch of s) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function rng(seed) { return () => { seed = (seed + 0x6D2B79F5) >>> 0; let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function search(q, limit) {
  const r = rng(hash(q)); const base = q.trim().charAt(0).toUpperCase() + q.trim().slice(1);
  const sizes = ["500 g", "1 kg", "250 g", "1 stk", "400 g"];
  return { products: [[base, ""], [base + ", økologisk", "øko"], [base + ", stor pakke", ""]].slice(0, limit).map(([name, l]) => ({
    id: String(500000 + hash(name) % 400000), name, price: Math.round((8 + r() * 52) * 100) / 100,
    unit_size: sizes[Math.floor(r() * sizes.length)], brand: "", image_url: "", available: r() > 0.1,
    is_organic: l === "øko", is_on_discount: r() > 0.8 })) };
}
function cartSummary() { const lines = [...cart.values()].map((v) => ({ name: v.name, quantity: v.quantity, total: Math.round(v.quantity * (v.price || 0) * 100) / 100 }));
  return { lines, count: lines.reduce((s, l) => s + l.quantity, 0), total: Math.round(lines.reduce((s, l) => s + l.total, 0) * 100) / 100,
    delivery: 29, delivery_time: "Demo – ingen levering" }; }
window.fetch = (url, opts = {}) => {
  const u = new URL(url, "https://demo.local/"); const body = opts.body ? JSON.parse(opts.body) : {};
  const delay = (v, ms = 350) => new Promise((res) => setTimeout(() => res(v), ms));
  switch (u.pathname) {
    case "/api/status": return json(D.status);
    case "/api/profile": return delay(json(D.profile), 500);
    case "/api/suggest": return delay(json(suggest(body)));
    case "/api/shopping-list": return delay(json(shoppingList(body)), 700);
    case "/api/search": return delay(json(search(u.searchParams.get("q") || "", +(u.searchParams.get("limit") || 8))));
    case "/api/cart":
      if ((opts.method || "GET") === "GET") return json(cartSummary());
      body.items.forEach((it) => { const l = cart.get(it.product_id) || { name: it.name, price: it.price, quantity: 0 };
        l.quantity += it.quantity; cart.set(it.product_id, l); });
      return delay(json({ result: { success: body.items.map((i) => i.product_id), failed: [] }, cart: cartSummary(),
        basket_url: "https://www.nemlig.com/basket" }), 600);
    case "/api/recipes/import": return json({ detail: "Import af opskrifter virker kun i den rigtige app, ikke i denne demo." }, 400);
    case "/api/logout": return json({ ok: true });
    default: return json({ detail: "Ukendt" }, 404);
  }
};
})();
"""


def build(out: Path) -> None:
    html = (ROOT / "madplan/static/index.html").read_text()
    # Artifact-siden får sit eget skelet: fjern doctype/html/head/body.
    head = html[html.index("<title>"):html.index("</head>")]
    body = html[html.index("<body>") + len("<body>"):html.index("</body>")]
    head = head.replace('<meta charset="utf-8">', "").replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1">', "")
    data = json.dumps(build_data(), ensure_ascii=False).replace("</", "<\\/")
    banner = ('<div style="background:var(--warm-soft);color:var(--ink);text-align:center;font-size:14px;'
              'padding-block:8px;padding-left:max(16px, env(safe-area-inset-left, 0px));'
              'padding-right:max(16px, env(safe-area-inset-right, 0px))">'
              'Demo med falske data. Intet bliver sendt til nemlig.com.</div>')
    mock = f"<script>window.__MADPLAN_DEMO__ = {data};</script>\n<script>{MOCK_JS}</script>\n"
    body = body.replace("<script>", mock + "<script>", 1)
    page = ('<meta name="claude:viewport-fit-sides" content="cover">\n' + head.strip() + "\n" + banner + body)
    out.write_text(page)
    print(f"Skrev {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "madplan-demo.html"))
