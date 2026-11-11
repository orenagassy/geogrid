import pytest

from app.competitive_metrics import (
    brand_confidence,
    classify_competitors,
    keyword_competition_v2,
    position_opportunity,
    target_brand_confidence,
)
from app.metrics import point_difficulty


TARGET = {
    "business_cid": "target-cid",
    "business_place_id": "target-place",
}


def business(cid, category="Marketing agency", rating=4.5, reviews=100, **extra):
    return {
        "name": f"Business {cid}",
        "cid": cid,
        "place_id": f"place-{cid}",
        "category": category,
        "rating": rating,
        "reviews": reviews,
        **extra,
    }


def test_ida_marks_experimental_evidence_without_claiming_confidence():
    results = [
        business(str(index))
        for index in range(5)
    ]

    result = point_difficulty(
        results,
        ["Marketing agency"],
    )

    assert result["ida"] is not None
    assert result["method"] == "full"
    assert result["evidence"] == "descriptive"
    assert result["confidence"] == "not_estimated"


def test_ida_does_not_count_unreviewed_top_three_as_relevance():
    results = [
        business("1", rating=None, reviews=None),
        business("2", rating=6, reviews=100),
        business("3", rating=4.5, reviews=1.5),
        business("4"),
        business("5"),
    ]

    result = point_difficulty(results, ["Marketing agency"])

    assert result["ida"] is not None
    assert result["review_sample_size"] == 2
    assert result["top3_relevance"] == 0


def test_ida_deduplicates_official_id_before_sample_gate():
    repeated = business("same")

    result = point_difficulty(
        [repeated, repeated, repeated],
        ["Marketing agency"],
    )

    assert result["ida"] is None
    assert result["sample_size"] == 1
    assert result["reason"] == "amostra_pequena"


def test_ida_excludes_target_by_official_identity():
    target = {
        "name": "Target",
        "cid": "target-cid",
        "place_id": "target-place",
        "category": "Marketing agency",
        "rating": 4.9,
        "reviews": 500,
    }
    results = [
        target,
        business("a"),
        business("b"),
    ]

    result = point_difficulty(
        results,
        ["Marketing agency"],
        target=TARGET,
    )

    assert result["ida"] is not None
    assert result["excluded_target_occurrences"] == 1
    assert result["sample_size"] == 2
    assert result["relevant_count"] == 2


def test_ida_requires_target_identity_when_explicitly_requested():
    result = point_difficulty(
        [business("a"), business("b"), business("c")],
        ["Marketing agency"],
        target={"business_cid": None},
    )

    assert result["ida"] is None
    assert result["reason"] == "target_identity_unavailable"


def test_ida_requires_two_valid_review_observations_for_small_sample():
    results = [
        business("a", reviews=-1),
        business("b", rating=6),
    ]

    result = point_difficulty(
        results,
        ["Marketing agency"],
    )

    assert result["ida"] is None
    assert result["reason"] == "avaliacoes_indisponiveis"
    assert result["review_sample_size"] == 0


def test_target_icm_requires_consistent_observations():
    target_listing = business(
        "target-cid",
        place_id="target-place",
        rating=4.7,
        reviews=125,
    )
    points = [
        {"status": "ok", "results": [target_listing]},
        {"status": "ok", "results": [dict(target_listing)]},
    ]

    result = target_brand_confidence(points, TARGET)

    assert result["score"] == brand_confidence(4.7, 125)["score"]
    assert result["observed_occurrences"] == 2


def test_target_icm_withholds_score_for_inconsistent_observations():
    points = [
        {
            "status": "ok",
            "results": [business("target-cid", place_id="target-place")],
        },
        {
            "status": "ok",
            "results": [
                business(
                    "target-cid",
                    place_id="target-place",
                    rating=4.8,
                    reviews=300,
                )
            ],
        },
    ]

    result = target_brand_confidence(points, TARGET)

    assert result["score"] is None
    assert result["reason"] == "inconsistent_target_observations"


@pytest.mark.parametrize(
    "category,name,expected",
    [
        ("Marketing agency", "Same category", "direct"),
        ("Advertising agency", "Adjacent category", "indirect"),
        ("Computer store", "Marketing agency Austin", "keyword_only"),
        ("Computer store", "Local retailer", "indeterminate"),
    ],
)
def test_ice_uses_explicit_category_and_keyword_evidence(
    category,
    name,
    expected,
):
    listing = business("competitor", category=category, name=name)
    result = classify_competitors(
        [{"status": "ok", "results": [listing]}],
        target=TARGET,
        target_category="Marketing agency",
        keyword="marketing agency",
        related_categories=["Advertising agency"],
    )

    assert result["businesses"][0]["classification"] == expected


