from app import main


def listing(
    name,
    cid,
    place_id,
    category,
    rating=4.5,
    reviews=100,
):
    return {
        "name": name,
        "cid": cid,
        "place_id": place_id,
        "category": category,
        "rating": rating,
        "reviews": reviews,
    }


def test_scan_analysis_exposes_indicators_from_saved_results(monkeypatch):
    target = listing(
        "Target Marketing",
        "target-cid",
        "target-place",
        "Marketing agency",
        4.8,
        250,
    )
    direct = listing("Direct competitor", "direct-cid", "direct-place", "Marketing agency")
    indirect = listing("Indirect competitor", "indirect-cid", "indirect-place", "Advertising agency")
    keyword_only = listing(
        "Marketing agency search result",
        "keyword-cid",
        "keyword-place",
        "Computer store",
    )
    points = [
        {
            "row": 0,
            "col": index,
            "lat": 0,
            "lng": index,
            "rank": 1 if index == 0 else None,
            "status": "ok",
            "results": [target, direct, indirect, keyword_only],
        }
        for index in range(3)
    ]
    monkeypatch.setattr(
        main.db,
        "get_scan",
        lambda scan_id: {
            "id": scan_id,
            "keyword": "marketing agency",
            "business_name": "Target Marketing",
            "business_cid": "target-cid",
            "business_place_id": "target-place",
            "business_category": "Marketing agency",
            "points": points,
        },
    )

    result = main.scan_analysis(
        10,
        ["Marketing agency"],
        ["Advertising agency"],
    )

    assert result["icm"]["score"] is not None
    assert result["icpb_v2"]["score"] is not None
    assert result["icpb_v2"]["excluded_target_occurrences"] == 3
    assert result["ice"]["counts"] == {
        "direct": 1,
        "indirect": 1,
        "keyword_only": 1,
        "indeterminate": 0,
    }
    assert result["iop"]["score"] is not None
    assert result["iop"]["status"] == "prototype_unvalidated"
    assert result["ida_average"] is None
    assert all(
        point["difficulty"]["reason"] == "amostra_pequena"
        for point in result["points"]
    )


def test_scan_analysis_withholds_target_metrics_without_official_id(monkeypatch):
    monkeypatch.setattr(
        main.db,
        "get_scan",
        lambda scan_id: {
            "id": scan_id,
            "keyword": "marketing agency",
            "business_name": "Target Marketing",
            "business_cid": None,
            "business_place_id": None,
            "business_category": "Marketing agency",
            "points": [
                {
                    "row": 0,
                    "col": 0,
                    "rank": None,
                    "status": "ok",
                    "results": [
                        listing("A", "a", "place-a", "Marketing agency"),
                        listing("B", "b", "place-b", "Marketing agency"),
                        listing("C", "c", "place-c", "Marketing agency"),
                    ],
                }
            ],
        },
    )

    result = main.scan_analysis(11, None, None)

    assert result["icm"]["score"] is None
    assert result["icpb_v2"]["score"] is None
    assert result["ice"]["reason"] == "target_identity_unavailable"
    assert result["iop"]["score"] is None
    assert all(point["difficulty"]["ida"] is None for point in result["points"])
