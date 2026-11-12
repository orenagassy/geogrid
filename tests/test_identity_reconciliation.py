from app.competitor_identity import reconcile_business_identities


def test_links_place_id_to_known_cid():
    result = reconcile_business_identities([
        {"name": "Clínica Saúde", "cid": "123", "place_id": "abc"},
        {"name": "Clínica Saúde", "place_id": "abc"},
    ])

    records = result["records"]

    assert records[0]["key"] == "cid:123"
    assert records[1]["key"] == "cid:123"
    assert result["conflict_count"] == 0


def test_same_place_id_with_two_cids_is_conflict():
    result = reconcile_business_identities([
        {"cid": "123", "place_id": "abc"},
        {"cid": "456", "place_id": "abc"},
    ])

    assert result["conflict_count"] == 2
    assert all(r["key"] is None for r in result["records"])
    assert result["conflicting_places"] == ["abc"]


def test_same_cid_with_two_place_ids_is_conflict():
    result = reconcile_business_identities([
        {"cid": "123", "place_id": "abc"},
        {"cid": "123", "place_id": "xyz"},
    ])

    assert result["conflict_count"] == 2
    assert all(r["key"] is None for r in result["records"])
    assert result["conflicting_cids"] == ["123"]


def test_name_only_remains_unresolved():
    result = reconcile_business_identities([
        {"name": "Clínica Saúde"},
    ])

    assert result["records"][0]["key"] is None
    assert result["unresolved_count"] == 1


def test_place_only_record_inherits_conflict():
    result = reconcile_business_identities([
        {"cid": "123", "place_id": "abc"},
        {"cid": "456", "place_id": "abc"},
        {"place_id": "abc"},
    ])

    assert result["conflict_count"] == 3
    assert all(r["key"] is None for r in result["records"])


def test_indirect_conflict_propagates_to_place_only_record():
    """A place-only record must inherit a conflicting CID relationship."""
    result = reconcile_business_identities([
        {"name": "Empresa A", "cid": "123", "place_id": "abc"},
        {"name": "Empresa A", "cid": "123", "place_id": "xyz"},
        {"name": "Empresa A", "place_id": "abc"},
    ])

    assert result["conflict_count"] == 3
    assert result["conflicting_cids"] == ["123"]

    for record in result["records"]:
        assert record["status"] == "conflict"
        assert record["key"] is None
        assert record["reason"] == "identifier_conflict"


def test_chained_identifier_conflicts():
    """Conflicts must propagate through connected identifiers."""
    result = reconcile_business_identities([
        {"name": "Empresa A", "cid": "111", "place_id": "XYZ"},
        {"name": "Empresa B", "cid": "222", "place_id": "XYZ"},
        {"name": "Empresa B", "cid": "222", "place_id": "ABC"},
        {"name": "Empresa B", "place_id": "ABC"},
    ])

    assert result["conflict_count"] == 4
    assert result["conflicting_cids"] == ["222"]
    assert result["conflicting_places"] == ["XYZ"]

    for record in result["records"]:
        assert record["status"] == "conflict"
        assert record["key"] is None
        assert record["reason"] == "identifier_conflict"
