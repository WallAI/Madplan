"""Fælles datatyper."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class OrderLine:
    product_id: str
    name: str
    quantity: float = 1
    price: float | None = None
    unit_size: str = ""
    category: str = ""


@dataclass
class Order:
    number: str
    date: datetime | None
    lines: list[OrderLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Order":
        date = datetime.fromisoformat(d["date"]) if d.get("date") else None
        return cls(
            number=str(d["number"]),
            date=date,
            lines=[OrderLine(**line) for line in d.get("lines", [])],
        )


@dataclass
class Product:
    """Et produkt fra nemlig.com (normaliseret fra nemlig_shopper.api)."""

    id: str
    name: str
    price: float | None = None
    unit_size: str = ""
    brand: str = ""
    image_url: str = ""
    available: bool = True
    is_organic: bool = False
    is_on_discount: bool = False

    @classmethod
    def from_api(cls, d: dict) -> "Product":
        return cls(
            id=str(d.get("id")),
            name=d.get("name") or "",
            price=d.get("price"),
            unit_size=d.get("unit_size") or "",
            brand=d.get("brand") or "",
            image_url=d.get("image_url") or "",
            available=bool(d.get("available", True)),
            is_organic=bool(d.get("is_organic", False)),
            is_on_discount=bool(d.get("is_on_discount", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)
