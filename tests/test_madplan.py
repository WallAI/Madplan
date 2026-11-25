from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from madplan.app import create_app
from madplan.demo import DemoClient
from madplan.history import analyze, match_quality
from madplan.models import Order, OrderLine
from madplan.nemlig import parse_date, parse_order_lines, parse_order_list
from madplan.planner import aggregate_ingredients, compute_quantity, parse_size, suggest
from madplan.recipes import BY_ID, RECIPES


def test_match_quality():
    assert match_quality("tomater", "Tomater i bakke") >= 1
    assert match_quality("tomater", "Hakkede tomater") < 1
    assert match_quality("hakkede tomater", "Hakkede tomater 400 g") >= 1
    assert match_quality("æg", "Æg, frilands 10 stk") >= 1
    assert match_quality("æg", "Ægnudler") == 0
    assert match_quality("mælk", "Letmælk 1,5%") >= 1
    assert match_quality("kartofler", "Kartofler, faste") >= 1
    assert match_quality("laks", "Kyllingebryst") == 0


def test_parse_size_and_quantity():
    assert parse_size("500 g") == (500, "g")
    assert parse_size("1 kg") == (1000, "g")
    assert parse_size("1 l") == (1000, "ml")
    assert parse_size("2 x 125 g") == (250, "g")
    assert compute_quantity(1000, "g", "500 g") == 2
    assert compute_quantity(400, "g", "500 g") == 1
    assert compute_quantity(2, "dåse", "400 g") == 2
    assert compute_quantity(5, "dl", "1 l") == 1
    assert compute_quantity(1, "stk", "1 kg") == 1


def test_parse_nemlig_responses():
    lst = parse_order_list({"Orders": [{"OrderNumber": 123, "DeliveryTime": "2026-10-01T17:00:00"}]})
    assert lst == [{"number": "123", "date": datetime(2026, 10, 1, 17)}]
    lines = parse_order_lines({"Lines": [{"ProductNumber": "5001", "ProductName": "Letmælk", "Quantity": 2,
                                          "Price": 11.95, "Description": "1 l"}]})
    assert lines[0].product_id == "5001" and lines[0].quantity == 2 and lines[0].unit_size == "1 l"
    assert parse_date("/Date(1700000000000)/").year == 2023


def _orders():
    now = datetime(2026, 11, 25)
    milk = OrderLine("1", "Letmælk", 2, 11.95, "1 l")
    beef = OrderLine("2", "Hakket oksekød 8-12%", 1, 44.95, "500 g")
    coffee = OrderLine("3", "Kaffe", 1, 49.0, "400 g")
    return [
        Order("a", now - timedelta(days=7), [milk, beef]),
        Order("b", now - timedelta(days=14), [milk, coffee]),
        Order("c", now - timedelta(days=21), [milk, beef, coffee]),
    ], now


def test_analyze_and_basics():
    orders, now = _orders()
    p = analyze(orders, today=now)
    milk = next(x for x in p.products if x.name == "Letmælk")
    assert milk.orders == 3 and milk.share == 1 and milk.typical_qty == 2
    assert milk.avg_interval_days == 7 and milk.due == 1.0
    assert {b.name for b in p.basics()} == {"Letmælk", "Hakket oksekød 8-12%", "Kaffe"}


def test_suggest_prefers_history_and_varies():
    orders, now = _orders()
    p = analyze(orders, today=now)
    plan = suggest(p, count=5, seed=1)
    assert len(plan) == 5 and len({r["id"] for r in plan}) == 5
    assert len({r["main"] for r in plan}) >= 3
    veg = suggest(p, count=3, prefs=["vegetar"], seed=1)
    assert all(r["main"] == "vegetar" for r in veg)


def test_aggregate_scales_and_merges():
    items = aggregate_ingredients([BY_ID["bolognese"], BY_ID["vegetarlasagne"]], persons=2)
    tomatoes = next(i for i in items if i["name"] == "hakkede tomater")
    assert tomatoes["amount"] == 2  # (2 + 2) dåser * 2/4
    assert len(tomatoes["recipes"]) == 2


def test_all_recipes_valid():
    assert len(RECIPES) >= 20
    assert len(BY_ID) == len(RECIPES)
    for r in RECIPES:
        assert r.ingredients and r.steps and r.main in {"kylling", "okse", "svin", "fisk", "vegetar"}


def test_full_flow_demo():
    client = TestClient(create_app(demo=True))
    assert client.get("/api/status").json()["logged_in"]
    prof = client.get("/api/profile").json()
    assert prof["order_count"] == 12 and prof["basics"]
    plan = client.post("/api/suggest", json={"count": 4, "seed": 3}).json()["recipes"]
    assert len(plan) == 4
    lst = client.post("/api/shopping-list", json={"recipe_ids": [r["id"] for r in plan], "persons": 4}).json()
    assert lst["items"] and lst["basics"]
    assert any(i["source"] == "history" for i in lst["items"])
    chosen = [i for i in lst["items"] + lst["basics"] if i["checked"] and i["product"]]
    body = {"items": [{"product_id": i["product"]["id"], "quantity": i["quantity"],
                       "name": i["product"]["name"], "price": i["product"]["price"]} for i in chosen]}
    res = client.post("/api/cart", json=body).json()
    assert len(res["result"]["success"]) == len(chosen)
    assert res["cart"]["count"] >= len(chosen)
    assert res["basket_url"].startswith("https://www.nemlig.com")


def test_real_mode_requires_login(monkeypatch, tmp_path):
    monkeypatch.delenv("NEMLIG_USERNAME", raising=False)
    monkeypatch.delenv("NEMLIG_PASSWORD", raising=False)
    monkeypatch.setattr("nemlig_shopper.config.CREDENTIALS_FILE", tmp_path / "none.json")
    client = TestClient(create_app(demo=False))
    assert client.get("/api/status").json()["logged_in"] is False
    assert client.post("/api/shopping-list", json={"recipe_ids": ["bolognese"]}).status_code == 401


def test_demo_client_search():
    c = DemoClient()
    assert c.search("mælk", limit=2)
