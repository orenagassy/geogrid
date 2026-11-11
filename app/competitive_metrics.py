"""Experimental Google review-based brand reputation indicator.

ICM is an observed reputation proxy, not a probability of trust.
Parameters are provisional and require empirical calibration.
"""
import math
import re
import unicodedata

METHOD = "icm_v1_experimental"
IOP_METHOD = "iop_prototype_v1"
IOP_WEIGHTS = {
    "position_gap": 0.50,
    "competition_ease": 0.25,
    "territorial_ease": 0.25,
}


def brand_confidence(rating, reviews, *, prior_mean=4.0, prior_weight=20,
                     volume_reference=1000):
    """Return reputation score and evidence metadata."""
    result = {
        "score": None,
        "method": METHOD,
        "evidence": "insufficient",
        "reason": None,
    }

    if rating is None or reviews is None:
        return {**result, "reason": "missing_data"}
    if isinstance(rating, bool) or isinstance(reviews, bool):
        return {**result, "reason": "invalid_data"}

    try:
        rating = float(rating)
        reviews_float = float(reviews)
    except (TypeError, ValueError, OverflowError):
        return {**result, "reason": "invalid_data"}

    if not (
        math.isfinite(rating)
        and math.isfinite(reviews_float)
        and 1 <= rating <= 5
        and reviews_float >= 0
        and reviews_float.is_integer()
    ):
        return {**result, "reason": "invalid_data"}

    reviews = int(reviews_float)

    if reviews == 0:
        return {**result, "reason": "no_reviews"}

    if not (
        1 <= prior_mean <= 5
        and prior_weight > 0
        and volume_reference > 1
    ):
        raise ValueError("Invalid calibration parameters")

    adjusted = (
        reviews * rating + prior_weight * prior_mean
    ) / (reviews + prior_weight)

    volume = min(
        1.0,
        math.log1p(reviews) / math.log1p(volume_reference)
    )

    score = 100 * (
        0.70 * adjusted / 5
        + 0.30 * volume
    )

    evidence = (
        "limited" if reviews < 20
        else "moderate" if reviews < 100
        else "substantial"
    )

    return {
        "score": round(score, 1),
        "method": METHOD,
        "evidence": evidence,
        "reason": None,
        "rating": rating,
        "reviews": reviews,
        "adjusted_rating": round(adjusted, 3),
        "volume_factor": round(volume, 3),
    }


def keyword_competition(points, *, min_valid_points=3,
                        min_unique_businesses=3,
                        min_review_coverage=0.6):
    """Experimental keyword competition pressure from observed Maps results.

    Uses unique businesses per point, preserving ranking positions.
    Does not treat neighboring grid points as independent observations.
    """
    from app.metrics import _competitor_key

    result = {
        "score": None,
        "method": "icpb_v1_experimental",
        "evidence": "insufficient",
        "reason": None,
    }

    if not isinstance(points, list) or not points:
        return {**result, "reason": "no_points"}

    valid = [p for p in points if p.get("status") == "ok"]
    total = len(points)

    if len(valid) < min_valid_points:
        return {
            **result,
            "reason": "insufficient_valid_points",
            "valid_points": len(valid),
            "total_points": total,
        }

    businesses = {}
    observed = []
    top3 = []

    for point in valid:
        seen = set()
        point_scores = []
        top_scores = []

        for business in point.get("results") or []:
            if not isinstance(business, dict):
                continue

            key = _competitor_key(business)
            if not key or key in seen:
                continue

            seen.add(key)
            position = len(seen)

            if key not in businesses:
                businesses[key] = business

            reputation = brand_confidence(
                business.get("rating"),
                business.get("reviews"),
            )

            if reputation["score"] is not None:
                strength = reputation["score"] / 100
                point_scores.append(strength)

                if position <= 3:
                    top_scores.append(strength)

        if point_scores:
            observed.append(sum(point_scores) / len(point_scores))

        if top_scores:
            top3.append(sum(top_scores) / len(top_scores))

    unique_count = len(businesses)

    reviewed = sum(
        brand_confidence(
            b.get("rating"),
            b.get("reviews"),
        )["score"] is not None
        for b in businesses.values()
    )

    review_coverage = reviewed / unique_count if unique_count else 0
    point_coverage = len(valid) / total
    usable_point_coverage = len(observed) / len(valid) if valid else 0

    metadata = {
        "valid_points": len(valid),
        "total_points": total,
        "unique_businesses": unique_count,
        "reviewed_businesses": reviewed,
        "review_coverage_pct": round(100 * review_coverage, 1),
        "point_coverage_pct": round(100 * point_coverage, 1),
        "usable_point_coverage_pct": round(100 * usable_point_coverage, 1),
    }

    if unique_count < min_unique_businesses:
        return {
            **result, **metadata,
            "reason": "insufficient_unique_businesses",
        }

    if review_coverage < min_review_coverage:
        return {
            **result, **metadata,
            "reason": "insufficient_review_coverage",
        }

    if not observed or not top3:
        return {
            **result, **metadata,
            "reason": "insufficient_reputation_data",
        }

    # Minimum usable geographic coverage.
    # Operational threshold; not a statistical confidence interval.
    if usable_point_coverage < 0.80:
        return {
            **result, **metadata,
            "reason": "insufficient_spatial_coverage",
        }

    # Equal weighting of valid, usable geographic points.
    # This is a descriptive grid score, not an independent-sample estimate.
    average_strength = sum(observed) / len(observed)
    top3_strength = sum(top3) / len(top3)

    score = 100 * (
        0.60 * average_strength
        + 0.40 * top3_strength
    )

    evidence = (
        "limited"
        if point_coverage < 0.8 or usable_point_coverage < 0.8
        else "descriptive"
    )

    return {
        **result,
        **metadata,
        "score": round(score, 1),
        "evidence": evidence,
        "reason": None,
        "average_strength": round(average_strength, 3),
        "top3_strength": round(top3_strength, 3),
    }


