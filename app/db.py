"""SQLite storage (stdlib). One short-lived connection per operation."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("GEOGRID_DB", Path(__file__).resolve().parent.parent / "geogrid.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    cid TEXT UNIQUE,
    place_id TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    address TEXT,
    category TEXT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    keyword TEXT NOT NULL,
    grid_size INTEGER NOT NULL,
    spacing_km REAL NOT NULL,
    center_lat REAL NOT NULL,
    center_lng REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',   -- running | done | failed
    progress INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    metrics TEXT,
    competitors TEXT,
    error TEXT,
    created TEXT NOT NULL,
    finished TEXT
);
CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    row INTEGER NOT NULL,
    col INTEGER NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    rank INTEGER,                              -- NULL = not in top 20 (or error)
    status TEXT NOT NULL,                      -- ok | error
    error TEXT,
    results TEXT
);
CREATE INDEX IF NOT EXISTS idx_points_scan ON points(scan_id);
CREATE INDEX IF NOT EXISTS idx_scans_business ON scans(business_id, keyword);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.execute("PRAGMA journal_mode = WAL")  # live progress reads don't block per-point writes
        c.executescript(SCHEMA)


def upsert_business(b: dict) -> int:
    with connect() as c:
        if b.get("cid"):
            row = c.execute("SELECT id FROM businesses WHERE cid = ?", (b["cid"],)).fetchone()
            if row:
                return row["id"]
        cur = c.execute(
            "INSERT INTO businesses (name, cid, place_id, lat, lng, address, category, created) VALUES (?,?,?,?,?,?,?,?)",
            (b["name"], b.get("cid"), b.get("place_id"), b["lat"], b["lng"], b.get("address"), b.get("category"), now()))
        return cur.lastrowid


def get_business(business_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone()
        return dict(row) if row else None


def list_businesses() -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM businesses ORDER BY name")]


def create_scan(business_id: int, keyword: str, grid_size: int, spacing_km: float,
                center_lat: float, center_lng: float) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO scans (business_id, keyword, grid_size, spacing_km, center_lat, center_lng, total, created)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (business_id, keyword, grid_size, spacing_km, center_lat, center_lng, grid_size * grid_size, now()))
        return cur.lastrowid


def save_point(scan_id: int, p, rank: int | None, status: str, results: list[dict] | None, error: str | None) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO points (scan_id, row, col, lat, lng, rank, status, error, results) VALUES (?,?,?,?,?,?,?,?,?)",
            (scan_id, p.row, p.col, p.lat, p.lng, rank, status, error,
             json.dumps(results) if results is not None else None))
        c.execute("UPDATE scans SET progress = progress + 1 WHERE id = ?", (scan_id,))


def finish_scan(scan_id: int, status: str, metrics: dict | None, competitors: list | None,
                error: str | None = None) -> None:
    with connect() as c:
        c.execute("UPDATE scans SET status=?, metrics=?, competitors=?, error=?, finished=? WHERE id=?",
                  (status, json.dumps(metrics) if metrics else None,
                   json.dumps(competitors) if competitors else None, error, now(), scan_id))


def mark_interrupted_scans() -> None:
    """Scans left 'running' by a previous process will never finish."""
    with connect() as c:
        c.execute("UPDATE scans SET status='failed', error='interrupted', finished=? WHERE status='running'", (now(),))


def _scan_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("metrics", "competitors"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def list_scans(business_id: int | None = None, limit: int = 100) -> list[dict]:
    # Leaves out the (large) competitors column: lists only need metrics.
    sql = ("SELECT s.id, s.business_id, s.keyword, s.grid_size, s.spacing_km, s.center_lat, s.center_lng, s.status,"
           " s.progress, s.total, s.metrics, s.error, s.created, s.finished, b.name AS business_name"
           " FROM scans s JOIN businesses b ON b.id = s.business_id"
           + (" WHERE s.business_id = ?" if business_id else "") + " ORDER BY s.id DESC LIMIT ?")
    args = (business_id, limit) if business_id else (limit,)
    with connect() as c:
        return [_scan_row(r) for r in c.execute(sql, args)]


def get_scan(scan_id: int, with_points: bool = True) -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT s.*, b.name AS business_name, b.cid AS business_cid, b.lat AS business_lat,"
            " b.lng AS business_lng FROM scans s JOIN businesses b ON b.id = s.business_id WHERE s.id = ?",
            (scan_id,)).fetchone()
        if not row:
            return None
        scan = _scan_row(row)
        if with_points:
            scan["points"] = [
                {**dict(p), "results": json.loads(p["results"]) if p["results"] else []}
                for p in c.execute("SELECT * FROM points WHERE scan_id = ? ORDER BY row, col", (scan_id,))]
        return scan


def previous_scan_id(scan: dict) -> int | None:
    """Most recent finished scan of the same business + keyword + grid before this one."""
    with connect() as c:
        row = c.execute(
            "SELECT id FROM scans WHERE business_id=? AND keyword=? AND grid_size=? AND spacing_km=?"
            " AND status='done' AND id < ? ORDER BY id DESC LIMIT 1",
            (scan["business_id"], scan["keyword"], scan["grid_size"], scan["spacing_km"], scan["id"])).fetchone()
        return row["id"] if row else None


def delete_scan(scan_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
