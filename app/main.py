"""Web UI + JSON API.  Run:  uvicorn app.main:app --reload   then open http://localhost:8000"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .fetchers.base import FetchError
from .scan import compare, create_scans, make_fetcher, run_scan

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("geogrid")

state: dict = {"fetcher": None}
# Scans run one at a time (each scan already fetches points concurrently); queued scans wait here.
scan_lock = asyncio.Lock()


def fetcher():
    if state["fetcher"] is None:
        state["fetcher"] = make_fetcher()
    return state["fetcher"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    db.init_db()
    db.mark_interrupted_scans()
    yield
    if state["fetcher"]:
        await state["fetcher"].close()


app = FastAPI(title="GeoGrid", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class BusinessIn(BaseModel):
    query: str = Field(min_length=2, description="Google Maps link or 'Name, City'")


class ScanIn(BaseModel):
    business_id: int
    keywords: list[str] = Field(min_length=1, max_length=10)
    grid_size: int = Field(7, ge=3, le=13)
    spacing_km: float = Field(1.0, gt=0, le=50)
    center_lat: float | None = None
    center_lng: float | None = None


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/businesses")
def businesses():
    return db.list_businesses()


@app.post("/api/businesses")
async def add_business(body: BusinessIn):
    try:
        info = await fetcher().resolve_business(body.query.strip())
    except FetchError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("resolve failed")
        raise HTTPException(502, f"lookup failed: {e}")
    return db.get_business(db.upsert_business(info))


@app.get("/api/scans")
def scans(business_id: int | None = None):
    return db.list_scans(business_id)


async def _run_queued(scan_ids: list[int]) -> None:
    async with scan_lock:
        for sid in scan_ids:
            try:
                await run_scan(sid, fetcher())
            except Exception:
                log.exception("scan %s crashed", sid)


@app.post("/api/scans")
async def start_scans(body: ScanIn):
    biz = db.get_business(body.business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    center = (body.center_lat, body.center_lng) if body.center_lat is not None and body.center_lng is not None else None
    try:
        ids = create_scans(biz, body.keywords, body.grid_size, body.spacing_km, center)
    except ValueError as e:
        raise HTTPException(422, str(e))
    asyncio.create_task(_run_queued(ids))
    return {"scan_ids": ids}


@app.get("/api/scans/{scan_id}")
def scan_detail(scan_id: int):
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "scan not found")
    scan["comparison"] = None
    if scan["status"] == "done" and (prev_id := db.previous_scan_id(scan)):
        scan["comparison"] = compare(scan, db.get_scan(prev_id))
    return scan


@app.delete("/api/scans/{scan_id}")
def remove_scan(scan_id: int):
    scan = db.get_scan(scan_id, with_points=False)
    if not scan:
        raise HTTPException(404, "scan not found")
    if scan["status"] == "running":
        raise HTTPException(409, "scan is still running")
    db.delete_scan(scan_id)
    return {"deleted": scan_id}