def keyword_competition_v2(
    points,
    *,
    target,
    min_valid_points=3,
    min_unique_businesses=3,
    min_review_coverage=0.6,
    min_point_coverage=0.8,
):
    """Experimental descriptive competition index, version 2.

    Grid points are spatially dependent. Scores require 80% total point
    coverage; conflicting complete rating observations for one identity are
    excluded from the reputation component rather than arbitrarily selected.
    This score is not a probability, confidence interval, or calibrated
    market estimate.
    """
    from collections import defaultdict

    from app.competitor_identity import (
        reconcile_business_identities,
        safe_target_decision,
    )

    base = {
        "score": None,
        "method": "icpb_v2_experimental",
        "evidence": "insufficient",
        "reason": None,
        "excluded_target_occurrences": 0,
        "conflicting_occurrences": 0,
        "unresolved_occurrences": 0,
        "total_points": 0,
        "valid_points": 0,
        "point_coverage_pct": 0.0,
        "total_point_coverage_pct": 0.0,
        "unique_businesses": 0,
        "usable_points": 0,
        "usable_point_coverage_pct": 0.0,
    }

    if not isinstance(points, list) or not points:
        return {**base, "reason": "no_points"}

    if not (
        isinstance(min_point_coverage, (int, float))
        and not isinstance(min_point_coverage, bool)
        and math.isfinite(min_point_coverage)
        and 0 < min_point_coverage <= 1
    ):
        return {**base, "reason": "coverage_threshold_invalid"}

    valid = [
        p for p in points
        if isinstance(p, dict) and p.get("status") == "ok"
    ]

    total = len(points)
    point_coverage = len(valid) / total

    # Reconcile all observed business identities together.
    occurrences = []

    for point_index, point in enumerate(valid):
        for position, business in enumerate(
            point.get("results") or [], start=1
        ):
            if isinstance(business, dict):
                occurrences.append(
                    (point_index, position, business)
                )

    reconciliation = reconcile_business_identities(
        [entry[2] for entry in occurrences]
    )

    by_point = defaultdict(dict)
    observations_by_identity = defaultdict(list)
    excluded_target = 0
    conflicting = 0
    unresolved = 0

    for (point_index, position, business), identity in zip(
        occurrences, reconciliation["records"]
    ):
        if identity["status"] == "conflict":
            conflicting += 1
            continue

        if identity["status"] != "identified" or not identity.get("key"):
            unresolved += 1
            continue

        decision = safe_target_decision(
            business, target, identity
        )

        if decision["is_target"] is True:
            excluded_target += 1
            continue

        if decision["is_target"] is None:
            unresolved += 1
            continue

        key = identity["key"]
        observations_by_identity[key].append(business)

        # Deduplicate within each point; keep first ranking position.
        if key in by_point[point_index]:
            continue

        by_point[point_index][key] = (position, business)

    # Territorial recurrence uses all identified, deduplicated
    # competitors, regardless of reputation availability.
    territorial_appearances = defaultdict(set)

    for point_index, businesses in by_point.items():
        for key in businesses:
            territorial_appearances[key].add(point_index)

    territorial_recurrence = (
        sum(
            len(point_ids) / len(valid)
            for point_ids in territorial_appearances.values()
        ) / len(territorial_appearances)
        if territorial_appearances else None
    )

    reputation_by_identity = {}
    inconsistent_review_businesses = 0
    unavailable_review_businesses = 0
    for key, observations in observations_by_identity.items():
        consistent_pairs = {}
        for business in observations:
            reputation = brand_confidence(
                business.get("rating"),
                business.get("reviews"),
            )
            if reputation["score"] is not None:
                pair = (reputation["rating"], reputation["reviews"])
                consistent_pairs[pair] = reputation

        if len(consistent_pairs) > 1:
            inconsistent_review_businesses += 1
        elif consistent_pairs:
            reputation_by_identity[key] = next(
                iter(consistent_pairs.values())
            )
        else:
            unavailable_review_businesses += 1

    unique_count = len(observations_by_identity)
    reviewed = len(reputation_by_identity)
    review_coverage = reviewed / unique_count if unique_count else 0
    usable_point_indexes = {
        point_index
        for point_index, businesses in by_point.items()
        if any(key in reputation_by_identity for key in businesses)
    }
    usable_points = len(usable_point_indexes)
    usable_coverage = usable_points / len(valid) if valid else 0.0
    metadata = {
        "territorial_recurrence": (
            round(territorial_recurrence, 3)
            if territorial_recurrence is not None
            else None
        ),
        "total_points": total,
        "valid_points": len(valid),
        "point_coverage_pct": round(100 * point_coverage, 1),
        "total_point_coverage_pct": round(100 * point_coverage, 1),
        "unique_businesses": unique_count,
        "excluded_target_occurrences": excluded_target,
        "conflicting_occurrences": conflicting,
        "unresolved_occurrences": unresolved,
        "reviewed_businesses": reviewed,
        "review_coverage_pct": round(100 * review_coverage, 1),
        "inconsistent_review_businesses": inconsistent_review_businesses,
        "unavailable_review_businesses": unavailable_review_businesses,
        "usable_points": usable_points,
        "usable_point_coverage_pct": round(100 * usable_coverage, 1),
    }

    if point_coverage < min_point_coverage:
        return {
            **base,
            **metadata,
            "reason": "insufficient_total_point_coverage",
        }

    if len(valid) < min_valid_points:
        return {
            **base,
            **metadata,
            "reason": "insufficient_valid_points",
        }

    if unique_count < min_unique_businesses:
        return {
            **base,
            **metadata,
            "reason": "insufficient_unique_businesses",
        }

    if review_coverage < min_review_coverage:
        return {
            **base,
            **metadata,
            "reason": "insufficient_review_coverage",
        }

    if conflicting:
        return {
            **base,
            **metadata,
            "reason": "conflicting_identifiers",
        }

    if unresolved:
        return {
            **base,
            **metadata,
            "reason": "unresolved_identifiers",
        }

    point_strengths = []
    for point_index, businesses in by_point.items():
        weighted_sum = 0.0
        weight_total = 0.0

        for key, (position, _) in businesses.items():
            reputation = reputation_by_identity.get(key)
            if reputation is None:
                continue

            # Provisional position discount, not calibrated.
            position_weight = 1 / position

            weighted_sum += (
                reputation["score"] / 100
            ) * position_weight

            weight_total += position_weight

        if weight_total:
            point_strengths.append(
                weighted_sum / weight_total
            )

    if usable_coverage < 0.8:
        return {
            **base,
            **metadata,
            "reason": "insufficient_spatial_coverage",
        }

    average_strength = (
        sum(point_strengths) / len(point_strengths)
    )

    # Recurrence is observed independently of reputation.
    recurrence = territorial_recurrence

    # Provisional weighting pending empirical calibration.
    score = 100 * (
        0.75 * average_strength
        + 0.25 * recurrence
    )

    return {
        **base,
        **metadata,
        "score": round(score, 1),
        "evidence": "descriptive",
        "reason": None,
        "average_strength": round(average_strength, 3),
        "territorial_recurrence": round(recurrence, 3),
    }


