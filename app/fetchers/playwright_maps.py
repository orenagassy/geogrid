"""Free fetcher: drives a real (headless) Chromium on google.com/maps.

All DOM selectors live in EXTRACT_JS / the constants below, so when Google changes the page
there is one place to fix (re-run tests/test_parser.py against a freshly saved page).
"""
import asyncio
import random
from urllib.parse import quote

from playwright.async_api import Browser, Page, async_playwright

from .base import MAX_RESULTS, FetchError, parse_place_url

FEED = 'div[role="feed"]'
PLACE_TITLE = "h1"

# Runs inside the page; returns one dict per result card in feed order.
EXTRACT_JS = r"""
() => {
  const feed = document.querySelector('div[role="feed"]');
  if (!feed) return [];
  return [...feed.querySelectorAll('div[role="article"]')].map(card => {
    const link = card.querySelector('a.hfpxzc');
    const stars = card.querySelector('span[role="img"][aria-label*="star"]');
    const rows = [...card.querySelectorAll('.W4Efsd > .W4Efsd')];
    const firstRow = rows.length ? [...rows[0].children].map(s => s.innerText.replace(/^\s*·\s*/, '').trim()) : [];
    const label = stars ? stars.getAttribute('aria-label') : '';
    const reviews = (label.match(/([\d,]+)\s+Reviews?/i) || [])[1];
    return {
      name: link ? link.getAttribute('aria-label') : null,
      href: link ? link.href : null,
      rating: stars ? parseFloat(label) : null,
      reviews: reviews ? parseInt(reviews.replace(/,/g, '')) : null,
      category: firstRow[0] || null,
      address: firstRow[1] || null,
      sponsored: /\bSponsored\b/.test(card.innerText),
    };
  });
}
"""

PLACE_JS = r"""
() => {
  const h1 = document.querySelector('h1');
  const cat = document.querySelector('button[jsaction*="category"]');
  const addr = document.querySelector('button[data-item-id="address"]');
  const stars = document.querySelector('div.F7nice span[aria-hidden="true"]');
  return {
    name: h1 ? h1.innerText.trim() : null,
    category: cat ? cat.innerText.trim() : null,
    address: addr ? addr.innerText.split('\n').pop().trim() : null,
    rating: stars ? parseFloat(stars.innerText) : null,
  };
}
"""


def cards_to_results(cards: list[dict], limit: int = MAX_RESULTS) -> list[dict]:
    """Drop ads and broken cards, enrich with ids from the place URL, keep the first `limit`."""
    out, seen = [], set()
    for c in cards:
        if c.get("sponsored") or not c.get("name") or not c.get("href"):
            continue
        r = {k: c.get(k) for k in ("name", "rating", "reviews", "category", "address")}
        r.update(parse_place_url(c["href"]))
        key = r.get("cid") or r["name"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= limit:
            break
    return out


class PlaywrightMapsFetcher:
    def __init__(self, headless: bool = True, proxy: str | None = None, zoom: int = 14,
                 delay: tuple[float, float] = (2.0, 5.0), lang: str = "en"):
        self.headless, self.proxy, self.zoom, self.delay, self.lang = headless, proxy, zoom, delay, lang
        self._pw = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def _get_browser(self) -> Browser:
        async with self._lock:
            if self._browser is None:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(
                    headless=self.headless, proxy={"server": self.proxy} if self.proxy else None)
            return self._browser

    async def _new_page(self, lat: float | None = None, lng: float | None = None) -> Page:
        browser = await self._get_browser()
        geo = {"geolocation": {"latitude": lat, "longitude": lng}, "permissions": ["geolocation"]} if lat is not None else {}
        # Fresh context per point = no cookies / history personalization between points.
        ctx = await browser.new_context(locale=f"{self.lang}-US", viewport={"width": 1280, "height": 900}, **geo)
        return await ctx.new_page()

    @staticmethod
    def _check_blocked(page: Page) -> None:
        if "/sorry/" in page.url or "consent.google" in page.url:
            raise FetchError(f"blocked by Google ({page.url[:80]})")

    async def fetch(self, keyword: str, lat: float, lng: float) -> list[dict]:
        await asyncio.sleep(random.uniform(*self.delay))
        page = await self._new_page(lat, lng)
        try:
            url = f"https://www.google.com/maps/search/{quote(keyword)}/@{lat},{lng},{self.zoom}z?hl={self.lang}"
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            self._check_blocked(page)
            try:
                await page.wait_for_selector(f"{FEED}, {PLACE_TITLE}", timeout=20000)
            except Exception as e:
                self._check_blocked(page)
                raise FetchError(f"no results panel: {e}") from e
            if not await page.locator(FEED).count():
                # Maps jumped straight to a single place: that place is the only result.
                await page.wait_for_function("location.href.includes('!3d')", timeout=10000)
                info = await page.evaluate(PLACE_JS)
                return [{**info, "reviews": None, **parse_place_url(page.url)}] if info.get("name") else []
            return cards_to_results(await self._scroll_and_extract(page))
        finally:
            await page.context.close()

    async def _scroll_and_extract(self, page: Page) -> list[dict]:
        feed = page.locator(FEED)
        cards, stale = [], 0
        for _ in range(15):
            cards = await page.evaluate(EXTRACT_JS)
            if len(cards_to_results(cards)) >= MAX_RESULTS:
                break
            if await page.get_by_text("reached the end of the list").count():
                break
            before = len(cards)
            await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            await page.wait_for_timeout(1200)
            stale = stale + 1 if len(await page.evaluate(EXTRACT_JS)) == before else 0
            if stale >= 3:
                break
        return cards

    async def resolve_business(self, query: str) -> dict:
        page = await self._new_page()
        try:
            if query.startswith("http"):
                url = query
            else:
                url = f"https://www.google.com/maps/search/{quote(query)}?hl={self.lang}"
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            self._check_blocked(page)
            await page.wait_for_selector(f"{FEED}, {PLACE_TITLE}", timeout=20000)
            if await page.locator(FEED).count():
                # Several matches: take the first organic one.
                results = cards_to_results(await page.evaluate(EXTRACT_JS), limit=1)
                if not results:
                    raise FetchError(f"no business found for {query!r}")
                return results[0]
            await page.wait_for_function("location.href.includes('!3d')", timeout=15000)
            info = await page.evaluate(PLACE_JS)
            biz = {**info, **parse_place_url(page.url)}
            if not biz.get("name") or "lat" not in biz:
                raise FetchError(f"could not read business details for {query!r}")
            return biz
        finally:
            await page.context.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None
