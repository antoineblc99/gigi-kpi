"""agent_optimiseur.py — agent Optimiseur ads (hebdo, lundi 6h UTC) → decision_log pause_ad.

Propose-only : écrit des décisions `pause_ad` en status=proposed, n'agit JAMAIS sur Meta.
Pipeline : candidats (2 requêtes validées dans communicator-app/lib/signals.ts)
  → cooldown/dédup (aucune ad avec une décision pause_ad <14j, tout statut)
  → juge LLM séparé (Claude Sonnet, rubric pattern Kashef — défaut = ne rien proposer)
  → insert decision_log.

Candidats :
  A. Ad qui brûle : spend 30j > 300€ et 0 vente attribuée (COUNT DISTINCT lead_id via
     fact_contact.utm_content → fact_sale won). ⚠️ Follow non attribuable ad-level
     (KPI_REGISTRY §8) — le juge rejette ce motif sur une ad Follow.
  B. CTR decay : ad active (spend 3j > 0), imp3 >= 1000, CTR 3j < 60% du CTR 14j.

Usage:
  python -m pipelines.agent_optimiseur [--dry-run]

Env (loaded from .env.local + ~/.env) :
  SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY (fallback ~/.zshrc)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from pipelines.lib.db import sb

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(Path.home() / ".env")

AGENT_NAME = "optimiseur"
JUDGE_MODEL = "claude-sonnet-4-6"
COOLDOWN_DAYS = 14
MAX_JUDGE_CALLS = 10  # coût borné (spec : ≤30 appels API/jour, l'agent est hebdo)


def log(msg: str) -> None:
    print(f"[optimiseur] {msg}")


def anthropic_key() -> str | None:
    """ANTHROPIC_API_KEY depuis l'env (zshrc export / .env), fallback parse ~/.zshrc."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        m = re.search(r'^export ANTHROPIC_API_KEY=["\']?([^"\'\n]+)', zshrc.read_text(), re.M)
        if m:
            return m.group(1).strip()
    return None


def run_sql(query: str) -> list[dict]:
    """SQL read-only via la RPC execute_readonly_sql."""
    url = os.environ["SUPABASE_PROJECT_URL"].rstrip("/") + "/rest/v1/rpc/execute_readonly_sql"
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    resp = requests.post(
        url,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query.strip()},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"SQL error: {data['error']}")
    return data.get("rows", []) if isinstance(data, dict) else (data or [])


# ============================================================================
# Candidats — requêtes transposées de communicator-app/lib/signals.ts (validées)
# ============================================================================

def fetch_burning_ads() -> list[dict]:
    """A. spend 30j > 300€, 0 vente attribuée (COUNT DISTINCT lead_id)."""
    return run_sql("""
        WITH ad_spend AS (
          SELECT ad_id, sum(spend)::numeric AS spend30
          FROM fact_ad_daily
          WHERE date >= current_date - 30
          GROUP BY ad_id
          HAVING sum(spend) > 300
        ),
        ad_sales AS (
          SELECT c.utm_content AS ad_id, count(DISTINCT s.lead_id)::int AS won
          FROM fact_contact c
          JOIN fact_sale s ON s.lead_id = c.lead_id AND s.is_won = true
          WHERE c.utm_content IS NOT NULL
          GROUP BY c.utm_content
        )
        SELECT a.ad_id, round(a.spend30, 2) AS spend30,
               COALESCE(d.name, a.ad_id) AS ad_name,
               CASE
                 WHEN d.name ILIKE '%VSL%' THEN 'VSL'
                 WHEN d.name ILIKE '%Follow%' OR d.name ILIKE '%BROAD%' OR d.name ILIKE '%LAL%' THEN 'Follow'
                 ELSE 'unknown'
               END AS funnel,
               COALESCE(sa.won, 0)::int AS sales_attributed
        FROM ad_spend a
        LEFT JOIN ad_sales sa ON sa.ad_id = a.ad_id
        LEFT JOIN dim_ad d ON d.ad_id = a.ad_id
        WHERE COALESCE(sa.won, 0) = 0
        ORDER BY a.spend30 DESC
    """)


