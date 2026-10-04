"""Scan metrics: ARP, ATRP, SoLV and a competitor leaderboard."""

NOT_FOUND_RANK = 21


def scan_metrics(ranks: list[int | None]) -> dict:
    """ranks: one entry per successfully-scanned point (None = not in top 20)."""
    n = len(ranks)
    found = [r for r in ranks if r is not None]
    return {
        "points": n,
        "found_pct": round(100 * len(found) / n, 1) if n else 0.0,
        "arp": round(sum(found) / len(found), 2) if found else None,
        "atrp": round(sum(r if r is not None else NOT_FOUND_RANK for r in ranks) / n, 2) if n else None,
        "solv": round(100 * sum(1 for r in found if r <= 3) / n, 1) if n else 0.0,
    }


def competitor_leaderboard(points_results: list[list[dict]], limit: int = 20) -> list[dict]:
    """Aggregate every business seen across all points; sort by SoLV then ATRP."""
    n = len(points_results)
    if not n:
        return []
    seen: dict[str, tuple[dict, list[int]]] = {}
    for results in points_results:
        counted = set()
        for i, r in enumerate(results, 1):
            key = r.get("cid") or r.get("name", "").lower()
            if not key or key in counted:
                continue
            counted.add(key)
            seen.setdefault(key, (r, []))[1].append(i)
    board = []
    for info, rs in seen.values():
        m = scan_metrics(rs + [None] * (n - len(rs)))
        del m["points"]
        board.append({k: info.get(k) for k in ("name", "cid", "rating", "reviews", "category")} | m)
    board.sort(key=lambda b: (-b["solv"], b["atrp"]))
    return board[:limit]
