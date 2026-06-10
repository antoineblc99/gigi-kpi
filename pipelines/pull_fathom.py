"""pull_fathom.py — transcripts des calls closing (Fathom share links) → fact_call_transcript.

Les closeuses postent leurs recordings Fathom dans l'EOD Typeform — les share links
atterrissent dans fact_eod_closeuse.fathom_urls. Le MCP/API Fathom du compte Scale.IA
n'a PAS accès aux recordings du compte d'Anaïs : on passe par la page share publique,
qui expose un endpoint copy_transcript authentifié par le share token lui-même.

Flow par URL :
  1. GET la page share → JSON inline `data-page` (call id, title, host, started_at, durée)
  2. GET /calls/{id}/copy_transcript?token={share_token} → plain_text (speakers + timestamps)
  3. upsert fact_call_transcript (idempotent sur share_token, skip si déjà pullé)

Usage:
  python -m pipelines.pull_fathom [--days 90] [--force]

Env (loaded from .env.local):
  SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb, upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125 Safari/537.36"
DATA_PAGE_RE = re.compile(r'data-page="([^"]+)"')


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_share_meta(share_url: str) -> dict | None:
    """Parse le JSON inline data-page de la page share → metadata du call."""
    try:
        page = _get(share_url).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"[fathom] WARN share page HTTP {e.code}: {share_url}", file=sys.stderr)
        return None
    m = DATA_PAGE_RE.search(page)
    if not m:
        print(f"[fathom] WARN no data-page found: {share_url}", file=sys.stderr)
        return None
    data = json.loads(html_mod.unescape(m.group(1)))
    props = data.get("props") or {}
    call = props.get("call") or {}
    if not call.get("id"):
        return None
    return {
        "fathom_call_id": call["id"],
        "title": call.get("title"),
        "host_email": ((call.get("host") or {}).get("email")),
        "started_at": call.get("started_at"),
        "duration_minutes": call.get("duration_minutes"),
        "copy_transcript_url": props.get("copyTranscriptUrl"),
    }


def fetch_transcript(copy_url: str) -> str | None:
    try:
        data = json.loads(_get(copy_url).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        print(f"[fathom] WARN transcript HTTP {e.code}: {copy_url}", file=sys.stderr)
        return None
    return data.get("plain_text") or None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90, help="fenêtre EOD à scanner")
    p.add_argument("--force", action="store_true", help="re-pull même si déjà en base")
    args = p.parse_args()

    since = (date.today() - timedelta(days=args.days)).isoformat()
    eod = (
        sb().table("fact_eod_closeuse")
        .select("submit_date, closer_name, fathom_urls")
        .gte("submit_date", since)
        .not_.is_("fathom_urls", "null")
        .execute()
        .data
    )

    # share_token → (url, closer, submit_date) ; un même call peut apparaître 2x, on garde le 1er
    targets: dict[str, dict] = {}
    for row in eod:
        for url in row.get("fathom_urls") or []:
            m = re.search(r"/share/([A-Za-z0-9_-]+)", url or "")
            if not m:
                continue
            targets.setdefault(m.group(1), {
                "share_url": url.strip(),
                "closer_name": row.get("closer_name"),
                "eod_submit_date": row.get("submit_date"),
            })

    if not targets:
        print("[fathom] no share URLs in EOD window")
        return 0

    existing: set[str] = set()
    if not args.force:
        got = sb().table("fact_call_transcript").select("share_token").execute().data
        existing = {r["share_token"] for r in got}

    todo = {t: v for t, v in targets.items() if t not in existing}
    print(f"[fathom] {len(targets)} share links in EOD ({args.days}d) · {len(todo)} to pull")

    rows, failed = [], 0
    for token, meta in todo.items():
        share_meta = fetch_share_meta(meta["share_url"])
        if not share_meta or not share_meta.get("copy_transcript_url"):
            failed += 1
            continue
        transcript = fetch_transcript(share_meta.pop("copy_transcript_url"))
        if not transcript:
            failed += 1
            continue
        rows.append({
            "share_token": token,
            "transcript": transcript,
            **{k: v for k, v in meta.items()},
            **share_meta,
        })
        print(f"[fathom] ok {share_meta['title']} ({share_meta['duration_minutes']}min) — {len(transcript)} chars")
        time.sleep(1)  # politesse — pages share publiques

    n = upsert("fact_call_transcript", rows, on_conflict="share_token")
    print(f"[fathom] upserted {n} transcripts · {failed} failed · {len(existing)} already in base")
    return 0 if failed == 0 else (0 if rows else 1)


if __name__ == "__main__":
    raise SystemExit(main())
