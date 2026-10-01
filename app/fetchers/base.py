"""Fetcher interface. A fetcher returns the top Maps results for a keyword searched from a lat/lng."""
import re
from typing import Protocol

MAX_RESULTS = 20


class FetchError(Exception):
    """A point could not be scanned (blocked, CAPTCHA, timeout)."""


class Fetcher(Protocol):
    async def fetch(self, keyword: str, lat: float, lng: float) -> list[dict]:
        """Ordered organic results (ads excluded), at most MAX_RESULTS dicts with keys:
        name, cid, place_id, lat, lng, rating, reviews, category, address."""
        ...

    async def resolve_business(self, query: str) -> dict:
        """Maps URL / share link / 'Name, City' -> {name, cid, place_id, lat, lng, address, category}."""
        ...

    async def close(self) -> None: ...


_CID_RE = re.compile(r"!1s0x[0-9a-f]+:0x([0-9a-f]+)")
_PLACE_ID_RE = re.compile(r"!19s(ChIJ[\w-]+)")
_LAT_RE = re.compile(r"!3d(-?\d+(?:\.\d+)?)")
_LNG_RE = re.compile(r"!4d(-?\d+(?:\.\d+)?)")


def parse_place_url(url: str) -> dict:
    """Pull cid / place_id / lat / lng out of a google.com/maps/place/... URL."""
    out: dict = {}
    if m := _CID_RE.search(url):
        out["cid"] = str(int(m.group(1), 16))
    if m := _PLACE_ID_RE.search(url):
        out["place_id"] = m.group(1)
    if (m1 := _LAT_RE.search(url)) and (m2 := _LNG_RE.search(url)):
        out["lat"], out["lng"] = float(m1.group(1)), float(m2.group(1))
    return out
