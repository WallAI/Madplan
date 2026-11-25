"""Analyse af ordrehistorik: hvad køber du, og hvor tit?"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .models import Order

WORD_RE = re.compile(r"[a-zæøåéü]+")


def words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def _stem(word: str) -> str:
    # Enkel dansk stamme: "kartofler" -> "kartof", "tomater" -> "tomat"
    for suffix in ("erne", "ene", "er", "e", "r"):
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _word_hit(term_word: str, name_word: str) -> bool:
    if len(term_word) <= 3:
        return name_word == term_word or (
            name_word.startswith(term_word) and len(name_word) <= len(term_word) + 2
        )
    return _stem(term_word) in name_word


def match_quality(term: str, name: str) -> float:
    """0 = ingen match. Højere = bedre. Alle ord i søgeordet skal findes i navnet."""
    t_words = words(term)
    n_words = words(name)
    if not t_words or not n_words:
        return 0.0
    for tw in t_words:
        if not any(_word_hit(tw, nw) for nw in n_words):
            return 0.0
    # Bonus, hvis navnets første ord er selve varen ("Tomater" og ikke "Hakkede tomater").
    first_hit = any(_word_hit(tw, n_words[0]) for tw in t_words)
    coverage = len(t_words) / len(n_words)
    if not first_hit and len(t_words) == 1:
        return 0.2 * coverage
    return 1.0 + coverage


@dataclass
class ProductStat:
    product_id: str
    name: str
    orders: int = 0
    total_qty: float = 0
    share: float = 0.0
    last_date: str | None = None
    days_since_last: int | None = None
    avg_interval_days: float | None = None
    due: float = 0.0  # >= 1 betyder: "det er tid at købe igen"
    typical_qty: int = 1
    last_price: float | None = None
    unit_size: str = ""
    category: str = ""
    _dates: list[datetime] = field(default_factory=list, repr=False)
    _qtys: list[float] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_dates", None)
        d.pop("_qtys", None)
        return d


@dataclass
class Profile:
    order_count: int
    products: list[ProductStat]
    first_date: str | None = None
    last_date: str | None = None

    def best_match(self, term: str, min_quality: float = 1.0) -> ProductStat | None:
        best, best_key = None, None
        for p in self.products:
            q = match_quality(term, p.name)
            if q < min_quality:
                continue
            key = (q >= 1.0, p.orders, q)
            if best_key is None or key > best_key:
                best, best_key = p, key
        return best

    def basics(self, min_share: float = 0.35, min_orders: int = 2) -> list[ProductStat]:
        """Varer, du køber i mange af dine ordrer."""
        out = [p for p in self.products if p.share >= min_share and p.orders >= min_orders]
        return sorted(out, key=lambda p: (-p.due, -p.share))

    def to_dict(self, top: int = 15) -> dict:
        return {
            "order_count": self.order_count,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "top_products": [p.to_dict() for p in self.products[:top]],
            "basics": [p.to_dict() for p in self.basics()],
        }


def analyze(orders: list[Order], today: datetime | None = None) -> Profile:
    today = today or datetime.now()
    stats: dict[str, ProductStat] = {}
    for order in orders:
        seen: set[str] = set()
        for line in order.lines:
            s = stats.setdefault(line.product_id, ProductStat(line.product_id, line.name))
            s.total_qty += line.quantity
            s._qtys.append(line.quantity)
            if line.product_id not in seen:
                s.orders += 1
                seen.add(line.product_id)
                if order.date:
                    s._dates.append(order.date)
            # Brug de nyeste oplysninger om navn og pris.
            if order.date and (not s.last_date or order.date.isoformat() >= s.last_date):
                s.last_date = order.date.isoformat()
                s.name = line.name
                s.last_price = line.price
                s.unit_size = line.unit_size or s.unit_size
                s.category = line.category or s.category

    n = max(len(orders), 1)
    for s in stats.values():
        s.share = s.orders / n
        s.typical_qty = max(1, round(statistics.median(s._qtys))) if s._qtys else 1
        dates = sorted(set(s._dates))
        if dates:
            s.days_since_last = (today - dates[-1]).days
        if len(dates) >= 2:
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            s.avg_interval_days = max(1.0, statistics.mean(gaps))
            s.due = round((s.days_since_last or 0) / s.avg_interval_days, 2)
        elif s.days_since_last is not None:
            s.due = 0.5

    products = sorted(stats.values(), key=lambda p: (-p.orders, -p.total_qty, p.name))
    dates = sorted(o.date for o in orders if o.date)
    return Profile(
        order_count=len(orders),
        products=products,
        first_date=dates[0].isoformat() if dates else None,
        last_date=dates[-1].isoformat() if dates else None,
    )
