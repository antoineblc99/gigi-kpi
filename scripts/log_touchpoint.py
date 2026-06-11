"""log_touchpoint.py — logger un contact avec Léa (table client_touchpoints).

Usage (une ligne, depuis Hermes ou une session) :
  python3 scripts/log_touchpoint.py --channel call --by mahdy --note "point hebdo"

Args:
  --channel : call / whatsapp / rapport / autre
  --by      : qui a eu le contact (antoine, mahdy, ...)
  --note    : résumé court
  --when    : optionnel, ISO timestamp (défaut = now)

Env (.env.local du repo, fallback ~/.env):
  SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv absent du python système — parser stdlib
    def load_dotenv(path):
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(Path.home() / ".env")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", required=True, choices=["call", "whatsapp", "rapport", "autre"])
    p.add_argument("--by", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--when", default=None, help="ISO timestamp (défaut: now)")
    args = p.parse_args()

    url = os.environ["SUPABASE_PROJECT_URL"].rstrip("/") + "/rest/v1/client_touchpoints"
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    body = {"channel": args.channel, "by_who": args.by, "note": args.note}
    if args.when:
        body["touched_at"] = args.when

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[touchpoint] ERROR {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return 1

    r = rows[0] if rows else {}
    print(f"[touchpoint] #{r.get('id')} {r.get('channel')} par {r.get('by_who')} — {r.get('note')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
