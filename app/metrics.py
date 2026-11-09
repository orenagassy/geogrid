
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
    """Calculate an experimental local competition difficulty score.

    The score is based on:
    - Review strength of relevant competitors.
    - Google rating of relevant competitors.
    - Concentration of relevant businesses in the top 3.

    Important:
    - This is an experimental competition intensity proxy.
    - It does not measure total market density.
    - It does not measure actual geographic proximity.
    - It is not the proprietary Localo difficulty metric.
    """

    # --------------------------------------------------
    # 1. Validate results
    # --------------------------------------------------

    if not isinstance(results, list):
        return {
            "ida": None,
            "level": "dados_insuficientes",
            "confidence": "low",
            "reason": "resultados_invalidos",
        }

    # --------------------------------------------------
    # 2. Validate category configuration
    # --------------------------------------------------

    if not category_terms:
        return {
            "ida": None,
            "level": "dados_insuficientes",
            "confidence": "low",
            "reason": "categorias_nao_configuradas",
            "sample_size": len(results),
        }

    # --------------------------------------------------
    # 3. Filter relevant competitors
    # --------------------------------------------------

    relevant = [
        (index, result)
        for index, result in enumerate(results, 1)
        if (
            isinstance(result, dict)
            and _relevant(result, category_terms)
        )
    ]

    # --------------------------------------------------
    # 4. Validate sample size
    # --------------------------------------------------

    if (
        len(results) < min_results
        or len(relevant) < 3
    ):
        return {
            "ida": None,
            "level": "dados_insuficientes",
            "confidence": "low",
            "reason": "amostra_pequena",
            "sample_size": len(results),
            "relevant_count": len(relevant),
        }

    # --------------------------------------------------
    # 5. Calculate review strength
    # --------------------------------------------------

    strengths = []

    for _, result in relevant:

        try:
            if (
                result.get("reviews") is None
                or result.get("rating") is None
            ):
                continue

            reviews = max(
                0,
                float(result["reviews"]),
            )

            rating = max(
                0,
                min(
                    5,
                    float(result["rating"]),
                ),
            )

            review_strength = min(
                1,
                math.log1p(reviews) / math.log1p(1000),
            )

            strength = (
                review_strength * rating / 5
            )

            if not math.isfinite(strength):
                continue

            strengths.append(strength)

        except (TypeError, ValueError, OverflowError):
            continue

    # --------------------------------------------------
    # 6. Validate available review data
    # --------------------------------------------------

    if not strengths:
        return {
            "ida": None,
            "level": "dados_insuficientes",
            "confidence": "low",
            "reason": "avaliacoes_indisponiveis",
            "sample_size": len(results),
            "relevant_count": len(relevant),
        }

    # --------------------------------------------------
    # 7. Calculate competitor authority proxy
    # --------------------------------------------------

    authority = (
        sum(strengths) / len(strengths)
    )

    # --------------------------------------------------
    # 8. Calculate top-three relevance
    # --------------------------------------------------

    top3_share = (
        sum(
            1
            for index, _ in relevant
            if index <= 3
        ) / 3
    )

    # --------------------------------------------------
    # 9. Calculate experimental IDA
    # --------------------------------------------------

    score = round(
        100 * (
            0.65 * authority
            + 0.35 * top3_share
        ),
        1,
    )

    # --------------------------------------------------
    # 10. Classify difficulty
    # --------------------------------------------------

    if score < 35:
        level = "facil"

    elif score < 70:
        level = "medio"

    else:
        level = "dificil"

    # --------------------------------------------------
    # 11. Return analysis
    # --------------------------------------------------

    return {
        "ida": score,
        "level": level,
        "confidence": "experimental",
        "sample_size": len(results),
        "relevant_count": len(relevant),
        "authority_proxy": round(authority, 3),
        "top3_relevance": round(top3_share, 3),
    }
