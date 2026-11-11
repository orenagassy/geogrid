"""Find the target business inside a list of Maps results."""
import re
import unicodedata

_STOPWORDS = {"the", "llc", "inc", "co", "ltd", "corp", "company", "and"}


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("&", " and ")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _STOPWORDS]
    return " ".join(words)


def find_rank(results: list[dict], target: dict) -> int | None:
    """Find target rank without accepting conflicting official identifiers."""
    target_cid = str(target.get("cid") or "").strip()
    target_place = str(target.get("place_id") or "").strip()
    target_name = normalize_name(target.get("name") or "")

    def matches(result):
        cid = str(result.get("cid") or "").strip()
        place = str(result.get("place_id") or "").strip()

        if target_cid and cid and target_cid != cid:
            return False
        if target_place and place and target_place != place:
            return False

        if target_cid and cid == target_cid:
            return True
        if target_place and place == target_place:
            return True

        return (
            bool(target_name)
            and normalize_name(result.get("name") or "") == target_name
        )

    for position, result in enumerate(results, 1):
        if isinstance(result, dict) and matches(result):
            return position

    return None
