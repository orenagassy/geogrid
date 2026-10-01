import pytest

from app.fetchers.base import parse_place_url
from app.grid import haversine_km, make_grid, parse_distance_km
from app.matching import find_rank, normalize_name
from app.metrics import competitor_leaderboard, scan_metrics


# ---- grid ----
@pytest.mark.parametrize("size", [3, 7, 13])
def test_grid_point_count_and_center(size):
    pts = make_grid(30.0, -97.0, size, 1.0)
    assert len(pts) == size * size
    mid = pts[len(pts) // 2]
    assert (mid.row, mid.col) == (size // 2, size // 2)
    assert mid.lat == pytest.approx(30.0) and mid.lng == pytest.approx(-97.0)


def test_grid_spacing_and_orientation():
    pts = {(p.row, p.col): p for p in make_grid(45.0, 10.0, 5, 2.0)}
    a, east, south = pts[(2, 2)], pts[(2, 3)], pts[(3, 2)]
    assert haversine_km(a.lat, a.lng, east.lat, east.lng) == pytest.approx(2.0, rel=1e-3)
    assert haversine_km(a.lat, a.lng, south.lat, south.lng) == pytest.approx(2.0, rel=1e-3)
    assert east.lng > a.lng and south.lat < a.lat


@pytest.mark.parametrize("size", [2, 4, 1, 15])
def test_grid_rejects_bad_sizes(size):
    with pytest.raises(ValueError):
        make_grid(0, 0, size, 1)


@pytest.mark.parametrize("raw,km", [("1km", 1), ("0.5 mi", 0.804672), ("800m", 0.8), ("2", 2), (1.5, 1.5)])
def test_parse_distance(raw, km):
    assert parse_distance_km(raw) == pytest.approx(km)


# ---- matching ----
RESULTS = [
    {"name": "Austin Plumbery", "cid": "1"},
    {"name": "Radiant Plumbing, Air Conditioning, & Electrical", "cid": "2"},
    {"name": "Joe's Plumbing LLC", "cid": None},
]


def test_find_rank_by_cid_wins_over_name():
    assert find_rank(RESULTS, {"cid": "2", "name": "something else"}) == 2


def test_find_rank_by_normalized_name():
    assert find_rank(RESULTS, {"cid": None, "name": "joes plumbing"}) == 3
    assert find_rank(RESULTS, {"cid": None, "name": "Joe’s Plumbing, LLC"}) == 3


def test_find_rank_not_found():
    assert find_rank(RESULTS, {"cid": "99", "name": "Nobody"}) is None


def test_normalize_name():
    assert normalize_name("The Plumbing Co. & Sons, LLC") == "plumbing sons"


# ---- metrics ----
def test_scan_metrics():
    m = scan_metrics([1, 2, 5, None])
    assert m["arp"] == pytest.approx(8 / 3, abs=0.01)
    assert m["atrp"] == pytest.approx((1 + 2 + 5 + 21) / 4)
    assert m["solv"] == 50.0
    assert m["found_pct"] == 75.0


def test_scan_metrics_nothing_found():
    m = scan_metrics([None, None])
    assert m["arp"] is None and m["atrp"] == 21 and m["solv"] == 0


def test_competitor_leaderboard():
    a, b, c = {"name": "A", "cid": "a"}, {"name": "B", "cid": "b"}, {"name": "C", "cid": "c"}
    board = competitor_leaderboard([[a, b, c], [b, a], [b, a, a]])  # duplicate A in last point counted once
    assert [x["name"] for x in board] == ["B", "A", "C"]
    by = {x["name"]: x for x in board}
    assert by["B"]["solv"] == 100.0 and by["B"]["atrp"] == pytest.approx(4 / 3, abs=0.01)
    assert by["C"]["found_pct"] == pytest.approx(33.3) and by["C"]["atrp"] == pytest.approx((3 + 21 + 21) / 3)


# ---- place url ----
def test_parse_place_url():
    url = ("https://www.google.com/maps/place/Economy+Plumbing/data=!4m7!3m6!1s0x8644b50bd9aa02cf:0xc40446deb336af45"
           "!8m2!3d30.2603828!4d-97.7042995!16s%2Fg%2F1yj4k3914!19sChIJzwKq2Qu1RIYRRa82s95GBMQ?authuser=0")
    assert parse_place_url(url) == {"cid": str(0xC40446DEB336AF45), "place_id": "ChIJzwKq2Qu1RIYRRa82s95GBMQ",
                                    "lat": 30.2603828, "lng": -97.7042995}
