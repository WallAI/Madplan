"""Demo-klient med falske data. Bruges med MADPLAN_DEMO=1.

Den taler ikke med nemlig.com. Den lader dig prøve hele flowet.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from .models import Order, OrderLine, Product

# (navn, størrelse, pris, andel af ordrer, typisk antal)
DEMO_HISTORY = [
    ("Letmælk 1,5%", "1 l", 11.95, 1.0, 2),
    ("Rugbrød, groft", "1000 g", 22.00, 0.9, 1),
    ("Æg, frilands 10 stk", "10 stk", 32.95, 0.8, 1),
    ("Bananer", "5 stk", 15.00, 0.8, 1),
    ("Smør, saltet", "250 g", 21.95, 0.7, 1),
    ("Agurk", "1 stk", 8.00, 0.7, 1),
    ("Skyr naturel", "1000 g", 24.95, 0.6, 1),
    ("Pålægsost 30+", "450 g", 39.95, 0.6, 1),
    ("Hakket oksekød 8-12%", "500 g", 44.95, 0.6, 1),
    ("Gulerødder", "1 kg", 12.00, 0.6, 1),
    ("Æbler, Pink Lady", "6 stk", 25.00, 0.6, 1),
    ("Kyllingebryst", "500 g", 49.95, 0.5, 1),
    ("Spaghetti", "500 g", 9.95, 0.5, 1),
    ("Havregryn, økologisk", "1000 g", 16.95, 0.5, 1),
    ("Hakkede tomater", "400 g", 6.95, 0.5, 2),
    ("Kartofler, faste", "1 kg", 14.95, 0.4, 1),
    ("Løg, gule", "1 kg", 10.00, 0.4, 1),
    ("Creme fraiche 18%", "2 dl", 12.95, 0.4, 1),
    ("Kaffe, formalet", "400 g", 49.00, 0.4, 1),
    ("Laksefilet", "250 g", 49.95, 0.3, 2),
    ("Toiletpapir", "8 stk", 39.95, 0.3, 1),
    ("Parmesan", "100 g", 29.95, 0.2, 1),
    ("Ris, jasmin", "1 kg", 21.95, 0.2, 1),
]


def _pid(name: str) -> str:
    return str(500000 + int(hashlib.md5(name.encode()).hexdigest()[:6], 16) % 400000)


class DemoClient:
    demo = True

    def __init__(self) -> None:
        self.username: str | None = "demo@example.com"
        self._logged_in = True
        self._cart: dict[str, dict] = {}
        self._catalog: dict[str, Product] = {}

    def login(self, username: str, password: str) -> None:
        self.username = username
        self._logged_in = True

    def is_logged_in(self) -> bool:
        return self._logged_in

    def get_orders(self, max_orders: int = 20) -> list[Order]:
        rng = random.Random(42)
        today = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
        orders = []
        for i in range(min(max_orders, 12)):
            date = today - timedelta(days=7 * i + 3)
            lines = [
                OrderLine(_pid(n), n, qty, price, size, "")
                for n, size, price, share, qty in DEMO_HISTORY
                if rng.random() < share
            ]
            orders.append(Order(number=f"DEMO{1000 - i}", date=date, lines=lines))
        return orders

    def search(self, query: str, limit: int = 6) -> list[Product]:
        rng = random.Random(query)
        base = query.strip().capitalize()
        variants = [(base, ""), (f"{base}, økologisk", "øko"), (f"{base}, stor pakke", "")]
        sizes = ["500 g", "1 kg", "250 g", "1 stk", "400 g"]
        out = []
        for name, label in variants[:limit]:
            p = Product(
                id=_pid(name), name=name, price=round(rng.uniform(8, 60), 2),
                unit_size=rng.choice(sizes), available=rng.random() > 0.1,
                is_organic=label == "øko", is_on_discount=rng.random() > 0.8,
            )
            self._catalog[p.id] = p
            out.append(p)
        return out

    def add_items(self, items: list[dict]) -> dict:
        result: dict = {"success": [], "failed": []}
        for it in items:
            pid = str(it.get("product_id"))
            line = self._cart.setdefault(pid, {"name": it.get("name") or pid, "quantity": 0,
                                                "price": it.get("price") or 0})
            line["quantity"] += int(it.get("quantity", 1))
            result["success"].append(pid)
        return result

    def get_cart(self) -> dict:
        lines = [
            {"name": v["name"], "quantity": v["quantity"], "total": round(v["quantity"] * (v["price"] or 0), 2)}
            for v in self._cart.values()
        ]
        return {"lines": lines, "count": sum(v["quantity"] for v in self._cart.values()),
                "total": round(sum(line["total"] for line in lines), 2), "delivery": 29.0,
                "delivery_time": "Demo – ingen levering"}
