"""pull_tally.py — Tally EOD closeuse form → fact_eod_closeuse.

Two modes:
  1. Tally API if TALLY_API_KEY + TALLY_FORM_ID are set (preferred, automated).
  2. Fallback: read latest ~/Downloads/responses-*.csv (matching FORM_ID prefix).

Usage:
  python -m pipelines.pull_tally [--since-date YYYY-MM-DD] [--csv PATH]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from pipelines.lib.db import sb, slugify, upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

DOWNLOADS = Path.home() / "Downloads"
TALLY_API = "https://api.tally.so"

# Header → column mapping (CSV format)
CSV_HEADER_MAP = {
    "Prénom & Nom":                              "closer_name",
    "Nombre de calls planifiés":                 "calls_planifies",
    "Nombre de calls reçus":                     "calls_recus",
    "Nombre de follow up":                       "follow_ups",
    "Nombre d'acomptes":                         "acomptes",
    "Nombre de ventes provenant du Setting":     "ventes_setting",
    "Nombre de ventes provenant de la VSL":      "ventes_vsl",
    "Cash Contracté":                            "cash_contracte",
    "Cash Collecté":                             "cash_collecte",
    "Estimation de la qualification des leads":  "qualif_lead",
    "Débrief et commentaires sur la journée":    "debrief",
    "Submit Date (UTC)":                         "submit_date",
    "#":                                         "network_id",  # actual unique submission id in Tally CSV
}
FATHOM_PREFIX = "Enregistrement - Appel"


def _to_int(v):
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", ".").strip()))
    except ValueError:
        return None


def _to_num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ".").replace("€", "").replace("\xa0", "").strip())
    except ValueError:
        return None


def _parse_date(v: str) -> date | None:
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _ensure_closer(name: str) -> str | None:
    if not name:
        return None
    closer_id = slugify(name)
    sb().table("dim_closer").upsert(
        {"closer_id": closer_id, "name": name.strip()},
        on_conflict="closer_id",
    ).execute()
    return closer_id


def parse_csv_row(row: dict) -> dict | None:
    out: dict = {}
    norm = {k.strip(): v for k, v in row.items() if k}
    for src, dst in CSV_HEADER_MAP.items():
        v = norm.get(src) or norm.get(src + " ")
        if v is None:
            continue
        out[dst] = v.strip() if isinstance(v, str) else v

    if not out.get("network_id") or not out.get("closer_name"):
        return None

    submit = _parse_date(out.get("submit_date", ""))
    if submit is None:
        return None
    out["submit_date"] = submit.isoformat()

    fathom_urls = [
        v.strip() for k, v in norm.items()
        if k and k.startswith(FATHOM_PREFIX) and v and v.strip()
    ]
    out["fathom_urls"] = fathom_urls or None

    for k in ("calls_planifies", "calls_recus", "follow_ups", "acomptes",
              "ventes_setting", "ventes_vsl"):
        out[k] = _to_int(out.get(k))
    for k in ("cash_contracte", "cash_collecte", "qualif_lead"):
        out[k] = _to_num(out.get(k))

    out["closer_id"] = _ensure_closer(out["closer_name"])
    out["source"] = "tally"
    return out


def find_latest_csv() -> Path | None:
    matches = sorted(DOWNLOADS.glob("responses-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def load_from_csv(csv_path: Path, since: date | None) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            r = parse_csv_row(raw)
            if not r:
                continue
            if since and date.fromisoformat(r["submit_date"]) < since:
                continue
            rows.append(r)
    return rows


# ---- Tally API ----------------------------------------------------------------

def _tally_get(path: str, params: dict | None = None) -> dict:
    key = os.environ["TALLY_API_KEY"]
    r = requests.get(f"{TALLY_API}{path}", headers={"Authorization": f"Bearer {key}"}, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def load_from_tally(form_id: str, since: date | None) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = _tally_get(f"/forms/{form_id}/submissions", {"page": page, "limit": 100})
        items = data.get("submissions", [])
        if not items:
            break
        for sub in items:
            mapped = {f["label"].strip(): f.get("value") for f in sub.get("responses", [])}
            mapped["Submit Date (UTC)"] = sub.get("submittedAt") or sub.get("createdAt")
            mapped["Network ID"] = sub.get("id") or sub.get("submissionId")
            r = parse_csv_row(mapped)
            if not r:
                continue
            if since and date.fromisoformat(r["submit_date"]) < since:
                continue
            rows.append(r)
        if data.get("hasMore") is False or len(items) < 100:
            break
        page += 1
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since-date", type=str, default=None)
    p.add_argument("--csv", type=str, default=None, help="path to a Tally CSV export")
    args = p.parse_args()

    since = date.fromisoformat(args.since_date) if args.since_date else None

    rows: list[dict] = []
    api_key = os.environ.get("TALLY_API_KEY")
    form_id = os.environ.get("TALLY_FORM_ID")
    if api_key and form_id and not args.csv:
        print(f"[tally] pulling via API form={form_id} since={since}")
        rows = load_from_tally(form_id, since)
    else:
        path = Path(args.csv) if args.csv else find_latest_csv()
        if not path or not path.exists():
            print("[tally] no CSV found in ~/Downloads and TALLY_API_KEY/TALLY_FORM_ID not set", file=sys.stderr)
            return 1
        print(f"[tally] reading CSV: {path}")
        rows = load_from_csv(path, since)

    # dedupe by network_id within the batch (PostgREST upsert disallows dupes)
    seen: dict[str, dict] = {}
    for r in rows:
        seen[r["network_id"]] = r
    rows = list(seen.values())

    if not rows:
        print("[tally] 0 rows to upsert")
        return 0

    n = upsert("fact_eod_closeuse", rows, on_conflict="network_id")
    print(f"[tally] upserted {n} rows into fact_eod_closeuse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
