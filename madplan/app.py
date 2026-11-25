"""Lokal web-app: http://127.0.0.1:8321

Start:  madplan          (rigtig nemlig.com-konto)
        madplan --demo   (falske data, ingen login)
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .history import Profile, analyze
from .planner import PREFERENCES, build_shopping_list, suggest
from .recipes import BY_ID, RECIPES, Recipe, recipe_from_url

logger = logging.getLogger("madplan")
STATIC = Path(__file__).parent / "static"


class State:
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.client = None
        self.profile: Profile | None = None
        self.imported: dict[str, Recipe] = {}
        self.env_login_tried = False
        self.lock = threading.Lock()
        self.reset_client()

    def reset_client(self) -> None:
        if self.demo:
            from .demo import DemoClient
            self.client = DemoClient()
        else:
            from .nemlig import NemligClient
            self.client = NemligClient()
        self.profile = None

    def recipe(self, rid: str) -> Recipe:
        r = BY_ID.get(rid) or self.imported.get(rid)
        if not r:
            raise HTTPException(404, f"Ukendt opskrift: {rid}")
        return r


def _err(e: Exception) -> HTTPException:
    logger.exception("Fejl")
    return HTTPException(400, str(e) or e.__class__.__name__)


class LoginIn(BaseModel):
    username: str
    password: str


class SuggestIn(BaseModel):
    count: int = Field(5, ge=1, le=7)
    prefs: list[str] = []
    exclude: list[str] = []
    seed: int | None = None


class ImportIn(BaseModel):
    url: str


class ListIn(BaseModel):
    recipe_ids: list[str]
    persons: int = Field(4, ge=1, le=12)


class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(1, ge=1, le=50)
    name: str | None = None
    price: float | None = None


class CartIn(BaseModel):
    items: list[CartItem]


def create_app(demo: bool = False) -> FastAPI:
    app = FastAPI(title="Madplan")
    state = State(demo=demo)
    app.state.madplan = state

    def ensure_login() -> None:
        c = state.client
        if c.is_logged_in():
            return
        if not state.env_login_tried:
            state.env_login_tried = True
            from nemlig_shopper.config import get_credentials
            user, pw = get_credentials()
            if user and pw:
                try:
                    c.login(user, pw)
                    return
                except Exception as e:  # noqa: BLE001
                    logger.warning("Login med gemte oplysninger fejlede: %s", e)
        raise HTTPException(401, "Log ind med din nemlig.com-konto")

    def profile() -> Profile | None:
        with state.lock:
            if state.profile is None:
                ensure_login()
                try:
                    state.profile = analyze(state.client.get_orders(max_orders=20))
                except Exception as e:  # noqa: BLE001
                    logger.warning("Ingen ordrehistorik: %s", e)
                    return None
            return state.profile

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        try:
            ensure_login()
            logged_in = True
        except HTTPException:
            logged_in = False
        return {
            "logged_in": logged_in,
            "demo": state.demo,
            "username": state.client.username if logged_in else None,
            "preferences": {k: v[0] for k, v in PREFERENCES.items()},
            "recipe_count": len(RECIPES),
        }

    @app.post("/api/login")
    def login(body: LoginIn):
        state.reset_client()
        try:
            state.client.login(body.username, body.password)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(401, f"Login fejlede: {e}") from None
        return {"ok": True, "username": body.username}

    @app.post("/api/logout")
    def logout():
        state.reset_client()
        state.env_login_tried = True
        return {"ok": True}

    @app.get("/api/profile")
    def get_profile(refresh: bool = False):
        if refresh:
            state.profile = None
        p = profile()
        if p is None:
            return {"order_count": 0, "top_products": [], "basics": [],
                    "warning": "Kunne ikke hente ordrehistorik. Forslag er ikke personlige."}
        return p.to_dict()

    @app.post("/api/suggest")
    def api_suggest(body: SuggestIn):
        p = profile()
        pool = RECIPES + list(state.imported.values())
        return {"recipes": suggest(p, body.count, body.prefs, body.exclude, pool=pool, seed=body.seed)}

    @app.get("/api/recipes")
    def list_recipes():
        return {"recipes": [r.to_dict() for r in RECIPES + list(state.imported.values())]}

    @app.post("/api/recipes/import")
    def import_recipe(body: ImportIn):
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(400, "Skriv en hel URL, der starter med https://")
        try:
            r = recipe_from_url(body.url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Kunne ikke læse opskriften: {e}") from None
        state.imported[r.id] = r
        d = r.to_dict()
        d["reasons"] = []
        return d

    @app.post("/api/shopping-list")
    def shopping_list(body: ListIn):
        ensure_login()
        recipes = [state.recipe(rid) for rid in body.recipe_ids]
        try:
            return build_shopping_list(recipes, body.persons, profile(), state.client)
        except Exception as e:  # noqa: BLE001
            raise _err(e) from None

    @app.get("/api/search")
    def search(q: str, limit: int = 8):
        ensure_login()
        try:
            return {"products": [p.to_dict() for p in state.client.search(q, limit=limit)]}
        except Exception as e:  # noqa: BLE001
            raise _err(e) from None

    @app.post("/api/cart")
    def add_to_cart(body: CartIn):
        ensure_login()
        try:
            result = state.client.add_items([i.model_dump() for i in body.items])
            cart = state.client.get_cart()
        except Exception as e:  # noqa: BLE001
            raise _err(e) from None
        from .nemlig import BASKET_URL
        return {"result": result, "cart": cart, "basket_url": BASKET_URL}

    @app.get("/api/cart")
    def get_cart():
        ensure_login()
        try:
            return state.client.get_cart()
        except Exception as e:  # noqa: BLE001
            raise _err(e) from None

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Madplan til nemlig.com")
    parser.add_argument("--demo", action="store_true", help="brug falske data (ingen login)")
    parser.add_argument("--port", type=int, default=8321)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import uvicorn

    demo = args.demo or os.getenv("MADPLAN_DEMO") in ("1", "true", "yes")
    url = f"http://127.0.0.1:{args.port}"
    print(f"Madplan kører på {url}" + (" (demo)" if demo else ""))
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(demo=demo), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
