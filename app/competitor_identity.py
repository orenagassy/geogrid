"""Conservative business identity resolution for GeoGrid.

This module does not change the existing leaderboard.
"""
import re
import unicodedata


def normalize_business_name(value):
    if not isinstance(value, str):
        return ""

    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


def normalize_identifier(value):
    if value is None or isinstance(value, bool):
        return None

    value = str(value).strip()
    return value or None


def business_identity(result):
    """Return a typed identity and its evidence level.

    Name-only records remain unresolved: a shared name is
    insufficient evidence to merge separate establishments.
    """
    if not isinstance(result, dict):
        return {
            "key": None,
            "status": "invalid",
            "reason": "invalid_result",
        }

    cid = normalize_identifier(result.get("cid"))
    place_id = normalize_identifier(result.get("place_id"))
    name = normalize_business_name(result.get("name"))

    if cid:
        return {
            "key": f"cid:{cid}",
            "status": "identified",
            "reason": "cid",
            "cid": cid,
            "place_id": place_id,
        }

    if place_id:
        return {
            "key": f"place_id:{place_id}",
            "status": "identified",
            "reason": "place_id",
            "cid": None,
            "place_id": place_id,
        }

    return {
        "key": None,
        "status": "unresolved",
        "reason": "missing_official_identifier",
        "normalized_name": name,
    }


def reconcile_business_identities(results):
    """Reconcile official IDs and propagate conflicts across connected IDs."""

    records = [business_identity(result) for result in results]

    place_to_cids = {}
    cid_to_places = {}
    graph = {}

    def connect(left, right):
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)

    for record in records:
        cid = record.get("cid")
        place = record.get("place_id")

        if cid and place:
            place_to_cids.setdefault(place, set()).add(cid)
            cid_to_places.setdefault(cid, set()).add(place)
            connect(("cid", cid), ("place_id", place))

    conflicting_places = {
        place for place, cids in place_to_cids.items()
        if len(cids) > 1
    }
    conflicting_cids = {
        cid for cid, places in cid_to_places.items()
        if len(places) > 1
    }

    seeds = (
        {("place_id", place) for place in conflicting_places}
        | {("cid", cid) for cid in conflicting_cids}
    )

    conflicted_nodes = set(seeds)
    pending = list(seeds)

    while pending:
        current = pending.pop()

        for neighbor in graph.get(current, ()):
            if neighbor not in conflicted_nodes:
                conflicted_nodes.add(neighbor)
                pending.append(neighbor)

    resolved = []

    for record in records:
        item = dict(record)
        cid = item.get("cid")
        place = item.get("place_id")

        has_conflict = (
            (cid is not None and ("cid", cid) in conflicted_nodes)
            or (
                place is not None
                and ("place_id", place) in conflicted_nodes
            )
        )

        if has_conflict:
            item.update(
                status="conflict",
                reason="identifier_conflict",
                key=None,
            )
        elif cid:
            item["key"] = f"cid:{cid}"
        elif place:
            linked = place_to_cids.get(place, set())

            if len(linked) == 1:
                linked_cid = next(iter(linked))
                item["key"] = f"cid:{linked_cid}"
                item["reason"] = "linked_place_id"

        resolved.append(item)

    return {
        "records": resolved,
        "conflicting_places": sorted(conflicting_places),
        "conflicting_cids": sorted(conflicting_cids),
        "conflict_count": sum(
            record["status"] == "conflict"
            for record in resolved
        ),
        "unresolved_count": sum(
            record["status"] == "unresolved"
            for record in resolved
        ),
    }


def is_target_business(result, target):
    """Identify the monitored business using official identifiers.

    Returns a structured decision, not a name-based guess.
    """
    if not isinstance(result, dict) or not isinstance(target, dict):
        return {
            "is_target": None,
            "reason": "invalid_input",
        }

    result_cid = normalize_identifier(result.get("cid"))
    result_place = normalize_identifier(result.get("place_id"))

    target_cid = normalize_identifier(
        target.get("business_cid") or target.get("cid")
    )
    target_place = normalize_identifier(
        target.get("business_place_id") or target.get("place_id")
    )

    cid_match = bool(
        result_cid and target_cid and result_cid == target_cid
    )
    place_match = bool(
        result_place and target_place and result_place == target_place
    )

    cid_conflict = bool(
        result_cid and target_cid and result_cid != target_cid
    )
    place_conflict = bool(
        result_place and target_place and result_place != target_place
    )

    if (cid_match and place_conflict) or (
        place_match and cid_conflict
    ):
        return {
            "is_target": None,
            "reason": "conflicting_identifiers",
        }

    if cid_match or place_match:
        return {
            "is_target": True,
            "reason": "official_identifier_match",
        }

    if cid_conflict or place_conflict:
        return {
            "is_target": False,
            "reason": "different_official_identifier",
        }

    return {
        "is_target": None,
        "reason": "insufficient_identifiers",
    }


def classify_scan_result(result, resolved_identity, target):
    """Classify a scan result after global identity reconciliation.

    Global conflicts take precedence over individual identifier matches.
    """
    if not isinstance(resolved_identity, dict):
        return {
            "classification": "indeterminate",
            "reason": "missing_reconciliation",
        }

    status = resolved_identity.get("status")

    if status == "conflict":
        return {
            "classification": "indeterminate",
            "reason": "identifier_conflict",
        }

    if status != "identified" or not resolved_identity.get("key"):
        return {
            "classification": "indeterminate",
            "reason": "unresolved_identity",
        }

    decision = is_target_business(result, target)

    if decision["is_target"] is True:
        return {
            "classification": "target",
            "reason": decision["reason"],
        }

    if decision["is_target"] is False:
        return {
            "classification": "competitor",
            "reason": decision["reason"],
        }

    return {
        "classification": "indeterminate",
        "reason": decision["reason"],
    }



def safe_target_decision(result, target, reconciled_record):
    """Identify target only after global identity validation."""

    if not isinstance(reconciled_record, dict):
        return {
            "is_target": None,
            "reason": "missing_reconciliation",
        }

    status = reconciled_record.get("status")

    if status == "conflict":
        return {
            "is_target": None,
            "reason": "global_identifier_conflict",
        }

    if status != "identified" or not reconciled_record.get("key"):
        return {
            "is_target": None,
            "reason": "identity_not_resolved",
        }

    return is_target_business(result, target)
