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
    """1-based rank of target in results, or None. Matches on CID first, then exact normalized name."""
    cid = target.get("cid")
    if cid:
        for i, r in enumerate(results, 1):
            if r.get("cid") == cid:
                return i
    want = normalize_name(target.get("name", ""))
    if want:
        for i, r in enumerate(results, 1):
            if normalize_name(r.get("name", "")) == want:
                return i
    return None