def target_brand_confidence(points, target):
    """Calculate ICM only from consistent, identified target observations."""
    from app.competitor_identity import (
        reconcile_business_identities,
        safe_target_decision,
    )

    base = {
        "score": None,
        "method": METHOD,
        "evidence": "insufficient",
        "reason": "target_not_observed",
        "observed_occurrences": 0,
    }

    if not isinstance(points, list) or not isinstance(target, dict):
        return {**base, "reason": "invalid_input"}
    if not any(
        target.get(key)
        for key in ("business_cid", "cid", "business_place_id", "place_id")
    ):
        return {**base, "reason": "target_identity_unavailable"}

    occurrences = [
        business
        for point in points
        if isinstance(point, dict) and point.get("status") == "ok"
        for business in (point.get("results") or [])
        if isinstance(business, dict)
    ]
    identities = reconcile_business_identities(occurrences)["records"]
    target_observations = []
    target_conflict = False

    for business, identity in zip(occurrences, identities):
        if identity["status"] == "conflict":
            target_cid = target.get("business_cid") or target.get("cid")
            target_place = (
                target.get("business_place_id") or target.get("place_id")
            )
            target_conflict |= bool(
                (target_cid and str(business.get("cid")) == str(target_cid))
                or (
                    target_place
                    and str(business.get("place_id")) == str(target_place)
                )
            )
            continue
        if identity["status"] != "identified" or not identity.get("key"):
            continue
        decision = safe_target_decision(business, target, identity)
        if decision["is_target"] is True:
            target_observations.append(business)

    if not target_observations:
        reason = "target_identity_conflict" if target_conflict else "target_not_observed"
        return {**base, "reason": reason}

    pairs = {
        (
            repr(business.get("rating")),
            repr(business.get("reviews")),
        )
        for business in target_observations
    }
    if len(pairs) > 1:
        return {
            **base,
            "reason": "inconsistent_target_observations",
            "observed_occurrences": len(target_observations),
        }

    observation = target_observations[0]
    return {
        **brand_confidence(
            observation.get("rating"),
            observation.get("reviews"),
        ),
        "observed_occurrences": len(target_observations),
    }


