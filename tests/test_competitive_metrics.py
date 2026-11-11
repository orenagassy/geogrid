import pytest
from app.competitive_metrics import brand_confidence


def test_missing_data():
    assert brand_confidence(None, 10)["score"] is None


def test_no_reviews():
    assert brand_confidence(5, 0)["reason"] == "no_reviews"


@pytest.mark.parametrize("rating,reviews", [
    (6, 20), (0, 20), (4.5, -1),
    (float("nan"), 20), (4.5, float("inf")),
    (4.5, 1.5), ("invalid", 20),
])
def test_invalid_inputs(rating, reviews):
    assert brand_confidence(rating, reviews)["score"] is None


def test_more_evidence_reduces_small_sample_inflation():
    small = brand_confidence(5, 2)
    large = brand_confidence(5, 500)
    assert large["score"] > small["score"]


def test_score_is_bounded():
    for rating in (1, 3, 5):
        for reviews in (1, 20, 1000, 100000):
            score = brand_confidence(rating, reviews)["score"]
            assert 0 <= score <= 100


def test_evidence_is_separate_from_score():
    result = brand_confidence(4.8, 150)
    assert result["evidence"] == "substantial"
    assert result["method"] == "icm_v1_experimental"
