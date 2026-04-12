"""Backfill vTurb → VTurb_Raw (daily stats) + VTurb_Retention_Curve (aggregate snapshot)."""
import os
import time
from datetime import date, datetime, timedelta
from typing import Iterable

import requests

from auth import get_sheets_service

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
VTURB_BASE = "https://analytics.vturb.net"
VTURB_TOKEN = os.environ["VTURB_API_TOKEN"]

# Videos de Léa (filtre sur les videos pertinentes — évite de backfiller des videos personnelles)
RELEVANT_PLAYERS = {
    "69a583a3260b750c46a983fb": "VSL Lea",
}


def headers() -> dict:
    return {
        "X-Api-Token": VTURB_TOKEN,
        "X-Api-Version": "v1",
        "Content-Type": "application/json",
    }


def vturb_post(path: str, body: dict) -> dict:
    for attempt in range(3):
        r = requests.post(f"{VTURB_BASE}{path}", headers=headers(), json=body, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"vTurb {path} {r.status_code}: {r.text[:300]}")
    raise RuntimeError(f"vTurb retries exhausted on {path}")


def vturb_get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{VTURB_BASE}{path}", headers=headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def day_bounds_str(d: date) -> tuple[str, str]:
    return f"{d.isoformat()} 00:00:00 UTC", f"{d.isoformat()} 23:59:59 UTC"


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_all_players() -> list[dict]:
    return vturb_get("/players/list")


def session_stats(player_id: str, duration: int, d: date) -> dict:
    s, e = day_bounds_str(d)
    return vturb_post("/sessions/stats", {
        "player_id": player_id,
        "video_duration": duration,
        "start_date": s,
        "end_date": e,
    })


def engagement(player_id: str, duration: int, start: date, end: date) -> dict:
    s, _ = day_bounds_str(start)
    _, e = day_bounds_str(end)
    return vturb_post("/times/user_engagement", {
        "player_id": player_id,
        "video_duration": duration,
        "start_date": s,
        "end_date": e,
    })


def completion_rate(stats: dict) -> float:
    started = stats.get("total_started", 0) or 0
    finished = stats.get("total_finished", 0) or 0
    return round((finished / started * 100) if started else 0, 2)


def cta_click_rate(stats: dict) -> float:
    started = stats.get("total_started", 0) or 0
    clicked = stats.get("total_clicked", 0) or 0
    return round((clicked / started * 100) if started else 0, 2)


def retention_at_pct(grouped: list[dict], duration: int, pct: float, started: int) -> float:
    """Share of starters still watching at pct of video duration."""
    if not started:
        return 0
    target = duration * pct / 100
    viewers = 0
    for point in grouped:
        if point["timed"] >= target:
            viewers = point["total_users"]
            break
    else:
        viewers = grouped[-1]["total_users"] if grouped else 0
    return round((viewers / started * 100) if started else 0, 2)


# ---------- Row builders ----------

def row_raw(d: date, player_id: str, stats: dict, eng: dict, duration: int) -> list:
    started = stats.get("total_started", 0) or 0
    grouped = eng.get("grouped_timed", [])
    r25 = retention_at_pct(grouped, duration, 25, started)
    r50 = retention_at_pct(grouped, duration, 50, started)
    r75 = retention_at_pct(grouped, duration, 75, started)
    viewed_uniq = stats.get("total_viewed_session_uniq", 0)
    avg_watch = round(float(eng.get("average_watched_time", 0) or 0), 1)
    return [
        d.isoformat(),
        player_id,
        started,
        viewed_uniq,
        float(stats.get("play_rate", 0) or 0),
        avg_watch,
        completion_rate(stats),
        stats.get("total_clicked", 0),
        cta_click_rate(stats),
        r25,
        r50,
        r75,
        now_iso(),
    ]


def rows_retention_curve(d_snapshot: date, player_id: str, grouped: list[dict], duration: int) -> list[list]:
    """20 rows = 5% segments of the video."""
    if not grouped:
        return []
    max_users = max(p["total_users"] for p in grouped) or 1
    out = []
    for pct in range(0, 101, 5):
        target = duration * pct / 100
        # Find closest grouped point at or after target
        viewers = 0
        for point in grouped:
            if point["timed"] >= target:
                viewers = point["total_users"]
                break
        else:
            viewers = grouped[-1]["total_users"]
        retention_pct = round(viewers / max_users * 100, 2)
        out.append([
            d_snapshot.isoformat(),
            player_id,
            pct,
            viewers,
            retention_pct,
            now_iso(),
        ])
    return out


# ---------- Sheet I/O ----------

def append_rows(sheets, tab: str, rows: list[list], value_input: str = "USER_ENTERED") -> int:
    if not rows:
        return 0
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption=value_input,
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def existing_keys(sheets, tab: str, key_cols: list[int]) -> set[tuple]:
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab}!A2:Z"
    ).execute()
    out = set()
    for row in resp.get("values", []):
        out.add(tuple(row[c] if c < len(row) else "" for c in key_cols))
    return out


# ---------- Main ----------

def run(start: date, end: date, force: bool = False) -> None:
    sheets = get_sheets_service()

    players = list_all_players()
    players_by_id = {p["id"]: p for p in players}

    raw_existing = set() if force else existing_keys(sheets, "VTurb_Raw", [0, 1])
    raw_rows: list[list] = []
    curve_rows: list[list] = []

    for pid, label in RELEVANT_PLAYERS.items():
        if pid not in players_by_id:
            print(f"⚠️  player {pid} ({label}) not found in vTurb account")
            continue
        duration = players_by_id[pid].get("duration", 0) or 1
        print(f"🎬 {label} (duration {duration}s)")

        for d in daterange(start, end):
            if (d.isoformat(), pid) in raw_existing:
                continue
            try:
                stats = session_stats(pid, duration, d)
                eng = engagement(pid, duration, d, d)
                raw_rows.append(row_raw(d, pid, stats, eng, duration))
            except RuntimeError as err:
                print(f"   {d} error: {err}")
                continue

        # Snapshot retention curve for the full backfill period
        try:
            eng_all = engagement(pid, duration, start, end)
            curve_rows.extend(rows_retention_curve(end, pid, eng_all.get("grouped_timed", []), duration))
        except RuntimeError as err:
            print(f"   curve error: {err}")

    n1 = append_rows(sheets, "VTurb_Raw", raw_rows)
    n2 = append_rows(sheets, "VTurb_Retention_Curve", curve_rows)
    print(f"✅ VTurb_Raw +{n1} | Retention_Curve +{n2}")


if __name__ == "__main__":
    import argparse
    from dateutil.parser import parse as parse_date

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-04-09")
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    run(parse_date(args.start).date(), parse_date(args.end).date(), force=args.force)
