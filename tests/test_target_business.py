import pytest

from app.competitor_identity import is_target_business


@pytest.mark.parametrize("result,target,expected,reason", [
    (
        {"cid": "123", "place_id": "abc"},
        {"business_cid": "123", "business_place_id": "abc"},
        True,
        "official_identifier_match",
    ),
    (
        {"place_id": "abc"},
        {"business_cid": "123", "business_place_id": "abc"},
        True,
        "official_identifier_match",
    ),
    (
        {"name": "Clínica Saúde", "cid": "456"},
        {"business_name": "Clínica Saúde", "business_cid": "123"},
        False,
        "different_official_identifier",
    ),
    (
        {"cid": "123", "place_id": "xyz"},
        {"business_cid": "123", "business_place_id": "abc"},
        None,
        "conflicting_identifiers",
    ),
    (
        {"cid": "456", "place_id": "abc"},
        {"business_cid": "123", "business_place_id": "abc"},
        None,
        "conflicting_identifiers",
    ),
    (
        {"name": "Clínica Saúde"},
        {"business_name": "Clínica Saúde", "business_cid": "123"},
        None,
        "insufficient_identifiers",
    ),
    (
        {"cid": "123"},
        {"business_cid": "123"},
        True,
        "official_identifier_match",
    ),
])
def test_target_identification(result, target, expected, reason):
    decision = is_target_business(result, target)

    assert decision["is_target"] is expected
    assert decision["reason"] == reason


def test_invalid_target_input():
    decision = is_target_business({"cid": "123"}, None)

    assert decision["is_target"] is None
    assert decision["reason"] == "invalid_input"
