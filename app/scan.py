"""Scan orchestration: grid -> fetch each point (rate limited) -> store -> metrics."""
import asyncio
import logging
import os

from . import db
from .fetchers.base import Fetcher
from .grid import make_grid
from .matching import find_rank
from .metrics import competitor_leaderboard, scan_metrics

log = logging.getLogger("geogrid.scan")

MAX_CONSECUTIVE_ERRORS = 5


def make_fetcher() -> Fetcher:
    """GEOGRID_FETCHER=playwright (default, free) | dataforseo (needs DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD)."""
    kind = os.environ.get("GEOGRID_FETCHER", "playwright").lower()
    if kind == "dataforseo":
        from .fetchers.dataforseo import DataForSEOFetcher
        return DataForSEOFetcher()
    from .fetchers.playwright_maps import PlaywrightMapsFetcher
    return PlaywrightMapsFetcher(headless=os.environ.get("GEOGRID_HEADLESS", "1") != "0",
                                 proxy=os.environ.get("GEOGRID_PROXY") or None)


def default_concurrency() -> int:
    return int(os.environ.get("GEOGRID_CONCURRENCY", "2"))


async def run_scan(scan_id: int, fetcher: Fetcher, concurrency: int | None = None) -> dict:
    scan = db.get_scan(scan_id, with_points=False)
    target = {"cid": scan["business_cid"], "name": scan["business_name"]}
    grid = make_grid(scan["center_lat"], scan["center_lng"], scan["grid_size"], scan["spacing_km"])
    sem = asyncio.Semaphore(concurrency or default_concurrency())
    abort = asyncio.Event()
    consecutive_errors = 0
    ok: list[tuple[int | None, list[dict]]] = []

    async def one(point):
        nonlocal consecutive_errors
        async with sem:
            if abort.is_set():
                db.save_point(scan_id, point, None, "error", None, "skipped after repeated errors")
                return
            try:
                results = await fetcher.fetch(scan["keyword"], point.lat, point.lng)
            except Exception as e:  # one bad point must not kill the scan
                log.warning("point %s,%s failed: %s", point.row, point.col, e)
                db.save_point(scan_id, point, None, "error", None, str(e)[:300])
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:  # most likely blocked; stop hammering Google
                    abort.set()
                return
            consecutive_errors = 0
            rank = find_rank(results, target)
            db.save_point(scan_id, point, rank, "ok", results, None)
            ok.append((rank, results))

    try:
        await asyncio.gather(*(one(p) for p in grid))
    except Exception as e:  # unexpected (DB etc.)
        db.finish_scan(scan_id, "failed", None, None, str(e)[:300])
        raise
    if not ok:
        db.finish_scan(scan_id, "failed", None, None, "every point failed (blocked by Google?)")
    else:
        metrics = scan_metrics([rank for rank, _ in ok])
        metrics["errors"] = len(grid) - len(ok)
        db.finish_scan(scan_id, "done", metrics, competitor_leaderboard([res for _, res in ok]))
    return db.get_scan(scan_id)


def compare(scan: dict, prev: dict) -> dict:
    """Metric deltas and the previous rank of every point, vs. an earlier scan of the same grid."""
    def delta(k):
        a, b = (scan["metrics"] or {}).get(k), (prev["metrics"] or {}).get(k)
        return None if a is None or b is None else round(a - b, 2)
    return {
        "previous_scan_id": prev["id"],
        "previous_created": prev["created"],
        "metrics": {k: delta(k) for k in ("arp", "atrp", "solv", "found_pct")},
        "points": {f'{p["row"]},{p["col"]}': p["rank"] for p in prev.get("points", []) if p["status"] == "ok"},
    }