def _classification_text(value):
    """Normalize visible text for exact category and query evidence checks."""
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def _contains_phrase(text, phrase):
    text = _classification_text(text)
    phrase = _classification_text(phrase)
    return bool(text and phrase and f" {phrase} " in f" {text} ")


def classify_competitors(
    points,
    *,
    target,
    target_category,
    keyword,
    related_categories=None,
):
    """Classify identified listings using explicit, observed text evidence.

    Direct means an exact normalized category match. Indirect means an exact
    match to a supplied related category. Keyword-only requires an explicit
    query phrase in the listing name/category and a different known category.
    Everything else, including unresolved identities, remains indeterminate.
    """
    from app.competitor_identity import (
        reconcile_business_identities,
        safe_target_decision,
    )

    base = {
        "method": "ice_rules_v1_experimental",
        "evidence": "descriptive",
        "counts": {
            "direct": 0,
            "indirect": 0,
            "keyword_only": 0,
            "indeterminate": 0,
        },
        "businesses": [],
        "excluded_target_occurrences": 0,
        "conflicting_occurrences": 0,
        "unresolved_occurrences": 0,
    }

    if not isinstance(points, list):
        return {**base, "reason": "invalid_points"}

    valid_points = [
        point
        for point in points
        if isinstance(point, dict) and point.get("status") == "ok"
    ]
    occurrences = [
        (point_index, position, business)
        for point_index, point in enumerate(valid_points)
        for position, business in enumerate(point.get("results") or [], 1)
        if isinstance(business, dict)
    ]
    if not occurrences:
        return {**base, "reason": "no_observed_results"}

    if not isinstance(target, dict) or not any(
        target.get(key)
        for key in ("business_cid", "cid", "business_place_id", "place_id")
    ):
        return {
            **base,
            "reason": "target_identity_unavailable",
            "unresolved_occurrences": len(occurrences),
            "counts": {**base["counts"], "indeterminate": len(occurrences)},
        }

    reconciliation = reconcile_business_identities(
        [business for _, _, business in occurrences]
    )
    grouped = {}
    unresolved_entries = []
    excluded_target = 0
    conflicting = 0
    unresolved = 0

    for occurrence, identity in zip(occurrences, reconciliation["records"]):
        point_index, _, business = occurrence
        if identity["status"] == "conflict":
            conflicting += 1
            unresolved_entries.append({
                "name": business.get("name"),
                "category": business.get("category"),
                "classification": "indeterminate",
                "reason": "identifier_conflict",
                "evidence": [],
            })
            continue
        if identity["status"] != "identified" or not identity.get("key"):
            unresolved += 1
            unresolved_entries.append({
                "name": business.get("name"),
                "category": business.get("category"),
                "classification": "indeterminate",
                "reason": "official_identifier_missing",
                "evidence": [],
            })
            continue

        decision = safe_target_decision(business, target, identity)
        if decision["is_target"] is True:
            excluded_target += 1
            continue
        if decision["is_target"] is None:
            unresolved += 1
            unresolved_entries.append({
                "name": business.get("name"),
                "category": business.get("category"),
                "classification": "indeterminate",
                "reason": decision["reason"],
                "evidence": [],
            })
            continue

        entry = grouped.setdefault(
            identity["key"],
            {
                "business_key": identity["key"],
                "categories": set(),
                "names": set(),
                "point_indexes": set(),
                "occurrences": 0,
            },
        )
        category = business.get("category")
        name = business.get("name")
        if isinstance(category, str) and category.strip():
            entry["categories"].add(category.strip())
        if isinstance(name, str) and name.strip():
            entry["names"].add(name.strip())
        entry["point_indexes"].add(point_index)
        entry["occurrences"] += 1

    target_category_norm = _classification_text(target_category)
    related = {
        _classification_text(category)
        for category in (related_categories or [])
        if isinstance(category, str) and category.strip()
    }
    results = []

    for business_key in sorted(grouped):
        entry = grouped[business_key]
        categories = entry["categories"]
        names = entry["names"]
        category = sorted(categories)[0] if len(categories) == 1 else None
        observed_names = sorted(names)
        name = observed_names[0] if len(observed_names) == 1 else None
        category_norm = _classification_text(category)
        evidence = []
        reason = "insufficient_category_evidence"

        if len(categories) > 1:
            classification = "indeterminate"
            reason = "inconsistent_category_observations"
        elif category_norm and target_category_norm and category_norm == target_category_norm:
            classification = "direct"
            reason = "same_business_category"
            evidence.append({"source": "category", "value": category})
        elif category_norm and category_norm in related and category_norm != target_category_norm:
            classification = "indirect"
            reason = "configured_related_category"
            evidence.append({"source": "category", "value": category})
        else:
            matching_names = [
                observed_name
                for observed_name in observed_names
                if _contains_phrase(observed_name, keyword)
            ]
            keyword_in_category = _contains_phrase(category, keyword)
            if (
                category_norm
                and target_category_norm
                and category_norm not in related
                and (matching_names or keyword_in_category)
            ):
                classification = "keyword_only"
                reason = "query_phrase_in_name_with_different_category"
                evidence.extend(
                    {"source": "name", "value": observed_name}
                    for observed_name in matching_names
                )
                if keyword_in_category:
                    evidence.append({"source": "category", "value": category})
                evidence.append({"source": "keyword", "value": keyword})
            else:
                classification = "indeterminate"

        results.append({
            "business_key": entry["business_key"],
            "name": name,
            "observed_names": observed_names,
            "category": category,
            "classification": classification,
            "reason": reason,
            "evidence": evidence,
            "occurrences": entry["occurrences"],
            "point_count": len(entry["point_indexes"]),
        })

    counts = dict(base["counts"])
    for result in results:
        counts[result["classification"]] += 1
    counts["indeterminate"] += len(unresolved_entries)
    results.extend(unresolved_entries)
    results.sort(
        key=lambda result: (
            str(result.get("business_key") or ""),
            str(result.get("name") or ""),
            str(result.get("category") or ""),
        )
    )

    return {
        **base,
        "reason": None,
        "counts": counts,
        "businesses": results,
        "excluded_target_occurrences": excluded_target,
        "conflicting_occurrences": conflicting,
        "unresolved_occurrences": unresolved,
        "valid_points": len(valid_points),
        "total_points": len(points),
        "point_coverage_pct": (
            round(100 * len(valid_points) / len(points), 1)
            if points
            else 0.0
        ),
    }