def test_ice_excludes_target_and_counts_unidentified_records_as_indeterminate():
    target_listing = {
        "name": "Target",
        "cid": "target-cid",
        "place_id": "target-place",
        "category": "Marketing agency",
    }
    points = [
        {
            "status": "ok",
            "results": [target_listing, {"name": "Unknown", "category": "Marketing agency"}],
        }
    ]

    result = classify_competitors(
        points,
        target=TARGET,
        target_category="Marketing agency",
        keyword="marketing agency",
    )

    assert result["excluded_target_occurrences"] == 1
    assert result["unresolved_occurrences"] == 1
    assert result["counts"]["indeterminate"] == 1
    assert result["counts"]["direct"] == 0


def test_ice_marks_inconsistent_category_evidence_indeterminate():
    points = [
        {
            "status": "ok",
            "results": [business("same", category="Marketing agency")],
        },
        {
            "status": "ok",
            "results": [business("same", category="Computer store")],
        },
    ]

    result = classify_competitors(
        points,
        target=TARGET,
        target_category="Marketing agency",
        keyword="marketing agency",
    )

    assert result["counts"]["indeterminate"] == 1
    assert result["businesses"][0]["reason"] == "inconsistent_category_observations"


def test_ice_does_not_infer_indirect_competition_without_related_category():
    result = classify_competitors(
        [
            {
                "status": "ok",
                "results": [
                    business("adjacent", category="Advertising agency", name="Adjacent company")
                ],
            }
        ],
        target=TARGET,
        target_category="Marketing agency",
        keyword="marketing agency",
    )

    assert result["counts"]["indirect"] == 0
    assert result["counts"]["indeterminate"] == 1


def test_iop_prototype_reports_components_and_hypotheses():
    points = [
        {"status": "ok", "row": 0, "col": 0, "rank": 1},
        {"status": "ok", "row": 0, "col": 1, "rank": 20},
        {"status": "ok", "row": 1, "col": 0, "rank": None},
    ]
    competition = {
        "score": 50,
        "average_strength": 0.6,
        "territorial_recurrence": 0.5,
        "usable_point_coverage_pct": 100,
    }

    result = position_opportunity(points, competition)

    assert result["score"] == pytest.approx(55.8)
    assert result["status"] == "prototype_unvalidated"
    assert result["weights"] == {
        "position_gap": 0.5,
        "competition_ease": 0.25,
        "territorial_ease": 0.25,
    }
    assert result["points"][0]["score"] == 22.5
    assert result["points"][1]["score"] == 72.5
    assert result["points"][2]["score"] == 72.5
    assert "probability" not in result
    assert "confidence" not in result


def test_iop_withholds_score_when_point_coverage_is_insufficient():
    result = position_opportunity(
        [
            {"status": "ok", "rank": 8},
            {"status": "error", "rank": None},
            {"status": "error", "rank": None},
        ],
        {
            "score": 50,
            "average_strength": 0.5,
            "territorial_recurrence": 0.5,
            "usable_point_coverage_pct": 100,
        },
    )

    assert result["score"] is None
    assert result["reason"] == "insufficient_point_coverage"


def test_iop_withholds_score_when_usable_rank_coverage_is_insufficient():
    points = [
        {"status": "ok", "rank": 4},
        {"status": "ok", "rank": "invalid"},
        {"status": "ok", "rank": True},
        {"status": "ok", "rank": 12},
    ]
    competition = {
        "score": 50,
        "average_strength": 0.5,
        "territorial_recurrence": 0.5,
        "usable_point_coverage_pct": 100,
    }

    result = position_opportunity(points, competition)

    assert result["score"] is None
    assert result["reason"] == "insufficient_position_coverage"
    assert result["usable_point_coverage_pct"] == 50.0


def test_iop_withholds_score_when_competition_has_identity_conflicts():
    conflicted = business("200", place_id="shared-place")
    conflicting = business("300", place_id="shared-place")
    independent = [
        business("400"),
        business("500"),
        business("600"),
    ]
    points = [
        {
            "status": "ok",
            "rank": 4,
            "results": [conflicted, conflicting, *independent],
        }
        for _ in range(3)
    ]

    competition = keyword_competition_v2(
        points,
        target={"business_cid": "target"},
    )
    result = position_opportunity(points, competition)

    assert competition["score"] is None
    assert competition["reason"] == "conflicting_identifiers"
    assert result["score"] is None
    assert result["reason"] == "conflicting_identifiers"
    assert result["status"] == "prototype_unvalidated"


def test_iop_retains_a_valid_zero_score():
    result = position_opportunity(
        [{"status": "ok", "rank": 1}],
        {
            "score": 100,
            "average_strength": 1,
            "territorial_recurrence": 1,
            "usable_point_coverage_pct": 100,
        },
        min_point_coverage=0.5,
        min_usable_point_coverage=0.5,
    )

    assert result["score"] == 0
