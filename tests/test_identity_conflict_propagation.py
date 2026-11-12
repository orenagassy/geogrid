from app.competitor_identity import reconcile_business_identities


def test_conflict_propagates_to_records_with_only_cid():
    results = [
        {"name": "Empresa A", "cid": "123", "place_id": "abc"},
        {"name": "Empresa B", "cid": "456", "place_id": "abc"},
        {"name": "Empresa A sem Place ID", "cid": "123"},
        {"name": "Empresa B sem Place ID", "cid": "456"},
        {"name": "Registro apenas Place ID", "place_id": "abc"},
    ]

    reconciliation = reconcile_business_identities(results)

    assert reconciliation["conflict_count"] == 5

    for record in reconciliation["records"]:
        assert record["status"] == "conflict"
        assert record["key"] is None
        assert record["reason"] == "identifier_conflict"


def test_conflict_propagates_through_connected_identifiers():
    results = [
        {"cid": "123", "place_id": "abc"},
        {"cid": "456", "place_id": "abc"},
        {"cid": "456", "place_id": "xyz"},
        {"cid": "789", "place_id": "xyz"},
        {"cid": "789"},
        {"place_id": "xyz"},
    ]

    reconciliation = reconcile_business_identities(results)

    assert reconciliation["conflict_count"] == 6

    for record in reconciliation["records"]:
        assert record["status"] == "conflict"
        assert record["key"] is None


def test_unrelated_business_remains_identified():
    results = [
        {"cid": "123", "place_id": "abc"},
        {"cid": "456", "place_id": "abc"},
        {"cid": "999", "place_id": "independent"},
    ]

    reconciliation = reconcile_business_identities(results)

    assert reconciliation["conflict_count"] == 2

    independent = reconciliation["records"][2]

    assert independent["status"] == "identified"
    assert independent["key"] == "cid:999"
