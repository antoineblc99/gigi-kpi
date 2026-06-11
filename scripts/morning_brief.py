"""morning_brief.py — brief du matin WhatsApp (7h30 Paris, cron Hermes local).

Compose un brief ≤12 lignes depuis le RPC read-only Supabase :
  badge santé · hier (EOD : calls, ventes, cash) · signaux simples (show rate 7j,
  leads chauds) · décisions en attente ("réponds : valide N", N = id decision_log) ·
  exécutions de la veille (outcome.executed_at).
Journée calme → 3 lignes. Aucune écriture en base, aucun appel LLM.

Usage:
  python3 scripts/morning_brief.py [--send] [--prefix "🌙 test nocturne —"]

  --send : pipe le brief vers `hermes send -t whatsapp` (home channel).

Env (.env.local du repo, fallback ~/.env):
  SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(Path.home() / ".env")

PARIS = ZoneInfo("Europe/Paris")

# Copie exacte de communicator-app/lib/signals.ts (lignes EOD sentinel = test Typeform)
EOD_SENTINEL_FILTER = """NOT (calls_planifies > 0 AND calls_planifies = calls_recus
  AND calls_planifies = ventes_setting AND calls_planifies = ventes_vsl
  AND calls_planifies::numeric = cash_contracte)"""


def q(query: str) -> list[dict]:
    """POST le RPC read-only execute_readonly_sql → rows."""
    url = os.environ["SUPABASE_PROJECT_URL"].rstrip("/") + "/rest/v1/rpc/execute_readonly_sql"
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        url,
        data=json.dumps({"query": query.strip()}).encode(),
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"RPC: {data['error']}")
    return data.get("rows") or []


# ----------------------------------------------------------------------------
# Blocs du brief
# ----------------------------------------------------------------------------

def eod_hier() -> str | None:
    """Hier (EOD closeuses, filtre sentinel) : calls, ventes, cash collecté."""
    rows = q(f"""
        SELECT COALESCE(sum(calls_recus), 0)::int AS recus,
               COALESCE(sum(calls_planifies), 0)::int AS planifies,
               COALESCE(sum(ventes_setting + ventes_vsl), 0)::int AS ventes,
               COALESCE(sum(cash_collecte), 0)::numeric AS cash
        FROM fact_eod_closeuse
        WHERE submit_date = (now() AT TIME ZONE 'Europe/Paris')::date - 1
          AND {EOD_SENTINEL_FILTER}
    """)
    r = rows[0] if rows else {}
    planifies = int(r.get("planifies") or 0)
    if planifies == 0 and int(r.get("ventes") or 0) == 0 and float(r.get("cash") or 0) == 0:
        return "Hier : pas d'EOD closeuse remontée"
    return (
        f"Hier : {int(r['recus'])}/{planifies} calls reçus · "
        f"{int(r['ventes'])} vente(s) · {float(r['cash']):.0f}€ collectés"
    )


def signaux() -> tuple[list[str], bool]:
    """Signaux simples (mêmes seuils que signals.ts) → (lignes, any_red)."""
    lines: list[str] = []
    any_red = False

    rows = q(f"""
        SELECT COALESCE(sum(calls_recus), 0)::int AS recus,
               COALESCE(sum(calls_planifies), 0)::int AS planifies
        FROM fact_eod_closeuse
        WHERE submit_date >= current_date - interval '7 days'
          AND {EOD_SENTINEL_FILTER}
    """)
    recus = int(rows[0].get("recus") or 0) if rows else 0
    planifies = int(rows[0].get("planifies") or 0) if rows else 0
    if planifies > 0:
        rate = recus / planifies * 100
        if rate < 60:
            any_red = any_red or rate < 50
            lines.append(f"{'🔴' if rate < 50 else '🟡'} Show rate 7j : {rate:.0f}% ({recus}/{planifies}) — cible 70-85%")

    rows = q("""
        SELECT count(*)::int AS n FROM (
          SELECT s.lead_id
          FROM fact_survey s
          WHERE s.submitted_at >= now() - interval '14 days'
            AND s.submitted_at < now() - interval '48 hours'
            AND (s.quand_demarrer ILIKE '%Tout de suite%' OR s.quand_demarrer ILIKE '%30 prochains%')
            AND s.budget ILIKE 'Oui%'
            AND NOT EXISTS (
              SELECT 1 FROM fact_call c
              WHERE c.lead_id = s.lead_id AND c.status != 'cancelled'
            )
          GROUP BY s.lead_id
        ) t
    """)
    n = int(rows[0].get("n") or 0) if rows else 0
    if n > 10:
        any_red = any_red or n > 25
        lines.append(f"{'🔴' if n > 25 else '🟡'} {n} leads chauds non bookés (>48h, fenêtre 14j)")

    return lines, any_red


def decisions_en_attente() -> list[dict]:
    """Décisions proposed des 14 derniers jours (les anomalies de mai restent hors brief)."""
    return q("""
        SELECT id, agent_name, decision_type, payload
        FROM decision_log
        WHERE status = 'proposed'
          AND created_at >= now() - interval '14 days'
        ORDER BY id
    """)


def executions_manuelles() -> int:
    """Décisions approved que l'Exécutant n'a pas pu exécuter (spec §3 : le brief le signale)."""
    rows = q("""
        SELECT count(*)::int AS n
        FROM decision_log
        WHERE status = 'approved'
          AND decision_type = 'pause_ad'
          AND outcome->>'manual_required' = 'true'
          AND COALESCE(outcome->>'executed', 'false') <> 'true'
    """)
    return int(rows[0].get("n") or 0) if rows else 0


def executions_veille() -> list[dict]:
    """Décisions exécutées dans les dernières 24h (outcome.executed_at)."""
    return q("""
        SELECT id, decision_type, payload, outcome
        FROM decision_log
        WHERE outcome->>'executed' = 'true'
          AND (outcome->>'executed_at')::timestamptz >= now() - interval '24 hours'
        ORDER BY id
    """)


def resume_decision(d: dict) -> str:
    p = d.get("payload") or {}
    summary = str(p.get("summary") or "").strip()
    # 1 ligne WhatsApp lisible : les summaries longs (ex: relance_batch) sont remplacés
    if summary and len(summary) <= 120:
        return summary
    if d["decision_type"] == "relance_batch":
        leads = p.get("leads") or []
        return f"Relancer {len(leads)} leads chauds (messages prêts dans le cockpit)"
    if d["decision_type"] == "pause_ad":
        return f"Couper l'ad {p.get('ad_name', p.get('ad_id', '?'))}"
    return (summary[:117] + "…") if summary else d["decision_type"]


# ----------------------------------------------------------------------------
# Composition (≤12 lignes ; journée calme = 3 lignes)
# ----------------------------------------------------------------------------

def compose() -> str:
    date_str = datetime.now(PARIS).strftime("%d/%m")
    hier = eod_hier()
    sig_lines, any_red = signaux()
    pending = decisions_en_attente()
    executed = executions_veille()
    n_manual = executions_manuelles()

    badge = "🔴" if any_red else ("🟡" if sig_lines or pending or n_manual else "🟢")
    lines = [f"{badge} Gigi — brief du {date_str}", hier]

    lines.extend(sig_lines)
    if n_manual:
        lines.append(f"⚠️ {n_manual} pause(s) ad à exécuter MANUELLEMENT (token Meta KO) — voir cockpit")

    if pending:
        lines.append(f"À valider ({len(pending)}) :")
        for d in pending[:4]:
            lines.append(f"{d['id']}. {resume_decision(d)} [{d['agent_name']}]")
        if len(pending) > 4:
            lines.append(f"… +{len(pending) - 4} autres (cockpit)")
        lines.append("→ Réponds : valide N")

    if executed:
        names = " · ".join(
            f"{e['decision_type']} {((e.get('payload') or {}).get('ad_name') or '#' + str(e['id']))}"
            for e in executed[:3]
        )
        lines.append(f"✅ Exécuté hier : {names}")

    if not sig_lines and not pending and not executed and not n_manual:
        lines.append("RAS — rien à signaler, rien à valider.")

    return "\n".join(lines[:12])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--send", action="store_true", help="envoie sur WhatsApp via hermes send")
    p.add_argument("--prefix", default="", help="préfixe ajouté en tête (ex: test)")
    args = p.parse_args()

    try:
        brief = compose()
    except Exception as e:
        print(f"[brief] ERROR compose: {e}", file=sys.stderr)
        return 1

    if args.prefix:
        brief = f"{args.prefix}\n{brief}"

    print(brief)

    if args.send:
        hermes = shutil.which("hermes") or str(Path.home() / ".local/bin/hermes")
        try:
            r = subprocess.run(
                [hermes, "send", "-t", "whatsapp"],
                input=brief, capture_output=True, text=True, timeout=60,
            )
        except FileNotFoundError:
            print("[brief] ERROR hermes introuvable", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"[brief] ERROR hermes send: {r.stderr.strip()}", file=sys.stderr)
            return 1
        print("[brief] sent to whatsapp", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
