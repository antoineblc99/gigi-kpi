"""Orchestrator: run Meta + GHL + vTurb backfills in sequence."""
import argparse
from datetime import date

from dateutil.parser import parse as parse_date

import backfill_meta
import backfill_ghl
import backfill_vturb


DEFAULT_START = {
    "meta": "2026-03-05",    # Follow campaign launch
    "ghl": "2026-03-05",     # aligned with Meta
    "vturb": "2026-04-09",   # VSL campaign launch
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="Override start date for all backfills (YYYY-MM-DD)")
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    ap.add_argument("--force", action="store_true", help="Re-write existing rows")
    ap.add_argument("--skip", nargs="*", default=[], choices=["meta", "ghl", "vturb"],
                    help="Skip specific backfills")
    args = ap.parse_args()

    end = parse_date(args.end).date()

    for name, module in (("meta", backfill_meta), ("ghl", backfill_ghl), ("vturb", backfill_vturb)):
        if name in args.skip:
            continue
        start_str = args.start or DEFAULT_START[name]
        start = parse_date(start_str).date()
        print(f"\n{'=' * 60}\n▶️  {name.upper()}  {start} → {end}\n{'=' * 60}")
        module.run(start, end, force=args.force)


if __name__ == "__main__":
    main()
