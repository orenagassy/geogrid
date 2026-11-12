from app.competitor_identity import (
    business_identity,
    normalize_business_name,
)


def test_identity_by_cid():
    result = business_identity({
        "name": "Clínica Saúde",
        "cid": "123",
        "place_id": "abc",
    })
    assert result["key"] == "cid:123"
    assert result["status"] == "identified"
    assert result["place_id"] == "abc"


def test_identity_by_place_id():
    result = business_identity({
        "name": "Clínica Saúde",
        "place_id": "abc",
    })
    assert result["key"] == "place_id:abc"


def test_same_name_different_cids():
    first = business_identity({
        "name": "Clínica Saúde",
        "cid": "123",
    })
    second = business_identity({
        "name": "Clínica Saúde",
        "cid": "456",
    })
    assert first["key"] != second["key"]


def test_missing_identifiers_remains_unresolved():
    result = business_identity({
        "name": "Clínica Saúde",
    })
    assert result["key"] is None
    assert result["status"] == "unresolved"


def test_normalize_business_name():
    assert (
        normalize_business_name("  Clínica   São-José! ")
        == "clinica sao jose"
    )


def test_cid_and_place_id_have_distinct_namespaces():
    cid = business_identity({"cid": "123"})
    place = business_identity({"place_id": "123"})
    assert cid["key"] != place["key"]


def test_invalid_result():
    result = business_identity(None)
    assert result["status"] == "invalid"
    assert result["key"] is None
