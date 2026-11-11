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
