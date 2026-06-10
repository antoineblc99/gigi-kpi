"""pull_vturb.py — rétention VSL (vTurb Analytics API) → fact_vsl_retention.

Une row par jour × player : events (started/viewed/finished), engagement moyen,
et la courbe de rétention seconde-par-seconde (jsonb). C'est la matière du
VSL Optimizer (où les viewers drop) — croisable avec fact_survey/fact_call
au niveau macro (par jour), pas par lead (l'API vTurb est agrégée).

API : https://vturb.gitbook.io/analytics-api — POST only, dates AVEC heures.
Référence locale : archives/vsl-analyzer-data-backup-20260501/references/vturb-api.md

Usage:
  python -m pipelines.pull_vturb [--days 14]

Env (.env.local):
  VTURB_API_TOKEN
  VTURB_PLAYER_ID   # défaut : VSL Lea 69a583a3260b750c46a983fb
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

BASE = "https://analytics.vturb.net"
DEFAULT_PLAYER = "69a583a3260b750c46a983fb"  # VSL Lea


def _req(path: str, body: dict | None, token: str, method: str = "POST") -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"X-Api-Token": token, "X-Api-Version": "v1", "Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"vTurb {path} HTTP {e.code}: {e.read().decode()[:300]}") from e
    raise RuntimeError(f"vTurb retries exhausted on {path}")


def day_bounds(d: date) -> tuple[str, str]:
    return f"{d.isoformat()} 00:00:00", f"{d.isoformat()} 23:59:59"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()

    token = os.environ.get("VTURB_API_TOKEN")
    player_id = os.environ.get("VTURB_PLAYER_ID", DEFAULT_PLAYER)
    if not token:
        print("[vturb] VTURB_API_TOKEN missing", file=sys.stderr)
        return 1

    players = {pl["id"]: pl for pl in _req("/players/list", None, token, method="GET")}
    player = players.get(player_id)
    if not player:
        print(f"[vturb] player {player_id} not found in /players/list", file=sys.stderr)
        return 1
    duration = int(player.get("duration") or 0)
    print(f"[vturb] player '{player['name']}' duration={duration}s · window {args.days}d")

    until = date.today() - timedelta(days=1)  # journée complète uniquement
    since = until - timedelta(days=args.days - 1)
    s_full, e_full = day_bounds(since)[0], day_bounds(until)[1]

    # 1 call pour les events de toute la fenêtre, par jour
    events_resp = _req("/events/total_by_company_day", {
        "player_id": player_id, "events": ["started", "viewed", "finished"],
        "start_date": s_full, "end_date": e_full, "timezone": "Europe/Paris",
    }, token)
    events_by_day: dict[str, dict[str, int]] = {}
    for ev in events_resp:
        for d in ev.get("events_by_day") or []:
            events_by_day.setdefault(d["day"], {})[ev["event"]] = int(d.get("total") or 0)

    # 1 call engagement (courbe) par jour
    rows = []
    for i in range(args.days):
        d = since + timedelta(days=i)
        s, e = day_bounds(d)
        eng = _req("/times/user_engagement", {
            "player_id": player_id, "video_duration": duration,
            "start_date": s, "end_date": e, "timezone": "Europe/Paris",
        }, token)
        ev = events_by_day.get(d.isoformat(), {})
        rows.append({
            "date": d.isoformat(),
            "player_id": player_id,
            "player_name": player.get("name"),
            "video_duration": duration,
            "views_started": ev.get("started", 0),
            "views_viewed": ev.get("viewed", 0),
            "views_finished": ev.get("finished", 0),
            "avg_watched_seconds": eng.get("average_watched_time"),
            "engagement_rate": eng.get("engagement_rate"),
            "retention_curve": eng.get("grouped_timed") or [],
        })
        time.sleep(1.1)  # rate limit Basic = 60 q/min

    n = upsert("fact_vsl_retention", rows, on_conflict="date,player_id")
    total_started = sum(r["views_started"] for r in rows)
    print(f"[vturb] upserted {n} daily rows · {total_started} starts sur {args.days}j")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
