"""pull_instagram.py — Instagram follower_count daily delta → fact_ig_followers.

Pulls follower_count from Instagram Graph Insights API. This is the only reliable
source for "Followers gained" by Léa's IG account (@giginails77) — the metric
visible in Meta Ads Manager UI as "Followers sur Instagram" is NOT exposed at
the ad level via the standard /insights endpoint.

What we get: daily follower_count_delta for the entire @giginails77 account.
What we DON'T get: per-ad attribution (impossible without UI export).

Usage:
  python -m pipelines.pull_instagram [--days 90]

Env (loaded from .env.local):
  META_ACCESS_TOKEN   # System User token with instagram_basic + ads_read
  META_IG_USER_ID     # Default 17841448640931967 (Léa @giginails77)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb, upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")


def fetch_insights(ig_id: str, token: str, since: str, until: str) -> list[dict]:
    """GET /{ig_user_id}/insights?metric=follower_count."""
    url = (
        f"https://graph.facebook.com/v21.0/{ig_id}/insights"
        f"?metric=follower_count&period=day&since={since}&until={until}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Meta IG insights HTTP {e.code}: {body[:300]}") from e

    metric = (data.get("data") or [{}])[0]
    return metric.get("values") or []


def fetch_total(ig_id: str, token: str) -> int | None:
    url = f"https://graph.facebook.com/v21.0/{ig_id}?fields=followers_count"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return int(data.get("followers_count") or 0)
    except Exception as e:
        print(f"[ig] total fetch failed: {e}", file=sys.stderr)
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()

    token = os.environ.get("META_ACCESS_TOKEN")
    ig_id = os.environ.get("META_IG_USER_ID", "17841448640931967")
    if not token:
        print("[ig] META_ACCESS_TOKEN missing in .env.local", file=sys.stderr)
        return 1

    today = date.today()
    # Meta IG follower_count only supports last 30 days excluding current day.
    # Cap window at 29 days back from yesterday.
    max_lookback = min(args.days, 29)
    final_until = today - timedelta(days=1)
    final_since = today - timedelta(days=max_lookback)
    if max_lookback < args.days:
        print(f"[ig] WARN: requested {args.days}d but Meta caps at 29d — using {max_lookback}d")
    print(f"[ig] pulling follower_count {final_since} → {final_until} for IG user {ig_id}")

    values: list[dict] = fetch_insights(ig_id, token, final_since.isoformat(), final_until.isoformat())

    if not values:
        print("[ig] no data in window")
        return 0

    # Dedupe by end_time (chunks may overlap on the boundary day)
    seen = set()
    unique_values = []
    for v in values:
        et = v.get("end_time")
        if et and et not in seen:
            seen.add(et)
            unique_values.append(v)
    values = unique_values

    total_now = fetch_total(ig_id, token)

    rows = []
    for v in values:
        end = v.get("end_time")
        if not end:
            continue
        d = datetime.fromisoformat(end.replace("Z", "+00:00")).date()
        rows.append({
            "date": d.isoformat(),
            "follower_count_delta": int(v.get("value") or 0),
            "follower_count_total": None,  # only known for "today"
            "ig_user_id": ig_id,
        })

    # Stamp today's row with the total if we have it
    if total_now is not None and rows:
        rows[-1]["follower_count_total"] = total_now

    n = upsert("fact_ig_followers", rows, on_conflict="date")
    total_delta = sum(r["follower_count_delta"] for r in rows)
    print(f"[ig] upserted {n} daily rows · total followers gained {args.days}d = {total_delta}")
    if total_now is not None:
        print(f"[ig] account total followers now = {total_now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
