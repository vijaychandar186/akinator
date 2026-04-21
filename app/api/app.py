"""FastAPI application exposing the Akinator game over HTTP."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.game import router as game_router
from app.api.explorer import router as explorer_router
from app.db import init_schema


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    dsn = os.environ.get("DATABASE_URL", "")
    if dsn:
        init_schema(dsn)
    yield


app = FastAPI(title="Akinator API", version="0.1.0", lifespan=_lifespan)

app.include_router(game_router)
app.include_router(explorer_router)

# ---------------------------------------------------------------------------
# Optional HTML UI — enabled by setting AKINATOR_SERVE_UI=1 before import.
# ---------------------------------------------------------------------------

_PUBLIC_DIR = Path(__file__).parent.parent.parent / "public"
_UI_HTML = (_PUBLIC_DIR / "templates" / "ui.html").read_text()
_DATA_HTML = (_PUBLIC_DIR / "templates" / "data.html").read_text()

if os.environ.get("AKINATOR_SERVE_UI"):
    app.mount(
        "/static", StaticFiles(directory=str(_PUBLIC_DIR / "static")), name="static"
    )

    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    def serve_ui() -> str:
        return _UI_HTML

    @app.get("/explorer", response_class=HTMLResponse, include_in_schema=False)
    def serve_data() -> str:
        return _DATA_HTML

    @app.get("/", response_class=RedirectResponse, include_in_schema=False)
    def root() -> str:
        return "/ui"
