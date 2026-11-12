from app.competitive_metrics import keyword_competition


def business(name, cid, rating=4.5, reviews=100):
    return {
        "name": name, "cid": cid,
        "rating": rating, "reviews": reviews,
    }


def point(results, status="ok"):
    return {"status": status, "results": results}


def test_no_points():
    assert keyword_competition([])["score"] is None


def test_insufficient_points():
    result = keyword_competition([point([business("A", "a")])])
    assert result["reason"] == "insufficient_valid_points"


def test_duplicate_business_not_counted_twice():
    a = business("A", "a")
    b = business("B", "b")
    c = business("C", "c")
    result = keyword_competition([
        point([a, a, b, c]),
        point([b, a, c]),
        point([c, b, a]),
    ])
    assert result["unique_businesses"] == 3
    assert result["score"] is not None


def test_missing_reviews_block_score():
    businesses = [
        business("A", "a", reviews=None),
        business("B", "b", reviews=None),
        business("C", "c", reviews=100),
    ]
    result = keyword_competition([point(businesses)] * 3)
    assert result["score"] is None
    assert result["reason"] == "insufficient_review_coverage"


def test_failed_points_reduce_coverage():
    businesses = [
        business("A", "a"),
        business("B", "b"),
        business("C", "c"),
    ]
    result = keyword_competition(
        [point(businesses)] * 3 + [point([], "error")]
    )
    assert result["point_coverage_pct"] == 75.0
    assert result["evidence"] == "limited"


def test_stronger_competitors_increase_score():
    weak = [
        business("A", "a", 3.0, 10),
        business("B", "b", 3.0, 10),
        business("C", "c", 3.0, 10),
    ]
    strong = [
        business("A", "a", 4.9, 500),
        business("B", "b", 4.9, 500),
        business("C", "c", 4.9, 500),
    ]
    low = keyword_competition([point(weak)] * 3)
    high = keyword_competition([point(strong)] * 3)
    assert high["score"] > low["score"]


def test_insufficient_spatial_coverage_blocks_score():
    businesses = [
        business("A", "a", 4.7, 100),
        business("B", "b", 4.6, 120),
        business("C", "c", 4.8, 150),
    ]

    points = (
        [point(businesses)] * 3
        + [point([])] * 2
    )

    result = keyword_competition(points)

    assert result["score"] is None
    assert result["reason"] == "insufficient_spatial_coverage"
    assert result["usable_point_coverage_pct"] == 60.0


def test_eighty_percent_spatial_coverage_allows_score():
    businesses = [
        business("A", "a", 4.7, 100),
        business("B", "b", 4.6, 120),
        business("C", "c", 4.8, 150),
    ]

    points = (
        [point(businesses)] * 4
        + [point([])]
    )

    result = keyword_competition(points)

    assert result["usable_point_coverage_pct"] == 80.0
    assert result["score"] is not None
    assert result["reason"] is None


def test_duplicate_results_do_not_change_competition_score():
    a = business("Empresa A", "a", 4.9, 500)
    b = business("Empresa B", "b", 4.5, 100)
    c = business("Empresa C", "c", 4.0, 30)

    normal = [
        point([a, b, c])
        for _ in range(3)
    ]

    duplicated = [
        point([a, a, a, b, c])
        for _ in range(3)
    ]

    baseline = keyword_competition(normal)
    repeated = keyword_competition(duplicated)

    assert baseline["score"] is not None
    assert baseline["score"] == repeated["score"]
    assert baseline["unique_businesses"] == 3
    assert repeated["unique_businesses"] == 3
    assert baseline["top3_strength"] == repeated["top3_strength"]
