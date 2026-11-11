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
