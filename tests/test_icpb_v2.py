from app.competitive_metrics import keyword_competition_v2


def business(cid, place_id, rating=4.5, reviews=150):
    return {
        "name": f"Empresa {cid}",
        "cid": cid,
        "place_id": place_id,
        "rating": rating,
        "reviews": reviews,
    }


def point(*results):
    return {
        "status": "ok",
        "results": list(results),
    }


def test_v2_excludes_monitored_business():
    target = {
        "business_cid": "100",
        "business_place_id": "target",
    }

    points = [
        point(
            business("100", "target"),
            business("200", "competitor-a"),
            business("300", "competitor-b"),
            business("400", "competitor-c"),
        )
        for _ in range(3)
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["method"] == "icpb_v2_experimental"
    assert result["excluded_target_occurrences"] == 3
    assert result["unique_businesses"] == 3
    assert result["score"] is not None


def test_v2_blocks_conflicting_identifiers():
    target = {
        "business_cid": "100",
        "business_place_id": "target",
    }

    points = [
        point(
            business("200", "shared"),
            business("300", "shared"),
            business("400", "independent"),
        )
        for _ in range(3)
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["conflicting_occurrences"] == 6
    assert result["score"] is None


def test_v2_rejects_insufficient_points():
    target = {"business_cid": "100"}

    result = keyword_competition_v2(
        [point(business("200", "competitor"))],
        target=target,
    )

    assert result["score"] is None
    assert result["reason"] == "insufficient_valid_points"


def test_v2_requires_coverage_of_total_grid():
    target = {"business_cid": "target"}
    valid_points = [
        point(
            business("200", "a"),
            business("300", "b"),
            business("400", "c"),
        )
        for _ in range(3)
    ]
    points = valid_points + [
        {"status": "error", "results": []}
        for _ in range(97)
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["score"] is None
    assert result["reason"] == "insufficient_total_point_coverage"
    assert result["total_points"] == 100
    assert result["valid_points"] == 3
    assert result["point_coverage_pct"] == 3.0
    assert result["total_point_coverage_pct"] == 3.0
    assert result["usable_points"] == 3
    assert result["usable_point_coverage_pct"] == 100.0


def test_v2_accepts_total_point_coverage_exactly_at_minimum():
    target = {"business_cid": "target"}
    valid_points = [
        point(
            business("200", "a"),
            business("300", "b"),
            business("400", "c"),
        )
        for _ in range(4)
    ]
    points = valid_points + [{"status": "error", "results": []}]

    result = keyword_competition_v2(points, target=target)

    assert result["point_coverage_pct"] == 80.0
    assert result["score"] is not None
    assert result["reason"] is None


def test_v2_reports_identity_conflicts_when_other_coverage_is_sufficient():
    target = {"business_cid": "target"}
    points = [
        point(
            business("200", "shared"),
            business("300", "shared"),
            business("400", "independent-a"),
            business("500", "independent-b"),
            business("600", "independent-c"),
        )
        for _ in range(3)
    ]

    result = keyword_competition_v2(points, target=target)

    assert result["score"] is None
    assert result["reason"] == "conflicting_identifiers"
    assert result["point_coverage_pct"] == 100.0
    assert result["valid_points"] == 3
