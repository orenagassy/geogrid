
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


# --------------------------------------------------
# Request models
# --------------------------------------------------

class BusinessIn(BaseModel):
    """Business registration request."""

    query: str = Field(
        min_length=2,
        description="Google Maps link or 'Name, City'",
    )


class ScanIn(BaseModel):
    """GeoGrid scan configuration."""

    business_id: int

    keywords: list[str] = Field(
        min_length=1,
        max_length=10,
    )

    grid_size: int = Field(
        default=7,
        ge=3,
        le=13,
    )

    spacing_km: float = Field(
        default=1.0,
        gt=0,
        le=50,
    )

    center_lat: float | None = None
    center_lng: float | None = None


# --------------------------------------------------
# Web interface
# --------------------------------------------------

@app.get("/")
def index():
    """Serve the GeoGrid web interface."""

    return FileResponse(
        STATIC / "index.html"
    )


# --------------------------------------------------
# Businesses API
# --------------------------------------------------

@app.get("/api/businesses")
def businesses():
    """List registered businesses."""

    return db.list_businesses()


@app.post("/api/businesses")
async def add_business(body: BusinessIn):
    """Register or update a business from Google Maps."""

    try:
        info = await fetcher().resolve_business(
            body.query.strip()
        )

    except FetchError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        log.exception("resolve failed")

        raise HTTPException(
            status_code=502,
            detail=f"lookup failed: {error}",
        ) from error

    business_id = db.upsert_business(info)

    return db.get_business(business_id)


# --------------------------------------------------
# Scans API
# --------------------------------------------------

@app.get("/api/scans/{scan_id}/analysis")
def scan_analysis(
    scan_id: int,
    category: list[str] | None = Query(default=None),
):
    """List scans, optionally filtered by business."""

    return db.list_scans(business_id)


async def _run_queued(
    scan_ids: list[int],
) -> None:
    """Execute queued scans sequentially."""

    async with scan_lock:

        for scan_id in scan_ids:

            try:
                await run_scan(
                    scan_id,
                    fetcher(),
                )

            except Exception:
                log.exception(
                    "scan %s crashed",
                    scan_id,
                )


@app.post("/api/scans")
async def start_scans(
    body: ScanIn,
):
    """Create and queue GeoGrid scans."""

    business = db.get_business(
        body.business_id
    )

    if not business:
        raise HTTPException(
            status_code=404,
            detail="business not found",
        )

    center = (
        (body.center_lat, body.center_lng)
        if (
            body.center_lat is not None
            and body.center_lng is not None
        )
        else None
    )

    try:
        scan_ids = create_scans(
            business,
            body.keywords,
            body.grid_size,
            body.spacing_km,
            center,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    asyncio.create_task(
        _run_queued(scan_ids)
    )

    return {
        "scan_ids": scan_ids,
    }


# --------------------------------------------------
# Scan details
# --------------------------------------------------

@app.get("/api/scans/{scan_id}")
def scan_detail(
    scan_id: int,
):
    """Return scan details and historical comparison."""

    scan = db.get_scan(scan_id)

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="scan not found",
        )

    scan["comparison"] = None

    if scan["status"] == "done":

        previous_id = db.previous_scan_id(scan)

        if previous_id:

            previous_scan = db.get_scan(
                previous_id
            )

            scan["comparison"] = compare(
                scan,
                previous_scan,
            )

    return scan


# --------------------------------------------------
# Delete scan
# --------------------------------------------------

@app.delete("/api/scans/{scan_id}")
def remove_scan(
    scan_id: int,
):
    """Delete a scan that is not currently running."""

    scan = db.get_scan(
        scan_id,
        with_points=False,
    )

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="scan not found",
        )

    if scan["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="scan is still running",
        )

    db.delete_scan(scan_id)

    return {
        "deleted": scan_id,
    }


# --------------------------------------------------
# GeoGrid ZURI - IVL and IDA analysis
# --------------------------------------------------

@app.get("/api/scans/{scan_id}/analysis")
def scan_analysis(
    scan_id: int,
    category: list[str] | None = None,
):
    """Return local visibility and competition analysis.

    Metrics:
        ARP: Average Rank Position.
        ATRP: Average Total Rank Position.
        SoLV: Share of Local Voice.
        IVL: Local Visibility Index.
        IDA: Experimental Area Difficulty Index.

    Failed scan points are excluded from ranking metrics.
    """

    # ----------------------------------------------
    # 1. Load scan
    # ----------------------------------------------

    scan = db.get_scan(scan_id)

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="scan not found",
        )

    scan_points = scan.get("points") or []

    # ----------------------------------------------
    # 2. Filter successfully scanned points
    # ----------------------------------------------

    valid = [
        point
        for point in scan_points
        if point.get("status") == "ok"
    ]

    # ----------------------------------------------
    # 3. Calculate visibility metrics
    # ----------------------------------------------

    ranks = [
        point.get("rank")
        for point in valid
    ]

    metrics = scan_metrics(ranks)

    total = len(scan_points)
    valid_count = len(valid)

    metrics["errors"] = (
        total - valid_count
    )

    metrics["coverage_pct"] = (
        round(
            100 * valid_count / total,
            1,
        )
        if total
        else 0.0
    )

    # ----------------------------------------------
    # 4. Calculate difficulty for each point
    # ----------------------------------------------

    points = []

    for point in scan_points:

        if point.get("status") == "ok":

            difficulty = point_difficulty(
                point.get("results") or [],
                category,
            )

        else:

            difficulty = {
                "ida": None,
                "level": "dados_insuficientes",
                "confidence": "low",
                "reason": "erro_na_consulta",
            }

        points.append(
            {
                "row": point.get("row"),
                "col": point.get("col"),
                "lat": point.get("lat"),
                "lng": point.get("lng"),
                "rank": point.get("rank"),
                "status": point.get("status"),
                "difficulty": difficulty,
            }
        )

    # ----------------------------------------------
    # 5. Collect valid difficulty scores
    # ----------------------------------------------

    scores = [
        point["difficulty"]["ida"]
        for point in points
        if point["difficulty"].get("ida") is not None
    ]

    # ----------------------------------------------
    # 6. Calculate average difficulty
    # ----------------------------------------------

    ida_average = (
        round(
            sum(scores) / len(scores),
            1,
        )
        if scores
        else None
    )

    # ----------------------------------------------
    # 7. Calculate difficulty data coverage
    # ----------------------------------------------

    ida_coverage_pct = (
        round(
            100 * len(scores) / valid_count,
            1,
        )
        if valid_count
        else 0.0
    )

    # ----------------------------------------------
    # 8. Return complete analysis
    # ----------------------------------------------

    return {
        "scan_id": scan_id,
        "keyword": scan.get("keyword"),
        "metrics": metrics,
        "ida_average": ida_average,
        "ida_evaluated_points": len(scores),
        "ida_coverage_pct": ida_coverage_pct,
        "points": points,
    }