def fetch_ctr_decay() -> list[dict]:
    """B. ads actives (spend 3j > 0), imp3 >= 1000, CTR 3j < 60% du CTR 14j."""
    return run_sql("""
        WITH win AS (
          SELECT ad_id,
            sum(clicks) FILTER (WHERE date >= current_date - 3)::numeric AS clicks3,
            sum(impressions) FILTER (WHERE date >= current_date - 3)::numeric AS imp3,
            sum(spend) FILTER (WHERE date >= current_date - 3)::numeric AS spend3,
            sum(clicks)::numeric AS clicks14,
            sum(impressions)::numeric AS imp14
          FROM fact_ad_daily
          WHERE date >= current_date - 14
          GROUP BY ad_id
        ),
        spend30 AS (
          SELECT ad_id, sum(spend)::numeric AS spend30
          FROM fact_ad_daily
          WHERE date >= current_date - 30
          GROUP BY ad_id
        ),
        ad_sales AS (
          SELECT c.utm_content AS ad_id, count(DISTINCT s.lead_id)::int AS won
          FROM fact_contact c
          JOIN fact_sale s ON s.lead_id = c.lead_id AND s.is_won = true
          WHERE c.utm_content IS NOT NULL
          GROUP BY c.utm_content
        )
        SELECT w.ad_id, COALESCE(d.name, w.ad_id) AS ad_name,
               round(100.0 * w.clicks3 / w.imp3, 2) AS ctr3,
               round(100.0 * w.clicks14 / w.imp14, 2) AS ctr14,
               w.imp3::int AS imp3,
               round(COALESCE(s30.spend30, 0), 2) AS spend30,
               CASE
                 WHEN d.name ILIKE '%VSL%' THEN 'VSL'
                 WHEN d.name ILIKE '%Follow%' OR d.name ILIKE '%BROAD%' OR d.name ILIKE '%LAL%' THEN 'Follow'
                 ELSE 'unknown'
               END AS funnel,
               COALESCE(sa.won, 0)::int AS sales_attributed
        FROM win w
        LEFT JOIN dim_ad d ON d.ad_id = w.ad_id
        LEFT JOIN spend30 s30 ON s30.ad_id = w.ad_id
        LEFT JOIN ad_sales sa ON sa.ad_id = w.ad_id
        WHERE COALESCE(w.spend3, 0) > 0
          AND w.imp3 >= 1000
          AND w.imp14 > 0 AND w.clicks14 > 0
          AND (w.clicks3 / w.imp3) < 0.6 * (w.clicks14 / w.imp14)
        ORDER BY w.imp3 DESC
    """)


def fetch_cooldown_ad_ids() -> set[str]:
    """Ads avec une décision pause_ad <14j, TOUT statut — jamais re-proposer."""
    rows = run_sql(f"""
        SELECT DISTINCT payload->>'ad_id' AS ad_id
        FROM decision_log
        WHERE decision_type = 'pause_ad'
          AND created_at >= now() - interval '{COOLDOWN_DAYS} days'
          AND payload->>'ad_id' IS NOT NULL
    """)
    return {r["ad_id"] for r in rows}


def build_candidates() -> list[dict]:
    """Fusionne les 2 requêtes en candidats uniques par ad_id (motifs cumulés)."""
    today = date.today()
    window30 = {"from": (today - timedelta(days=30)).isoformat(), "to": today.isoformat(), "days": 30}
    candidates: dict[str, dict] = {}

    for r in fetch_burning_ads():
        candidates[r["ad_id"]] = {
            "ad_id": r["ad_id"],
            "ad_name": r["ad_name"],
            "funnel": r["funnel"],
            "reasons": ["no_attributed_sales"],
            "spend_eur": float(r["spend30"]),
            "window": window30,
            "sales_attributed": int(r["sales_attributed"]),
            "spend30": float(r["spend30"]),
        }

    for r in fetch_ctr_decay():
        c = candidates.get(r["ad_id"])
        if c:
            c["reasons"].append("ctr_decay")
            c["ctr"] = {"ctr3_pct": float(r["ctr3"]), "ctr14_pct": float(r["ctr14"]), "imp3": int(r["imp3"])}
        else:
            candidates[r["ad_id"]] = {
                "ad_id": r["ad_id"],
                "ad_name": r["ad_name"],
                "funnel": r["funnel"],
                "reasons": ["ctr_decay"],
                "spend_eur": float(r["spend30"]),
                "window": window30,
                "sales_attributed": int(r["sales_attributed"]),
                "spend30": float(r["spend30"]),
                "ctr": {"ctr3_pct": float(r["ctr3"]), "ctr14_pct": float(r["ctr14"]), "imp3": int(r["imp3"])},
            }
    return list(candidates.values())


# ============================================================================
# Juge LLM (pattern Kashef) — défaut absolu = ne rien proposer
# ============================================================================

JUDGE_SYSTEM = """Tu es le juge des propositions de l'agent Optimiseur ads (Gigi Academy, funnel VSL + funnel Follow Instagram).
L'agent veut proposer de mettre en PAUSE une ad Meta. Toi seul décides si la proposition part en validation humaine.

Rubric — la proposition ne passe QUE si TOUS les critères tiennent :
1. Données suffisantes : spend significatif sur la fenêtre, et pour un CTR decay au moins 1000 impressions sur 3j.
2. Pas de vente récente qui disculpe : si sales_attributed > 0, le motif "no_attributed_sales" tombe — rejette sauf si le CTR decay seul justifie largement.
3. Attribution Follow exclue : le funnel Follow (clic ad → profil IG → DM) ne porte PAS l'utm_content — l'attribution des ventes au niveau de l'ad y est IMPOSSIBLE. Si funnel = "Follow" ou "unknown" et que le motif repose sur l'absence de ventes attribuées, REJETTE. Un CTR decay reste un motif valide pour une ad Follow (le CTR ne dépend pas de l'attribution).
4. Cooldown respecté : le champ cooldown_ok t'est fourni (déjà filtré en amont) ; s'il est false, rejette.

En cas de doute : REJETTE. Le défaut est de ne rien proposer.

Réponds UNIQUEMENT avec un JSON strict, sans markdown ni texte autour :
{"verdict": "propose" | "reject", "reasoning": "1-3 phrases en français"}"""


