"""GeoGrid ZURI metrics extension v1. No database writes or API calls.

Compatibility: keeps scan_metrics and competitor_leaderboard public interfaces.
IDA is an experimental proxy, not the proprietary Localo metric.
"""
import math
import unicodedata

NOT_FOUND_RANK = 21


def _visibility_weight(rank):
    if rank is None or rank > 20 or rank < 1:
        return 0.0
    if rank <= 3:
        return 1.0
    if rank <= 10:
        return (11 - rank) / 10
    return 0.1


def scan_metrics(ranks: list[int | None]) -> dict:
    """One rank per successfully scanned point; None = not found in top 20."""
    n = len(ranks)
    found = [r for r in ranks if r is not None]
    return {
        "points": n,
        "found_pct": round(100 * len(found) / n, 1) if n else 0.0,
        "arp": round(sum(found) / len(found), 2) if found else None,
        "atrp": round(sum(r if r is not None else NOT_FOUND_RANK for r in ranks) / n, 2) if n else None,
        "solv": round(100 * sum(1 for r in found if r <= 3) / n, 1) if n else 0.0,
        "top10_pct": round(100 * sum(1 for r in found if r <= 10) / n, 1) if n else 0.0,
        "ivl": round(100 * sum(_visibility_weight(r) for r in ranks) / n, 2) if n else None,
    }


def _normalize(s):
    s = unicodedata.normalize('NFKD', str(s or '')).casefold()
    return ''.join(c for c in s if not unicodedata.combining(c)).strip()


def _competitor_key(r):
    return str(r.get('cid') or r.get('place_id') or _normalize(r.get('name'))).strip()


def competitor_leaderboard(points_results: list[list[dict]], limit: int = 20) -> list[dict]:
    """Aggregate businesses across successful points; rank by SoLV then ATRP."""
    n = len(points_results)
    if not n:
        return []
    seen = {}
    for results in points_results:
        counted = set()
        for i, r in enumerate(results or [], 1):
            if not isinstance(r, dict):
                continue
            key = _competitor_key(r)
            if not key or key in counted:
                continue
            counted.add(key)
            seen.setdefault(key, (r, []))[1].append(i)
    board = []
    for info, rs in seen.values():
        m = scan_metrics(rs + [None] * (n - len(rs)))
        board.append({k: info.get(k) for k in ('name', 'cid', 'rating', 'reviews', 'category')} | m)
    board.sort(key=lambda b: (-b['solv'], b['atrp']))
    return board[:limit]


def _relevant(r, category_terms):
    if not category_terms:
        return None  # Unknown, not automatically relevant.
    category = _normalize(r.get('category'))
    return any(_normalize(t) in category for t in category_terms if _normalize(t))


def point_difficulty(results: list[dict], category_terms: list[str] | None = None, *,
                     min_results: int = 5) -> dict:
    """Experimental competition proxy. Only score sufficiently populated, classified samples.

    No claim of measuring total competitor density: search-result truncation biases counts.
    Score uses review strength and top-three concentration of relevant results.
    """
    if not isinstance(results, list):
        return {'ida': None, 'level': 'dados_insuficientes', 'confidence': 'low', 'reason': 'resultados_invalidos'}
    if not category_terms:
        return {'ida': None, 'level': 'dados_insuficientes', 'confidence': 'low', 'reason': 'categorias_nao_configuradas', 'sample_size': len(results)}
    relevant = [(i, r) for i, r in enumerate(results, 1)
                if isinstance(r, dict) and _relevant(r, category_terms)]
    if len(results) < min_results or len(relevant) < 3:
        return {'ida': None, 'level': 'dados_insuficientes', 'confidence': 'low',
                'reason': 'amostra_pequena', 'sample_size': len(results), 'relevant_count': len(relevant)}
    # Review strength capped logarithmically at 1000 reviews; rating contributes multiplicatively.
    strengths = []

for _, r in relevant:
    try:
        if r.get("reviews") is None or r.get("rating") is None:
            continue

        reviews = max(0, float(r["reviews"]))
        rating = max(0, min(5, float(r["rating"])))

        strengths.append(
            min(1, math.log1p(reviews) / math.log1p(1000))
            * rating / 5
        )
    except (TypeError, ValueError):
        continue

if not strengths:
    return {
        "ida": None,
        "level": "dados_insuficientes",
        "confidence": "low",
        "reason": "avaliacoes_indisponiveis",
        "sample_size": len(results),
        "relevant_count": len(relevant),
    }

authority = sum(strengths) / len(strengths)
    top3_share = sum(1 for i, _ in relevant if i <= 3) / 3
    # This is an intensity proxy, NOT true market density or proximity.
    score = round(100 * (0.65 * authority + 0.35 * top3_share), 1)
    return {'ida': score, 'level': 'facil' if score < 35 else 'medio' if score < 70 else 'dificil',
            'confidence': 'experimental', 'sample_size': len(results),
            'relevant_count': len(relevant), 'authority_proxy': round(authority, 3),
            'top3_relevance': round(top3_share, 3)}
