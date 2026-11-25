"""Vælg opskrifter og byg en indkøbsliste ud fra din profil."""

from __future__ import annotations

import math
import random
import re
from concurrent.futures import ThreadPoolExecutor

from .history import Profile, ProductStat, words
from .models import Product
from .recipes import RECIPES, Recipe

MAIN_KEYWORDS = {
    "kylling": ["kylling"],
    "okse": ["oksekød", "okse", "hakket oksekød", "bøf"],
    "svin": ["svinekød", "svin", "bacon", "skinke", "mørbrad", "flæsk", "pølse"],
    "fisk": ["laks", "torsk", "rejer", "fisk", "tun", "sej", "rødspætte"],
}

PREFERENCES = {
    "vegetar": ("Kun vegetar", lambda r: r.main == "vegetar"),
    "ingen-svin": ("Ingen svinekød", lambda r: r.main != "svin"),
    "hurtig": ("Højst 30 min", lambda r: 0 < r.minutes <= 30),
    "børnevenlig": ("Børnevenlig", lambda r: "børnevenlig" in r.tags),
}


# ---------- opskrifter ----------

def main_preferences(profile: Profile | None) -> dict[str, float]:
    """Hvor meget af hver hovedingrediens køber du? Værdier 0..1."""
    if not profile or not profile.order_count:
        return {k: 0.5 for k in [*MAIN_KEYWORDS, "vegetar"]}
    counts = {k: 0 for k in MAIN_KEYWORDS}
    for p in profile.products:
        name_words = " ".join(words(p.name))
        for main, kws in MAIN_KEYWORDS.items():
            if any(kw in name_words for kw in kws):
                counts[main] += p.orders
    top = max(counts.values()) or 1
    prefs = {k: v / top for k, v in counts.items()}
    # Vegetar: lidt bonus, hvis du sjældent køber kød.
    prefs["vegetar"] = max(0.3, 1 - max(prefs.values())) if top > 1 else 0.5
    return prefs


def score_recipe(recipe: Recipe, profile: Profile | None, main_pref: dict[str, float]) -> tuple[float, list[str]]:
    """Point for, hvor godt en opskrift passer til det, du plejer at købe."""
    reasons: list[str] = []
    core = [i for i in recipe.ingredients if not i.pantry]
    affinity = 0.0
    if profile and core:
        hits = []
        for ing in core:
            m = profile.best_match(ing.name)
            if m:
                hits.append(m)
        affinity = sum(min(1.0, m.share * 2) for m in hits) / len(core)
        reasons = [m.name for m in sorted(hits, key=lambda m: -m.orders)[:3]]
    score = 0.6 * affinity + 0.3 * main_pref.get(recipe.main, 0.3)
    return score, reasons


def suggest(
    profile: Profile | None,
    count: int = 5,
    prefs: list[str] | None = None,
    exclude: list[str] | None = None,
    pool: list[Recipe] | None = None,
    seed: int | None = None,
) -> list[dict]:
    """Foreslå `count` retter. Varierer hovedingrediensen."""
    rng = random.Random(seed)
    exclude_set = set(exclude or [])
    candidates = [r for r in (pool or RECIPES) if r.id not in exclude_set]
    for key in prefs or []:
        if key in PREFERENCES:
            candidates = [r for r in candidates if PREFERENCES[key][1](r)]

    main_pref = main_preferences(profile)
    scored = []
    for r in candidates:
        s, reasons = score_recipe(r, profile, main_pref)
        scored.append([s + rng.random() * 0.25, r, reasons])

    chosen: list[dict] = []
    used_mains: dict[str, int] = {}
    while scored and len(chosen) < count:
        best = max(scored, key=lambda x: x[0] - 0.3 * used_mains.get(x[1].main, 0))
        scored.remove(best)
        _, r, reasons = best
        used_mains[r.main] = used_mains.get(r.main, 0) + 1
        d = r.to_dict()
        d["reasons"] = reasons
        chosen.append(d)
    return chosen


# ---------- mængder ----------

SIZE_RE = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|gr|l|ltr|dl|cl|ml|stk)\b", re.I)
UNIT_FACTORS = {"g": ("g", 1), "gr": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "cl": ("ml", 10),
                "dl": ("ml", 100), "l": ("ml", 1000), "ltr": ("ml", 1000), "stk": ("stk", 1)}
COUNT_UNITS = {"dåse", "dåser", "pk", "pakke", "pakker", "pose", "poser", "bdt", "bundt", "glas", "flaske"}


def parse_size(text: str) -> tuple[float, str] | None:
    """'500 g' -> (500, 'g'). '1 l' -> (1000, 'ml'). '2 x 125 g' -> (250, 'g')."""
    m = SIZE_RE.search(text or "")
    if not m:
        return None
    mult = int(m.group(1)) if m.group(1) else 1
    value = float(m.group(2).replace(",", "."))
    base, factor = UNIT_FACTORS[m.group(3).lower()]
    return value * factor * mult, base


