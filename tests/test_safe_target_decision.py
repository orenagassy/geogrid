from app.competitor_identity import (
    reconcile_business_identities,
    safe_target_decision,
)


def test_global_conflicts_block_target_identification():
    target = {
        "business_cid": "123",
        "business_place_id": "abc",
    }

    results = [
        {"name": "Empresa monitorada", "cid": "123", "place_id": "abc"},
        {"name": "Registro conflitante", "cid": "456", "place_id": "abc"},
        {"name": "Registro incompleto", "place_id": "abc"},
    ]

    reconciliation = reconcile_business_identities(results)

    assert reconciliation["conflict_count"] == 3

    for original, resolved in zip(
        results, reconciliation["records"]
    ):
        decision = safe_target_decision(
            original, target, resolved
        )

        assert decision["is_target"] is None
        assert decision["reason"] == "global_identifier_conflict"


def test_valid_identity_can_match_target():
    result = {"cid": "123", "place_id": "abc"}
    target = {
        "business_cid": "123",
        "business_place_id": "abc",
    }

    reconciliation = reconcile_business_identities([result])

    decision = safe_target_decision(
        result, target, reconciliation["records"][0]
    )

    assert decision["is_target"] is True


def test_unresolved_identity_is_not_classified():
    result = {"name": "Empresa sem identificador"}
    target = {"business_cid": "123"}

    reconciliation = reconcile_business_identities([result])

    decision = safe_target_decision(
        result, target, reconciliation["records"][0]
    )

    assert decision["is_target"] is None
    assert decision["reason"] == "identity_not_resolved"