def judge_candidate(client, candidate: dict) -> tuple[str, str]:
    """Retourne (verdict, reasoning). Toute erreur API / parse → ('reject', ...) : défaut = rien."""
    payload = {k: v for k, v in candidate.items() if k != "spend30"}
    payload["cooldown_ok"] = True  # filtré en amont (aucune décision pause_ad <14j sur cette ad)
    user_msg = f"Candidat à juger :\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    last_err = "unknown"
    for attempt in range(2):  # 1 retry
        try:
            resp = client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=400,
                system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
                timeout=60.0,
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
            data = json.loads(text)
            verdict = data.get("verdict")
            reasoning = str(data.get("reasoning", "")).strip()
            if verdict in ("propose", "reject") and reasoning:
                return verdict, reasoning
            last_err = f"réponse invalide: {text[:120]}"
        except Exception as e:  # API down, timeout, JSON cassé → défaut = reject
            last_err = str(e)[:150]
        log(f"WARN judge attempt {attempt + 1} failed for {candidate['ad_id']}: {last_err}")
    return "reject", f"juge indisponible ou réponse non parsable ({last_err}) — défaut = ne rien proposer"


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="détecte + juge mais n'écrit rien")
    args = p.parse_args()

    candidates = build_candidates()
    log(f"{len(candidates)} candidat(s) détecté(s) : "
        + (", ".join(f"{c['ad_name']} [{'+'.join(c['reasons'])}]" for c in candidates) or "aucun"))
    if not candidates:
        log("rien à proposer")
        return 0

    # Cooldown / dédup — critère n°1 : jamais 2 propositions sur la même ad en <14j (tout statut)
    cooldown = fetch_cooldown_ad_ids()
    kept, skipped = [], []
    for c in candidates:
        (skipped if c["ad_id"] in cooldown else kept).append(c)
    for c in skipped:
        log(f"SKIP cooldown <{COOLDOWN_DAYS}j : {c['ad_name']} ({c['ad_id']})")
    if not kept:
        log("tous les candidats sont en cooldown — rien à proposer")
        return 0
    if len(kept) > MAX_JUDGE_CALLS:
        log(f"WARN {len(kept)} candidats > {MAX_JUDGE_CALLS} max — tronqué (coût API borné)")
        kept = kept[:MAX_JUDGE_CALLS]

    # Juge — sans clé API, défaut absolu : ne rien proposer
    key = anthropic_key()
    if not key:
        log("ERROR ANTHROPIC_API_KEY introuvable (env, ~/.env, ~/.zshrc) — défaut = ne rien proposer")
        return 1
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    decisions = []
    for c in kept:
        verdict, reasoning = judge_candidate(client, c)
        log(f"JUGE {verdict.upper()} {c['ad_name']} — {reasoning}")
        if verdict != "propose":
            continue
        reasons_txt = " + ".join(c["reasons"])
        payload = {
            "ad_id": c["ad_id"],
            "ad_name": c["ad_name"],
            "funnel": c["funnel"],
            "reasons": c["reasons"],
            "summary": f"Couper l'ad {c['ad_name']} — {c['spend_eur']:.0f}€ sur 30j, "
                       f"{c['sales_attributed']} vente(s) attribuée(s) ({reasons_txt})",
            "window": c["window"],
            "spend_eur": c["spend_eur"],
            "sales_attributed": c["sales_attributed"],
            "projection_eur_mois": round(c["spend30"]),
            "judge_verdict": verdict,
            "judge_reasoning": reasoning,
            "proposed_action": "pause_ad",
            "source": "fact_ad_daily + dim_ad + fact_contact.utm_content → fact_sale won (COUNT DISTINCT lead_id)",
        }
        if "ctr" in c:
            payload["ctr"] = c["ctr"]
        decisions.append({"agent_name": AGENT_NAME, "decision_type": "pause_ad", "payload": payload})

    log(f"{len(decisions)} proposition(s) validée(s) par le juge sur {len(kept)} jugée(s)")
    if args.dry_run:
        for d in decisions:
            log(f"DRY-RUN would write: {json.dumps(d['payload'], ensure_ascii=False)}")
        log("dry-run — rien écrit")
        return 0

    if decisions:
        sb().table("decision_log").insert(decisions).execute()
        for d in decisions:
            log(f"WROTE pause_ad proposed: {d['payload']['ad_name']} ({d['payload']['ad_id']})")
    else:
        log("rien à proposer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
