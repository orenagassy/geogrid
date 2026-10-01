"""Paid fallback fetcher: DataForSEO Google Maps SERP API (~$0.002/point on the live endpoint).

Set DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD and GEOGRID_FETCHER=dataforseo.
Business lookup (one request per new business) still uses the free Playwright resolver.
"""
import os

import httpx

from .base import MAX_RESULTS, FetchError

ENDPOINT = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"


class DataForSEOFetcher:
    def __init__(self, login: str | None = None, password: str | None = None, zoom: int = 14, lang: str = "en"):
        login = login or os.environ.get("DATAFORSEO_LOGIN")
        password = password or os.environ.get("DATAFORSEO_PASSWORD")
        if not login or not password:
            raise RuntimeError("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set")
        self.zoom, self.lang = zoom, lang
        self._client = httpx.AsyncClient(auth=(login, password), timeout=90)
        self._resolver = None

    async def fetch(self, keyword: str, lat: float, lng: float) -> list[dict]:
        body = [{"keyword": keyword, "location_coordinate": f"{lat},{lng},{self.zoom}z",
                 "language_code": self.lang, "depth": MAX_RESULTS}]
        try:
            resp = await self._client.post(ENDPOINT, json=body)
            resp.raise_for_status()
            task = resp.json()["tasks"][0]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise FetchError(f"DataForSEO request failed: {e}") from e
        if task.get("status_code") != 20000:
            raise FetchError(f"DataForSEO: {task.get('status_message')}")
        items = ((task.get("result") or [{}])[0] or {}).get("items") or []
        out = []
        for it in items:
            if it.get("type") != "maps_search":  # skips maps_paid_item (ads)
                continue
            rating = it.get("rating") or {}
            out.append({
                "name": it.get("title"),
                "cid": str(it["cid"]) if it.get("cid") else None,
                "place_id": it.get("place_id"),
                "lat": it.get("latitude"),
                "lng": it.get("longitude"),
                "rating": rating.get("value"),
                "reviews": rating.get("votes_count"),
                "category": it.get("category"),
                "address": it.get("address"),
            })
        return out[:MAX_RESULTS]

    async def resolve_business(self, query: str) -> dict:
        if self._resolver is None:
            from .playwright_maps import PlaywrightMapsFetcher
            self._resolver = PlaywrightMapsFetcher()
        return await self._resolver.resolve_business(query)

    async def close(self) -> None:
        await self._client.aclose()
        if self._resolver:
            await self._resolver.close()