def position_opportunity(
    points,
    competition,
    *,
    min_point_coverage=0.8,
    min_usable_point_coverage=0.8,
):
    """Return a provisional, descriptive IOP with explicit unvalidated weights.

    The candidate hypothesis rewards target ranking gaps and discounts
    opportunities where observed competitors are strong or recur broadly.
    It is a grid summary, not an independent-sample or probability estimate.
    """
    base = {
        "score": None,
        "method": IOP_METHOD,
        "status": "prototype_unvalidated",
        "evidence": "insufficient",
        "reason": None,
        "weights": dict(IOP_WEIGHTS),
        "hypothesis": (
            "A larger target ranking gap increases opportunity; stronger "
            "and more recurrent competitors reduce immediate opportunity."
        ),
        "points": [],
    }

    if not isinstance(points, list) or not points:
        return {**base, "reason": "no_points"}
    if not isinstance(competition, dict):
        return {**base, "reason": "competition_evidence_unavailable"}
    if competition.get("score") is None:
        return {
            **base,
            "reason": (
                competition.get("reason")
                or "competition_evidence_unavailable"
            ),
        }
    if not all(
        isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
        and math.isfinite(threshold)
        and 0 < threshold <= 1
        for threshold in (min_point_coverage, min_usable_point_coverage)
    ):
        return {**base, "reason": "coverage_threshold_invalid"}

    valid = [
        point
        for point in points
        if isinstance(point, dict) and point.get("status") == "ok"
    ]
    point_coverage = len(valid) / len(points)
    base["valid_points"] = len(valid)
    base["total_points"] = len(points)
    base["point_coverage_pct"] = round(100 * point_coverage, 1)

    if point_coverage < min_point_coverage:
        return {**base, "reason": "insufficient_point_coverage"}

    average_strength = competition.get("average_strength")
    recurrence = competition.get("territorial_recurrence")
    usable_coverage = competition.get("usable_point_coverage_pct")
    try:
        average_strength = float(average_strength)
        recurrence = float(recurrence)
        usable_coverage = float(usable_coverage) / 100
    except (TypeError, ValueError, OverflowError):
        return {**base, "reason": "competition_components_unavailable"}

    if not (
        math.isfinite(average_strength)
        and math.isfinite(recurrence)
        and math.isfinite(usable_coverage)
        and 0 <= average_strength <= 1
        and 0 <= recurrence <= 1
        and min_usable_point_coverage <= usable_coverage <= 1
    ):
        return {**base, "reason": "insufficient_competition_coverage"}

    competition_ease = 1 - average_strength
    territorial_ease = 1 - recurrence
    scored_points = []
    point_results = []

    for point in points:
        if not isinstance(point, dict) or point.get("status") != "ok":
            point_results.append({
                "row": point.get("row") if isinstance(point, dict) else None,
                "col": point.get("col") if isinstance(point, dict) else None,
                "score": None,
                "reason": "point_not_scanned",
            })
            continue

        rank = point.get("rank")
        if rank is None:
            position_gap = 1.0
        elif (
            isinstance(rank, bool)
            or not isinstance(rank, int)
            or not 1 <= rank <= 20
        ):
            point_results.append({
                "row": point.get("row"),
                "col": point.get("col"),
                "score": None,
                "reason": "rank_unavailable",
            })
            continue
        else:
            position_gap = (rank - 1) / 19

        score = 100 * (
            IOP_WEIGHTS["position_gap"] * position_gap
            + IOP_WEIGHTS["competition_ease"] * competition_ease
            + IOP_WEIGHTS["territorial_ease"] * territorial_ease
        )
        score = round(score, 1)
        scored_points.append(score)
        point_results.append({
            "row": point.get("row"),
            "col": point.get("col"),
            "score": score,
            "position_gap": round(position_gap, 3),
            "competition_ease": round(competition_ease, 3),
            "territorial_ease": round(territorial_ease, 3),
            "reason": None,
        })

    if not scored_points:
        return {
            **base,
            "reason": "no_usable_positions",
            "points": point_results,
        }

    usable_position_coverage = len(scored_points) / len(valid)
    if usable_position_coverage < min_usable_point_coverage:
        return {
            **base,
            "reason": "insufficient_position_coverage",
            "usable_points": len(scored_points),
            "usable_point_coverage_pct": round(
                100 * usable_position_coverage,
                1,
            ),
            "points": point_results,
        }

    return {
        **base,
        "score": round(sum(scored_points) / len(scored_points), 1),
        "evidence": "descriptive",
        "reason": None,
        "usable_points": len(scored_points),
        "usable_point_coverage_pct": round(100 * usable_position_coverage, 1),
        "average_strength": round(average_strength, 3),
        "territorial_recurrence": round(recurrence, 3),
        "points": point_results,
    }
