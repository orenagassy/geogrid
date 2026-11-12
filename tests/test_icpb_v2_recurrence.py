import pytest

from app.competitive_metrics import keyword_competition_v2


def business(cid, rating=None, reviews=None):
    return {
        "name": f"Empresa {cid}",
        "cid": cid,
        "place_id": f"place-{cid}",
        "rating": rating,
        "reviews": reviews,
    }


def test_territorial_recurrence_independent_of_reviews():
    target = {"business_cid": "999"}

    unknown = business("400")

    points = [
        {
            "status": "ok",
            "results": [
                business("100", 4.8, 500),
                business("200", 4.5, 200),
                business("300", 4.2, 100),
                unknown,
            ],
        },
        {"status": "ok", "results": [unknown]},
        {"status": "ok", "results": [unknown]},
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["unique_businesses"] == 4
    assert result["review_coverage_pct"] == 75.0
    assert result["usable_point_coverage_pct"] == 33.3

    # The score must remain unavailable.
    assert result["score"] is None
    assert result["reason"] == "insufficient_spatial_coverage"

    # Territorial presence must be reported independently.
    assert result["territorial_recurrence"] == pytest.approx(0.5)


def test_recurrence_counts_each_business_once_per_point():
    target = {"business_cid": "999"}

    a = business("100", 4.8, 500)
    b = business("200", 4.5, 200)
    c = business("300", 4.2, 100)

    points = [
        {"status": "ok", "results": [a, a, b, c]},
        {"status": "ok", "results": [a, b, c]},
        {"status": "ok", "results": [a, b, c]},
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["unique_businesses"] == 3
    assert result["territorial_recurrence"] == pytest.approx(1.0)


def test_review_data_uses_consistent_observations_not_first_occurrence():
    target = {"business_cid": "999"}
    incomplete_a = business("100")
    complete_a = business("100", 4.8, 500)
    b = business("200", 4.5, 200)
    c = business("300", 4.2, 100)

    points = [
        {"status": "ok", "results": [incomplete_a, b, c]},
        {"status": "ok", "results": [complete_a, b, c]},
        {"status": "ok", "results": [complete_a, b, c]},
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["score"] is not None
    assert result["reviewed_businesses"] == 3
    assert result["review_coverage_pct"] == 100.0
    assert result["inconsistent_review_businesses"] == 0
    assert result["unavailable_review_businesses"] == 0


def test_divergent_review_observations_are_excluded_not_arbitrarily_selected():
    target = {"business_cid": "999"}
    a_first = business("100", 4.0, 100)
    a_second = business("100", 5.0, 500)
    b = business("200", 4.5, 200)
    c = business("300", 4.2, 100)
    d = business("400", 4.7, 300)

    conflicting_points = [
        {"status": "ok", "results": [a_first, b, c, d]},
        {"status": "ok", "results": [a_second, b, c, d]},
        {"status": "ok", "results": [a_first, b, c, d]},
    ]
    unavailable_a = business("100")
    comparison_points = [
        {"status": "ok", "results": [unavailable_a, b, c, d]}
        for _ in range(3)
    ]

    result = keyword_competition_v2(conflicting_points, target=target)
    comparison = keyword_competition_v2(comparison_points, target=target)

    assert result["score"] == comparison["score"]
    assert result["inconsistent_review_businesses"] == 1
    assert result["reviewed_businesses"] == 3
    assert result["review_coverage_pct"] == 75.0
    assert result["score"] is not None


def test_partial_review_observations_do_not_form_a_synthetic_pair():
    target = {"business_cid": "999"}
    partial_a = business("100", 4.8, None)
    partial_b = business("200", None, 200)
    c = business("300", 4.2, 100)

    result = keyword_competition_v2(
        [
            {"status": "ok", "results": [partial_a, partial_b, c]},
            {"status": "ok", "results": [partial_a, partial_b, c]},
            {"status": "ok", "results": [partial_a, partial_b, c]},
        ],
        target=target,
    )

    assert result["score"] is None
    assert result["reason"] == "insufficient_review_coverage"
    assert result["reviewed_businesses"] == 1
    assert result["unavailable_review_businesses"] == 2
