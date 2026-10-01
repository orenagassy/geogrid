"""Runs the real in-page extraction JS against a saved Google Maps results page.

If Google changes its markup: save a fresh page (see README), replace fixtures/maps_results.html,
and fix EXTRACT_JS until this passes.
"""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.fetchers.base import MAX_RESULTS
from app.fetchers.playwright_maps import EXTRACT_JS, cards_to_results

FIXTURE = Path(__file__).parent / "fixtures" / "maps_results.html"


@pytest.fixture(scope="module")
def cards():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())  # offline: only the saved DOM matters
        page.set_content(FIXTURE.read_text(encoding="utf-8"), wait_until="domcontentloaded")
        data = page.evaluate(EXTRACT_JS)
        browser.close()
    return data


def test_extracts_cards(cards):
    assert len(cards) >= MAX_RESULTS
    assert all(c["name"] and c["href"] for c in cards)


def test_results_have_ids_and_fields(cards):
    results = cards_to_results(cards)
    assert len(results) == MAX_RESULTS
    assert len({r["cid"] for r in results}) == MAX_RESULTS
    for r in results:
        assert r["cid"].isdigit() and -90 < r["lat"] < 90 and -180 < r["lng"] < 180
    assert results[0]["name"] == "Economy Plumbing Services, LLC"
    assert results[0]["category"] == "Plumber"
    assert results[0]["address"] == "12, 701 Tillery St"
    assert results[0]["rating"] == 4.6


def test_sponsored_cards_are_skipped():
    cards = [{"name": "Ad Co", "href": "https://x/!1s0x1:0xa!3d1!4d2", "sponsored": True},
             {"name": "Real Co", "href": "https://x/!1s0x1:0xb!3d1!4d2", "sponsored": False}]
    assert [r["name"] for r in cards_to_results(cards)] == ["Real Co"]
