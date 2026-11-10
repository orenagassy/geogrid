
"""GeoGrid ZURI metrics extension v1.

No database writes or API calls.

Compatibility:
- Keeps scan_metrics and competitor_leaderboard public interfaces.
- Preserves ARP, ATRP, SoLV and competitor leaderboard.
- Adds IVL (Local Visibility Index).
- Adds IDA (experimental competition difficulty proxy).

IDA is not the proprietary Localo metric.
"""

import math
import unicodedata


NOT_FOUND_RANK = 21


def _visibility_weight(rank):
    """Calculate visibility weight based on Google Maps ranking."""

    if rank is None or rank > 20 or rank < 1:
        return 0.0

    if rank <= 3:
        return 1.0

    if rank <= 10:
        return (11 - rank) / 10

    return 0.1


def scan_metrics(ranks: list[int | None]) -> dict:
    """Calculate metrics for successfully scanned points.

    Args:
        ranks: One rank per successfully scanned point.
               None means the business was not found in the top 20.

    Returns:
        Dictionary containing ARP, ATRP, SoLV, Top 10 and IVL.
    """

    n = len(ranks)

    found = [
        rank
        for rank in ranks
        if rank is not None
    ]

    return {
        "points": n,

        "found_pct": (
            round(100 * len(found) / n, 1)
            if n
            else 0.0
        ),

        "arp": (
            round(sum(found) / len(found), 2)
            if found
            else None
        ),

        "atrp": (
            round(
                sum(
                    rank if rank is not None else NOT_FOUND_RANK
                    for rank in ranks
                ) / n,
                2,
            )
            if n
            else None
        ),

        "solv": (
            round(
                100 * sum(
                    1
                    for rank in found
                    if rank <= 3
                ) / n,
                1,
            )
            if n
            else 0.0
        ),

        "top10_pct": (
            round(
                100 * sum(
                    1
                    for rank in found
                    if rank <= 10
                ) / n,
                1,
            )
            if n
            else 0.0
        ),

        "ivl": (
            round(
                100 * sum(
                    _visibility_weight(rank)
                    for rank in ranks
                ) / n,
                2,
            )
            if n
            else None
        ),
    }


def _normalize(value):
    """Normalize text for category and competitor comparisons."""

    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    ).casefold()

    return "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    ).strip()


def _competitor_key(result):
    """Create a unique identifier for a competitor."""

    return str(
        result.get("cid")
        or result.get("place_id")
        or _normalize(result.get("name"))
    ).strip()


def competitor_leaderboard(
    points_results: list[list[dict]],
    limit: int = 20,
) -> list[dict]:
    """Aggregate businesses across successfully scanned points.

    Competitors are ranked by SoLV and then ATRP.
    """

    n = len(points_results)

    if not n:
        return []

    seen = {}

    for results in points_results:

        counted = set()

        for index, result in enumerate(results or [], 1):

            if not isinstance(result, dict):
                continue

            key = _competitor_key(result)

            if not key or key in counted:
                continue

            counted.add(key)

            seen.setdefault(
                key,
                (result, []),
            )[1].append(index)

    board = []

    for info, ranks in seen.values():

        metrics = scan_metrics(
            ranks + [None] * (n - len(ranks))
        )

        competitor = {
            key: info.get(key)
            for key in (
                "name",
                "cid",
                "rating",
                "reviews",
                "category",
            )
        }

        competitor.update(metrics)

        board.append(competitor)

    board.sort(
        key=lambda competitor: (
            -competitor["solv"],
            competitor["atrp"],
        )
    )

    return board[:limit]


def _relevant(result, category_terms):
    """Check whether a result matches configured business categories."""

    if not category_terms:
        return None

    category = _normalize(
        result.get("category")
    )

    return any(
        _normalize(term) in category
        for term in category_terms
        if _normalize(term)
    )


def point_difficulty(
    results: list[dict],
    category_terms: list[str] | None = None,
    *,
    min_results: int = 5,
) -> dict:
    """IDA experimental adaptativo, calculado somente com evidências observadas.

    Amostra robusta: >= min_results resultados e >= 3 concorrentes relevantes.
    Amostra moderada: >= 2 resultados e >= 2 relevantes com avaliações.
    Amostras menores não recebem pontuação; nunca inferir concorrentes ausentes.
    A fórmula é mantida para preservar a comparabilidade com o IDA anterior.
    """
    # IDA_ADAPTATIVO_ZURI_V2
    if not isinstance(results, list):
        return {"ida": None, "level": "dados_insuficientes", "confidence": "low", "reason": "resultados_invalidos"}
    if not category_terms:
        return {"ida": None, "level": "dados_insuficientes", "confidence": "low", "reason": "categorias_nao_configuradas", "sample_size": len(results)}

    relevant = [
        (index, result)
        for index, result in enumerate(results, 1)
        if isinstance(result, dict) and _relevant(result, category_terms)
    ]
    sample_size = len(results)
    relevant_count = len(relevant)
    robust = sample_size >= min_results and relevant_count >= 3
    moderate = sample_size >= 2 and relevant_count >= 2
    if not (robust or moderate):
        return {
            "ida": None, "level": "dados_insuficientes", "confidence": "low",
            "reason": "amostra_pequena", "sample_size": sample_size,
            "relevant_count": relevant_count,
        }

    strengths = []
    for _, result in relevant:
        try:
            if result.get("reviews") is None or result.get("rating") is None:
                continue
            reviews = float(result["reviews"])
            rating = float(result["rating"])
            if not (math.isfinite(reviews) and math.isfinite(rating)):
                continue
            reviews = max(0.0, reviews)
            rating = max(0.0, min(5.0, rating))
            review_strength = min(1.0, math.log1p(reviews) / math.log1p(1000))
            strengths.append(review_strength * rating / 5)
        except (TypeError, ValueError, OverflowError):
            continue
    # Para amostra moderada, exigir dados de avaliação de ambos os concorrentes.
    minimum_strengths = 1 if robust else 2
    if len(strengths) < minimum_strengths:
        return {
            "ida": None, "level": "dados_insuficientes", "confidence": "low",
            "reason": "avaliacoes_indisponiveis", "sample_size": sample_size,
            "relevant_count": relevant_count, "review_sample_size": len(strengths),
        }

    authority = sum(strengths) / len(strengths)
    top3_share = sum(1 for index, _ in relevant if index <= 3) / 3
    score = round(100 * (0.65 * authority + 0.35 * top3_share), 1)
    level = "facil" if score < 35 else "medio" if score < 70 else "dificil"
    return {
        "ida": score, "level": level,
        "confidence": "experimental" if robust else "moderate",
        "sample_size": sample_size, "relevant_count": relevant_count,
        "review_sample_size": len(strengths),
        "authority_proxy": round(authority, 3),
        "top3_relevance": round(top3_share, 3),
        "method": "full" if robust else "adaptive_small_sample",
    }
