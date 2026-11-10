"""GeoGrid ZURI - Web UI and JSON API.

Run:
    uvicorn app.main:app --reload

Open:
    http://localhost:8000
"""

import asyncio
import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .fetchers.base import FetchError
from .metrics import point_difficulty, scan_metrics
from .scan import compare, create_scans, make_fetcher, run_scan


# --------------------------------------------------
# Configuration
# --------------------------------------------------

STATIC = Path(__file__).parent / "static"

log = logging.getLogger("geogrid")

state: dict = {
    "fetcher": None,
}

# Scans run one at a time.
# Each scan already fetches points concurrently.
# Queued scans wait for the previous scan to finish.

scan_lock = asyncio.Lock()


# --------------------------------------------------
# Fetcher
# --------------------------------------------------

def fetcher():
    """Return the shared fetcher instance."""

    if state["fetcher"] is None:
        state["fetcher"] = make_fetcher()

    return state["fetcher"]


# --------------------------------------------------
# Application lifecycle
# --------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database and manage application resources."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    db.init_db()
    db.mark_interrupted_scans()

    yield

    if state["fetcher"]:
        await state["fetcher"].close()


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="GeoGrid",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC),
    name="static",
)
