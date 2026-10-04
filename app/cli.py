"""Command line: run scans without the web UI (e.g. weekly from Windows Task Scheduler).

    python -m app.cli scan --business "Joe's Plumbing, Austin TX" --keyword plumber --keyword "water heater repair"
    python -m app.cli scan --business-id 1 --keyword plumber --grid 7 --spacing 1km --center 30.27,-97.74
    python -m app.cli list
"""
import argparse
import asyncio
import logging
import sys

from . import db
from .grid import parse_distance_km
from .scan import create_scans, make_fetcher, run_scan


def print_grid(scan: dict) -> None:
    size = scan["grid_size"]
    cells = {(p["row"], p["col"]): p for p in scan["points"]}
    for r in range(size):
        line = []
        for c in range(size):
            p = cells.get((r, c))
            if not p or p["status"] != "ok":
                line.append("  ?")
            else:
                line.append(f"{p['rank']:>3}" if p["rank"] else "20+")
        print(" ".join(line))


def print_summary(scan: dict) -> None:
    print(f"\nScan #{scan['id']}  {scan['business_name']}  \"{scan['keyword']}\"  "
          f"{scan['grid_size']}x{scan['grid_size']} @ {scan['spacing_km']} km  -> {scan['status']}")
    if scan["status"] == "failed":
        print("  error:", scan["error"])
    if scan.get("points"):
        print_grid(scan)
    m = scan.get("metrics")
    if m:
        print(f"  ARP {m['arp']}  ATRP {m['atrp']}  SoLV {m['solv']}%  found {m['found_pct']}%  errors {m['errors']}")
    for i, comp in enumerate((scan.get("competitors") or [])[:5], 1):
        print(f"  #{i} {comp['name']}  SoLV {comp['solv']}%  ATRP {comp['atrp']}")


async def cmd_scan(args) -> int:
    fetcher = make_fetcher()
    try:
        if args.business_id:
            biz = db.get_business(args.business_id)
            if not biz:
                print(f"no business with id {args.business_id}", file=sys.stderr)
                return 2
        else:
            print(f"Looking up {args.business!r} ...")
            info = await fetcher.resolve_business(args.business)
            biz = db.get_business(db.upsert_business(info))
            print(f"  -> {biz['name']} (id {biz['id']}, cid {biz['cid']}) at {biz['lat']},{biz['lng']}")
        center = tuple(float(x) for x in args.center.split(",")) if args.center else None
        try:
            scan_ids = create_scans(biz, args.keyword, args.grid, parse_distance_km(args.spacing), center)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        exit_code = 0
        for scan_id in scan_ids:
            scan = db.get_scan(scan_id, with_points=False)
            print(f"Scanning \"{scan['keyword']}\" ({scan['total']} points) ...")
            await run_scan(scan_id, fetcher, args.concurrency)
            scan = db.get_scan(scan_id)
            print_summary(scan)
            if scan["status"] != "done":
                exit_code = 1
        return exit_code
    finally:
        await fetcher.close()


def cmd_list(_args) -> int:
    for b in db.list_businesses():
        print(f"business {b['id']}: {b['name']}  ({b['lat']},{b['lng']})")
    for s in db.list_scans(limit=30):
        m = s["metrics"] or {}
        print(f"scan {s['id']}: {s['created']}  {s['business_name']}  \"{s['keyword']}\"  {s['grid_size']}x{s['grid_size']}"
              f"  {s['status']}  ARP {m.get('arp')}  SoLV {m.get('solv')}")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="geogrid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("scan", help="run a geo-grid scan")
    who = sp.add_mutually_exclusive_group(required=True)
    who.add_argument("--business", help="Google Maps link or 'Name, City'")
    who.add_argument("--business-id", type=int, help="id of a saved business (see `list`)")
    sp.add_argument("--keyword", action="append", required=True, help="repeat for several keywords")
    sp.add_argument("--grid", type=int, default=7, help="odd size 3..13 (default 7)")
    sp.add_argument("--spacing", default="1km", help="distance between points: 1km, 0.5mi, 800m (default 1km)")
    sp.add_argument("--center", help="lat,lng (default: the business location)")
    sp.add_argument("--concurrency", type=int, default=None)
    sub.add_parser("list", help="list saved businesses and recent scans")
    args = ap.parse_args(argv)
    db.init_db()
    if args.cmd == "scan":
        return asyncio.run(cmd_scan(args))
    return cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