def to_base(amount: float | None, unit: str) -> tuple[float, str] | None:
    if amount is None:
        return None
    u = (unit or "").lower().strip(".")
    if u in UNIT_FACTORS:
        base, factor = UNIT_FACTORS[u]
        return amount * factor, base
    if u == "":
        return amount, "stk"
    return None


def compute_quantity(amount: float | None, unit: str, unit_size: str) -> int:
    u = (unit or "").lower().strip(".")
    if u in COUNT_UNITS and amount:
        return max(1, min(12, math.ceil(amount)))
    need = to_base(amount, unit)
    size = parse_size(unit_size)
    if not need or not size or need[1] != size[1] or size[0] <= 0:
        return 1
    return max(1, min(12, math.ceil(need[0] / size[0] - 0.05)))


# ---------- indkøbsliste ----------

def _fmt_amount(amount: float | None, unit: str) -> str:
    if amount is None:
        return ""
    a = round(amount, 1)
    a_txt = str(int(a)) if a == int(a) else str(a).replace(".", ",")
    return f"{a_txt} {unit}".strip()


def aggregate_ingredients(recipes: list[Recipe], persons: int) -> list[dict]:
    """Saml ens ingredienser fra flere retter og skalér til antal personer."""
    items: dict[str, dict] = {}
    for r in recipes:
        factor = persons / (r.servings or 4)
        for ing in r.ingredients:
            key = ing.name.lower().strip()
            amount = ing.amount * factor if ing.amount is not None else None
            if key not in items:
                items[key] = {"name": ing.name, "amount": amount, "unit": ing.unit,
                              "pantry": ing.pantry, "recipes": [r.title]}
                continue
            it = items[key]
            if r.title not in it["recipes"]:
                it["recipes"].append(r.title)
            it["pantry"] = it["pantry"] and ing.pantry
            if amount is not None and it["amount"] is not None and it["unit"] == ing.unit:
                it["amount"] += amount
            elif amount is not None and it["unit"] != ing.unit:
                a, b = to_base(it["amount"], it["unit"]), to_base(amount, ing.unit)
                if a and b and a[1] == b[1]:
                    it["amount"], it["unit"] = a[0] + b[0], a[1]
    for it in items.values():
        it["amount_text"] = _fmt_amount(it["amount"], it["unit"])
    return list(items.values())


def _product_from_stat(s: ProductStat) -> dict:
    return Product(id=s.product_id, name=s.name, price=s.last_price, unit_size=s.unit_size).to_dict()


def _pick(products: list[Product]) -> Product | None:
    available = [p for p in products if p.available]
    return (available or products or [None])[0]


def build_shopping_list(recipes: list[Recipe], persons: int, profile: Profile | None, client) -> dict:
    items = aggregate_ingredients(recipes, persons)

    to_search = []
    for it in items:
        stat = profile.best_match(it["name"]) if profile else None
        if stat:
            it["product"] = _product_from_stat(stat)
            it["source"] = "history"
            it["note"] = f"Du har købt den {stat.orders} gange"
        else:
            to_search.append(it)

    def search(it: dict) -> None:
        try:
            p = _pick(client.search(it["name"], limit=5))
        except Exception:  # noqa: BLE001 - nemlig kan fejle for enkelte søgninger
            p = None
        it["product"] = p.to_dict() if p else None
        it["source"] = "search" if p else "none"
        it["note"] = "Fundet ved søgning" if p else "Ingen vare fundet – søg selv"

    if to_search:
        search(to_search[0])  # første kald sætter sessionen op
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(search, to_search[1:]))

    for it in items:
        p = it.get("product")
        it["quantity"] = compute_quantity(it["amount"], it["unit"], p["unit_size"] if p else "")
        it["checked"] = bool(p) and not it["pantry"]
        if it["pantry"] and p:
            it["note"] = "Har du den i skabet? " + it["note"].lower()

    used_ids = {it["product"]["id"] for it in items if it.get("product")}
    basics = []
    if profile:
        for s in profile.basics():
            if s.product_id in used_ids:
                continue
            last = f" · sidst for {s.days_since_last} dage siden" if s.days_since_last is not None else ""
            basics.append({
                "name": s.name,
                "product": _product_from_stat(s),
                "quantity": s.typical_qty,
                "checked": s.due >= 0.8,
                "due": s.due,
                "note": f"I {s.orders} af {profile.order_count} ordrer{last}",
            })

    items.sort(key=lambda it: (it["pantry"], it["name"]))
    return {"items": items, "basics": basics}
