# GeoGrid: Free GBP / GMB Heatmap Rank Tracker

**See exactly where your Google Business Profile ranks, street by street. Free, open source, and running on your own computer.**

GeoGrid is a self-hosted, open-source alternative to paid GMB heatmap tools like Local Falcon, LeadSnap and LocalGrids. It puts a grid of points over your service area, searches Google Maps for your keyword from every point, and turns the results into a color-coded **Google Maps ranking heatmap**. You can see in seconds where you're in the Map Pack and where competitors take your customers.

No subscription. No per-scan credits. No API key needed.

![GeoGrid heatmap: a used car dealer ranking #1 across a 3×3 grid in Queens, NY, with the competitor leaderboard](docs/screenshot.png)

---

## Why GeoGrid?

Your Google Business Profile (formerly Google My Business / GMB) doesn't have *one* ranking. It has a different ranking on every street. A customer searching "plumber" two miles from your shop sees a different Map Pack than one standing at your front door. Regular rank trackers check one location and miss this.

Geo-grid tracking shows the full picture, and paid tools charge **$50–$100+ per month** for it. GeoGrid gives you the same core workflow for free.

| | Paid GMB heatmap tools | **GeoGrid** |
|---|---|---|
| Geo-grid heatmap (3×3 to 13×13) | ✅ | ✅ |
| ARP, ATRP & Share of Local Voice (SoLV) | ✅ | ✅ |
| Competitor leaderboard + "flip the map" | ✅ | ✅ |
| Scan history & change over time | ✅ | ✅ |
| Scheduled scans | ✅ | ✅ (Windows Task Scheduler / cron) |
| PDF reports | ✅ | ✅ |
| Monthly cost | $$$ | **$0** |
| Your data stays on your machine | ❌ | ✅ |
| Open source & hackable | ❌ | ✅ MIT |

## Features

- 🗺️ **GBP rank heatmaps.** Grids from 3×3 up to 13×13, with any spacing in km or miles. Drag the center pin to scan any neighborhood.
- 🎯 **Precise business matching.** Your listing is matched by its unique Google CID, not a fuzzy name match, so look-alike competitors never count as you.
- 📊 **Local SEO metrics:**
  - **ARP**: average rank where you appear.
  - **ATRP**: average rank across the whole grid.
  - **SoLV (Share of Local Voice)**: % of points where you're in the top 3 (the Map Pack).
  - **Found %**: % of points where you're in the top 20.
- 🥊 **Competitor intelligence.** Every business that ranks anywhere in your grid, sorted by SoLV. Click any competitor to **flip the map** and see their heatmap.
- 📍 **Point drill-down.** Click any point to see the full top-20 Google Maps results at that spot.
- 📈 **Track progress.** Each scan is saved. Switch to *Change vs previous* to see which points moved up or down after your GBP optimization work.
- 🔑 **Multiple keywords per run.** Scan "plumber", "emergency plumber" and "water heater repair" in one go.
- 🧾 **Client-ready PDF reports** in one click.
- ⏰ **Automated scans** from the command line. Schedule weekly runs and watch the trend.
- 🚫 **Ads excluded.** "Sponsored" listings don't distort your organic Map Pack rankings.
- 🔌 **Pluggable data source.** Free browser-based scanning by default, or switch to the DataForSEO API (about $0.002 per point) for high-volume agency use.

## Who it's for

- **Local businesses** that want to know if their Google Maps ranking reaches their whole service area
- **SEO agencies & freelancers** proving GBP optimization results to clients without a per-seat SaaS bill
- **Multi-location brands and dealerships** comparing Map Pack visibility across stores
- **Developers** who want a hackable local rank tracker to build on

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/geogrid.git
cd geogrid
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # macOS/Linux: .venv/bin/pip
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000** and:

1. **Add your business.** Paste its Google Maps link, or type `Business Name, City`.
2. **Enter keywords**, one per line, the way customers search, *without* the city (`used cars`, not `used cars queens`).
3. **Pick a grid.** For example, 7×7 at 1 km covers about 6×6 km. Drag the blue pin to move the center.
4. **Run the scan** and watch the heatmap fill in live.

**Color guide:** 🟢 1–3 (Map Pack), 🟡 4–10, 🟠 11–20, 🔴 not in the top 20.

## Command line & scheduled scans

```bash
python -m app.cli scan --business "Joe's Plumbing, Austin TX" --keyword plumber --keyword "water heater repair" --grid 7 --spacing 1km
python -m app.cli scan --business-id 1 --keyword plumber      # re-scan a saved business
python -m app.cli list                                         # saved businesses & recent scans
```

To scan automatically, schedule the `--business-id` command weekly with Windows Task Scheduler or cron. Results appear in the web UI history, ready for comparison.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GEOGRID_FETCHER` | `playwright` | `dataforseo` switches to the DataForSEO Maps API (set `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`) |
| `GEOGRID_CONCURRENCY` | `2` | Parallel searches per scan |
| `GEOGRID_PROXY` | none | Proxy, e.g. `http://user:pass@host:port` |
| `GEOGRID_HEADLESS` | `1` | Set `0` to watch the browser work |
| `GEOGRID_DB` | `geogrid.db` | SQLite database file |

## How it works

1. GeoGrid finds your business on Google Maps once and stores its CID and coordinates.
2. It builds an evenly spaced grid around the center you choose.
3. At each point, a fresh, cookie-free browser session searches Google Maps *as if standing at that spot* and reads the top 20 organic results.
4. It finds your rank at every point, computes the metrics, and stores everything in a local SQLite database.

**Tech:** Python · FastAPI · Playwright · SQLite · Leaflet + OpenStreetMap

```
app/
  grid.py              grid geometry
  fetchers/            data sources (Playwright = free, DataForSEO = paid API)
  matching.py          CID / name matching
  metrics.py           ARP, ATRP, SoLV, competitor leaderboard
  scan.py              scan runner
  main.py              web API
  cli.py               command line
  static/              web UI
tests/                 pytest suite, incl. parser test on a saved Maps page
```

## Responsible use

The free scanner automates searches on google.com/maps, which Google's Terms of Service don't allow. Keep the volume modest (a few scans a day is fine for checking your own businesses). If you scan heavily, Google will show CAPTCHAs; GeoGrid detects this, stops the scan and marks the affected points. For agency-scale volume, use the DataForSEO data source. You are responsible for how you use this tool.

If Google changes the Maps page layout and scans start coming back empty, see `tests/test_parser.py` and `EXTRACT_JS` in `app/fetchers/playwright_maps.py`. All selectors are kept in one place.

## Contributing

Issues and pull requests are welcome. Ideas on the roadmap:

- Circle and ZIP-code grid shapes
- Time-lapse GIF of ranking changes
- White-label report branding
- Review-count enrichment for competitors

Run the tests with:

```bash
python -m pytest -q
```

## License

[MIT](LICENSE). Free for personal and commercial use.

---

<sub>Keywords: GBP rank tracker, GMB heatmap, Google Business Profile heatmap, Google My Business rank tracker, local rank tracker, geo-grid rank tracking, Map Pack tracker, Google Maps rank checker, local SEO tool, Local Falcon alternative, open source local SEO.</sub>
