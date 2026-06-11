"""execute_decisions.py — Exécutant Meta (le SEUL pipeline qui écrit hors Supabase).

Scope STRICT (SPEC-M1-AGENTS §3) :
  decision_log status=approved AND decision_type=pause_ad AND outcome.executed != true
  → POST graph.facebook.com/{version}/{ad_id} {status: PAUSED}
  → merge outcome {executed, executed_at, meta_response} + executed_by += " · exécutant"

Jamais delete, jamais création, jamais budget, jamais une ad hors payload
d'une décision approved. Idempotent : re-run = no-op (outcome.executed=true filtré).
Échec API → 1 retry, puis outcome {executed:false, execution_error, manual_required:true}.

Usage:
  python -m pipelines.execute_decisions             # exécute les approved
  python -m pipelines.execute_decisions --dry-run   # liste sans rien toucher
  python -m pipelines.execute_decisions --probe     # vérifie le droit d'écriture Meta (no-op)

Env (loaded from .env.local):
  SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY, META_ACCESS_TOKEN, META_API_VERSION
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb
from pipelines.lib.meta_client import MetaClient, MetaError

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

PROBE_AD_ID = "120244689151840073"  # GIGI_VSL_VIDEO_STORY_80EUROS_RETARGETING


def meta_post(client: MetaClient, ad_id: str, fields: dict) -> dict:
    """POST sur un node ad — uniquement {status}, 1 retry. Pas dans meta_client (GET-only) exprès :
    ce script est le seul autorisé à écrire côté Meta."""
    assert set(fields) == {"status"}, "écriture limitée au champ status"
    url = f"{client.base}/{ad_id}"
    body = urllib.parse.urlencode({**fields, "access_token": client.token}).encode()
    last_err: Exception | None = None
    for attempt in range(2):  # 1 essai + 1 retry, jamais plus
        req = urllib.request.Request(url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            last_err = MetaError(f"Meta {e.code}: {detail}")
        except urllib.error.URLError as e:
            last_err = MetaError(f"Meta network: {e}")
        if attempt == 0:
            print(f"[executant] WARN POST {ad_id} failed, retry 1/1: {last_err}", file=sys.stderr)
    raise last_err  # type: ignore[misc]


def pending_decisions() -> list[dict]:
    rows = (
        sb().table("decision_log")
        .select("id, agent_name, status, executed_by, payload, outcome")
        .eq("status", "approved")
        .eq("decision_type", "pause_ad")
        .order("id")
        .execute()
        .data
    )
    # outcome->>executed IS DISTINCT FROM 'true' — filtré côté Python (null ou false passent)
    return [r for r in rows if not ((r.get("outcome") or {}).get("executed") is True)]


def mark(decision: dict, patch: dict, executed: bool) -> None:
    outcome = {**(decision.get("outcome") or {}), **patch}
    update: dict = {"outcome": outcome}
    if executed:
        prev = decision.get("executed_by")
        update["executed_by"] = f"{prev} · exécutant" if prev else "exécutant"
    sb().table("decision_log").update(update).eq("id", decision["id"]).execute()


def run_probe(client: MetaClient) -> int:
    """GET status de l'ad sonde + POST no-op (même statut) → prouve ads_management sans rien changer."""
    print(f"[executant] probe — ad {PROBE_AD_ID}")
    try:
        ad = client.get(PROBE_AD_ID, {"fields": "status,effective_status"})
    except MetaError as e:
        print(f"[executant] probe READ FAILED: {e}", file=sys.stderr)
        return 1
    print(f"[executant] read OK — status={ad.get('status')} effective_status={ad.get('effective_status')}")
    try:
        res = meta_post(client, PROBE_AD_ID, {"status": ad["status"]})  # no-op : statut identique
        print(f"[executant] write OK (no-op POST status={ad['status']}) — response={json.dumps(res)}")
        print("[executant] probe verdict: token PEUT écrire (ads_management OK)")
        return 0
    except MetaError as e:
        print(f"[executant] write FAILED — token ne peut PAS écrire (exécution manuelle requise): {e}", file=sys.stderr)
        return 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="liste les décisions à exécuter, ne touche à rien")
    p.add_argument("--probe", action="store_true", help="vérifie le droit d'écriture Meta (GET + POST no-op)")
    args = p.parse_args()

    client = MetaClient()
    if args.probe:
        return run_probe(client)

    todo = pending_decisions()
    if not todo:
        print("[executant] 0 décision approved à exécuter — rien à faire")
        return 0

    if args.dry_run:
        for d in todo:
            pl = d.get("payload") or {}
            print(f"[executant] DRY-RUN would pause ad {pl.get('ad_id')} ({pl.get('ad_name')}) — decision #{d['id']}")
        print(f"[executant] DRY-RUN: {len(todo)} pause(s) seraient exécutées")
        return 0

    failed = 0
    for d in todo:
        pl = d.get("payload") or {}
        ad_id = pl.get("ad_id")
        if not ad_id:
            print(f"[executant] WARN decision #{d['id']} sans ad_id dans le payload — skip", file=sys.stderr)
            mark(d, {"executed": False, "execution_error": "payload sans ad_id", "manual_required": True}, executed=False)
            failed += 1
            continue
        now = datetime.now(timezone.utc).isoformat()
        try:
            res = meta_post(client, str(ad_id), {"status": "PAUSED"})
            mark(d, {
                "executed": True,
                "executed_at": now,
                "meta_response": {"success": bool(res.get("success", res)), "ad_id": str(ad_id), "set_status": "PAUSED"},
            }, executed=True)
            print(f"[executant] PAUSED ad {ad_id} ({pl.get('ad_name')}) — decision #{d['id']}")
        except MetaError as e:
            mark(d, {"executed": False, "execution_error": str(e)[:500], "manual_required": True}, executed=False)
            print(f"[executant] FAILED ad {ad_id} — decision #{d['id']} → exécution manuelle requise: {e}", file=sys.stderr)
            failed += 1

    print(f"[executant] done — {len(todo) - failed} exécutée(s), {failed} échec(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
