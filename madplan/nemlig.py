"""Klient til nemlig.com.

Login, søgning og kurv kommer fra pakken `nemlig-shopper` (MIT).
Ordrehistorik er tilføjet her. Nemlig.com har ikke et officielt API, så
svarene læses defensivt: vi prøver flere feltnavne.

Klienten lægger kun varer i kurven. Den gennemfører aldrig en bestilling.
Du betaler selv på nemlig.com.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nemlig_shopper.api import NemligAPI, NemligAPIError
from nemlig_shopper.config import API_BASE_URL

from .models import Order, OrderLine, Product

logger = logging.getLogger("madplan")

BASKET_URL = "https://www.nemlig.com/basket"
CACHE_DIR = Path.home() / ".madplan"

__all__ = ["NemligClient", "NemligAPIError", "BASKET_URL", "parse_date"]


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def parse_date(value: Any) -> datetime | None:
    """Læs en dato fra nemlig. Både ISO-tekst og '/Date(ms)/' virker."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
    text = str(value)
    m = re.search(r"/Date\((\d+)", text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            continue
    return None


def _as_list(data: Any, *keys: str) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _as_list(v, *keys)
                if inner:
                    return inner
    return []


def parse_order_list(data: Any) -> list[dict]:
    """Svar fra order/GetBasicOrderHistory -> [{number, date}]."""
    out = []
    for o in _as_list(data, "Orders", "orders", "Items", "Results"):
        number = _first(o, "OrderNumber", "Number", "Id", "OrderId")
        if number is None:
            continue
        date = parse_date(_first(o, "DeliveryTime", "DeliveryDate", "OrderDate", "Date", "Created"))
        out.append({"number": str(number), "date": date})
    return out


def parse_order_lines(data: Any) -> list[OrderLine]:
    """Svar fra order/GetOrderHistory -> [OrderLine]."""
    lines = []
    for line in _as_list(data, "Lines", "OrderLines", "Products", "Items"):
        pid = _first(line, "ProductNumber", "ProductId", "Id")
        name = _first(line, "ProductName", "Name", "Text")
        if pid is None or not name:
            continue
        try:
            qty = float(_first(line, "Quantity", "Amount", "Count", default=1))
        except (TypeError, ValueError):
            qty = 1
        price = _first(line, "Price", "ItemPrice", "UnitPrice")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        lines.append(
            OrderLine(
                product_id=str(pid),
                name=str(name),
                quantity=qty,
                price=price,
                unit_size=str(_first(line, "Description", "UnitSize", default="")),
                category=str(_first(line, "MainGroupName", "Category", "GroupName", default="")),
            )
        )
    return lines


class NemligClient:
    """Tynd indpakning af NemligAPI med ordrehistorik og cache."""

    demo = False

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.api = NemligAPI()
        self.username: str | None = None
        self.cache_dir = cache_dir

    # --- login ---
    def login(self, username: str, password: str) -> None:
        self.api.login(username, password)
        self.username = username

    def is_logged_in(self) -> bool:
        return self.api.is_logged_in()

    # --- ordrehistorik ---
    def _cache_file(self) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", self.username or "anon")
        return self.cache_dir / f"orders_{safe}.json"

    def _load_cache(self) -> dict[str, Order]:
        f = self._cache_file()
        if not f.exists():
            return {}
        try:
            return {o["number"]: Order.from_dict(o) for o in json.loads(f.read_text())}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _save_cache(self, orders: list[Order]) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            f = self._cache_file()
            f.write_text(json.dumps([o.to_dict() for o in orders], ensure_ascii=False))
            f.chmod(0o600)
        except OSError:
            logger.warning("Kunne ikke gemme ordre-cache")

    def _get_json(self, path: str, params: dict) -> Any:
        r = self.api.client.get(f"{API_BASE_URL}/{path}", params=params)
        r.raise_for_status()
        return r.json()

    def get_orders(self, max_orders: int = 20) -> list[Order]:
        """Hent de seneste ordrer med varelinjer.

        Ordrer, der allerede er hentet, ligger i en cache i ~/.madplan.
        """
        if not self.is_logged_in():
            raise NemligAPIError("Du skal logge ind først")
        try:
            summary = parse_order_list(
                self._get_json("order/GetBasicOrderHistory", {"skip": 0, "take": max_orders})
            )
        except Exception as e:  # noqa: BLE001 - uofficielt API
            raise NemligAPIError(f"Kunne ikke hente ordrehistorik: {e}") from e

        cache = self._load_cache()
        missing = [s for s in summary[:max_orders] if s["number"] not in cache]

        def fetch(s: dict) -> Order:
            data = self._get_json("order/GetOrderHistory", {"orderNumber": s["number"]})
            return Order(number=s["number"], date=s["date"], lines=parse_order_lines(data))

        with ThreadPoolExecutor(max_workers=4) as pool:
            for order in pool.map(fetch, missing):
                cache[order.number] = order

        orders = [cache[s["number"]] for s in summary[:max_orders] if s["number"] in cache]
        self._save_cache(list(cache.values()))
        return orders

    # --- produkter og kurv ---
    def search(self, query: str, limit: int = 6) -> list[Product]:
        return [Product.from_api(d) for d in self.api.search_products(query, limit=limit)]

    def add_items(self, items: list[dict]) -> dict:
        return self.api.add_multiple_to_cart(items)

    def get_cart(self) -> dict:
        data = self.api.get_cart()
        lines = [
            {
                "name": line.get("ProductName", "?"),
                "quantity": line.get("Quantity", 1),
                "total": line.get("Total", line.get("Price", 0)),
            }
            for line in data.get("Lines", [])
        ]
        return {
            "lines": lines,
            "count": data.get("NumberOfProducts", len(lines)),
            "total": data.get("TotalProductsPrice", 0),
            "delivery": data.get("DeliveryPrice", 0),
            "delivery_time": data.get("FormattedDeliveryTime", ""),
        }
