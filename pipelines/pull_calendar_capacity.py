"""pull_calendar_capacity.py — GHL calendar saturation snapshot → fact_calendar_capacity.

For each closeuse calendar (VSL + Standard), pulls:
  1. /calendars/{id}/free-slots → slots libres next 14 days (API)
  2. fact_call (Supabase) → slots déjà bookés (status != 'cancelled')

Computes per-day:
  - slots_booked = COUNT(fact_call) for this calendar/day, status actif
  - slots_free   = COUNT(slots in API response for this day)
  - slots_total  = booked + free  (capacity totale ouverte ce jour)
  - utilization_pct = booked / total

This avoids the openHours-empty issue (GHL stores availability at user level,
not always exposed at calendar level). Free + booked = ground truth capacity.

Stored append-only with snapshot_at — trend analysis enabled (e.g., detect
"utilization > 90% over 3 consecutive weeks" → recruit signal).

Usage:
  python -m pipelines.pull_calendar_capacity [--days 14]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from pipelines.lib.db import sb, upsert
from pipelines.lib.retry import retry_call

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

# Calendars Léa (cf CLAUDE.md projet)
CALENDARS = [
    ("8ECqPVcPGz81JGlzCmoG", "VSL"),
    ("AQ8RmdYw7iyru79Axymf", "Standard (Setting)"),
    # Bienvenue calendar = post-vente, pas critique pour capacity acquisition
    # ("BCghpu5fgGfkROyaQge5", "Bienvenue"),
]

GHL_BASE = "https://services.leadconnectorhq.com"


def make_session() -> requests.Session:
    api_key = os.environ.get("GHL_API_KEY")
    if not api_key:
        print("[capacity] GHL_API_KEY missing in .env.local", file=sys.stderr)
        raise SystemExit(1)
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Version": "2021-07-28",
        "Accept": "application/json",
        # Cloudflare 1010 blocks urllib default UA — use browser-like UA.
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    return s


def fetch_calendar_config(s: requests.Session, calendar_id: str) -> dict:
    r = s.get(f"{GHL_BASE}/calendars/{calendar_id}", timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"calendar config HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("calendar", {}) or {}


def fetch_free_slots(s: requests.Session, calendar_id: str, days: int) -> dict:
    start_ms = int(datetime.now().timestamp() * 1000)
    end_ms = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)
    r = s.get(
        f"{GHL_BASE}/calendars/{calendar_id}/free-slots",
        params={"startDate": start_ms, "endDate": end_ms, "timezone": "Europe/Paris"},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"free-slots HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def fetch_booked_slots_per_day(calendar_id: str, days: int) -> dict[str, int]:
    """Count active bookings per target_date for a calendar via supabase-py SDK.

    Active = status NOT IN ('cancelled'). Returns {date_iso: count}.
    """
    today = date.today()
    end = today + timedelta(days=days + 1)
    res = (
        sb().table("fact_call")
        .select("scheduled_at,status")
        .eq("calendar_id", calendar_id)
        .gte("scheduled_at", today.isoformat())
        .lt("scheduled_at", end.isoformat())
        .limit(2000)
        .execute()
    )
    out: dict[str, int] = {}
    for row in res.data or []:
        st = (row.get("status") or "").lower()
        if st == "cancelled":
            continue
        ts = row.get("scheduled_at")
        if not ts:
            continue
        d_iso = ts[:10]  # YYYY-MM-DD
        out[d_iso] = out.get(d_iso, 0) + 1
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()

    s = make_session()
    snapshot_at = datetime.now().isoformat()
    rows: list[dict] = []

    for calendar_id, label in CALENDARS:
        try:
            cfg = fetch_calendar_config(s, calendar_id)
        except Exception as e:
            print(f"[capacity] {label}: config failed → {e}", file=sys.stderr)
            continue

        cal_name = cfg.get("name") or label
        slot_duration = int(cfg.get("slotDuration") or 30)
        slot_unit = cfg.get("slotDurationUnit", "mins").lower()
        if "hour" in slot_unit:
            slot_duration *= 60
        team_count = len(cfg.get("teamMembers") or [])

        time.sleep(0.4)  # gentle to GHL
        try:
            slots_data = fetch_free_slots(s, calendar_id, args.days)
        except Exception as e:
            print(f"[capacity] {label}: free-slots failed → {e}", file=sys.stderr)
            continue

        # Pull bookings count per day from fact_call
        booked_by_day = fetch_booked_slots_per_day(calendar_id, args.days)

        today = date.today()
        for offset in range(args.days + 1):
            d = today + timedelta(days=offset)
            d_iso = d.isoformat()

            # slots_free = ce que l'API GHL dit dispo (live)
            day_block = slots_data.get(d_iso) or {}
            slots_arr = day_block.get("slots") if isinstance(day_block, dict) else None
            slots_free = len(slots_arr) if isinstance(slots_arr, list) else 0

            # slots_booked = bookings actifs déjà pris (fact_call)
            slots_booked = booked_by_day.get(d_iso, 0)

            slots_total = slots_booked + slots_free
            utilization = round(slots_booked / slots_total * 100, 1) if slots_total > 0 else None

            rows.append({
                "snapshot_at": snapshot_at,
                "calendar_id": calendar_id,
                "calendar_name": cal_name,
                "target_date": d_iso,
                "slots_total": slots_total,
                "slots_free": slots_free,
                "slots_booked": slots_booked,
                "utilization_pct": utilization,
                "slot_duration_min": slot_duration,
                "working_minutes": None,  # not exposed at calendar level
                "team_member_count": team_count,
                "raw": None,
            })

        print(f"[capacity] {label}: {team_count} TM · slot {slot_duration}min · {args.days+1} days analyzed")

    if not rows:
        print("[capacity] no rows produced")
        return 1

    # Append-only insert (snapshot per run for trend analysis)
    retry_call(
        lambda: sb().table("fact_calendar_capacity").insert(rows).execute(),
        label="insert fact_calendar_capacity",
    )

    # Quick summary print
    by_cal: dict[str, dict] = {}
    today = date.today()
    for r in rows:
        d = date.fromisoformat(r["target_date"])
        if d < today or (d - today).days > 3:  # focus on next 72h
            continue
        b = by_cal.setdefault(r["calendar_name"], {"total": 0, "booked": 0, "free": 0})
        b["total"] += r["slots_total"]
        b["booked"] += r["slots_booked"]
        b["free"] += r["slots_free"]

    print("\n[capacity] Saturation 72h prochaines:")
    for name, agg in by_cal.items():
        util = round(agg["booked"] / agg["total"] * 100, 1) if agg["total"] > 0 else None
        emoji = "🔴" if util and util > 90 else "🟠" if util and util > 85 else "🟢" if util and util >= 70 else "🟡"
        print(f"  {emoji} {name}: {agg['booked']}/{agg['total']} bookés ({util}%) · {agg['free']} libres")

    print(f"\n[capacity] inserted {len(rows)} rows for snapshot {snapshot_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
