"""agent_relanceur.py — leads chauds non bookés → UNE décision relance_batch/jour (propose-only).

Même SQL que le skill /relances : survey qualifié <30j (quand_demarrer "Tout de suite"
ou "30 prochains jours" + budget "Oui..."), aucun fact_call non-cancelled sur le lead_id,
et >48h depuis le survey (on laisse au lead le temps de booker seul).

Garde-fous (SPEC-M1-AGENTS section 1) :
  - Dédup 14j : un lead déjà présent dans un relance_batch des 14 derniers jours
    (proposed/approved/rejected confondus) n'est jamais re-proposé.
  - 1 décision groupée max/jour : skip si un relance_batch existe déjà aujourd'hui (UTC).
  - Top 12 leads les plus récents (submitted_at desc). Propose-only : V1 = envoi
    manuel par Anaïs depuis le payload, jamais d'envoi automatique ici.
  - Messages : Claude Haiku (voix Léa, référence à LEUR réponse survey, CTA
    {LIEN_BOOKING}) ; fallback template déterministe si API indispo.

Usage:
  python -m pipelines.agent_relanceur [--dry-run] [--limit 12]

Env (.env.local + ~/.env): SUPABASE_PROJECT_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(Path.home() / ".env")

AGENT_NAME = "relanceur"
DECISION_TYPE = "relance_batch"
DEDUP_DAYS = 14
BATCH_SIZE = 12
HAIKU_MODEL = "claude-haiku-4-5-20251001"
BOOKING_PLACEHOLDER = "{LIEN_BOOKING}"

# SQL validé du skill /relances (KPI_REGISTRY : lead chaud + COUNT DISTINCT lead_id
# via DISTINCT ON, jointure survey↔call sur lead_id) + filtre >48h de la spec.
LEADS_SQL = """
SELECT DISTINCT ON (s.lead_id)
  s.lead_id,
  c.first_name,
  c.email,
  c.phone,
  s.statut_onglerie,
  s.quand_demarrer,
  s.budget,
  s.motivation,
  s.submitted_at,
  ROUND(EXTRACT(EPOCH FROM (now() - s.submitted_at)) / 86400) AS anciennete_jours
FROM fact_survey s
JOIN fact_contact c ON c.lead_id = s.lead_id
WHERE s.submitted_at >= now() - interval $$30 days$$
  AND s.submitted_at <= now() - interval $$48 hours$$
  AND (s.quand_demarrer ILIKE $$%Tout de suite%$$ OR s.quand_demarrer ILIKE $$%30 prochains%$$)
  AND s.budget ILIKE $$Oui%$$
  AND NOT EXISTS (
    SELECT 1 FROM fact_call k
    WHERE k.lead_id = s.lead_id
      AND k.status <> $$cancelled$$
  )
ORDER BY s.lead_id, s.submitted_at DESC
"""

SYSTEM_PROMPT = """Tu écris un SMS de relance au nom de Léa, fondatrice de la Gigi Academy (formation onglerie).
La fille a regardé la vidéo de Léa et répondu au questionnaire (réponses fournies), mais n'a jamais réservé son appel.

Règles STRICTES :
- 2 à 3 phrases courtes maximum, format SMS, ton oral.
- Tutoiement immédiat. Ouverture "Coucou [prénom]" ou direct dans le vif — jamais "Bonjour".
- Cite UN élément concret de SA réponse au questionnaire (quand elle veut démarrer, sa situation onglerie ou sa motivation) — c'est ce qui montre que c'est pas un message automatique.
- Voix de Léa : copine experte, grande sœur passée par là. Transitions "alors", "du coup". Rassurance ("t'inquiète pas"). Le mot "passion" lui va bien ("vivre de ta passion").
- Zéro jargon : jamais "funnel", "leads", "call" (dire "appel"), "business", "mindset", "opportunité".
- Frame sélection, pas supplication : Léa préfère accompagner les filles motivées, elle ne supplie pas, elle ne brade pas.
- Termine EXACTEMENT par : clique juste ici pour choisir ton créneau : {LIEN_BOOKING}
  (garde le placeholder {LIEN_BOOKING} tel quel, il sera remplacé à l'envoi).
- 1 emoji maximum. Pas de vulgarité, pas d'ironie, pas de pression artificielle.

Réponds UNIQUEMENT avec le texte du SMS, rien d'autre."""


def anthropic_key() -> str | None:
    """ANTHROPIC_API_KEY : env (chargé depuis .env.local / ~/.env) puis export ~/.zshrc."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        m = re.search(r'^export ANTHROPIC_API_KEY=["\']?([^"\'\n]+)', zshrc.read_text(), re.M)
        if m:
            return m.group(1).strip()
    return None


def run_readonly_sql(query: str) -> list[dict]:
    # le RPC exige que la query COMMENCE par SELECT/WITH → strip obligatoire
    res = sb().rpc("execute_readonly_sql", {"query": query.strip()}).execute()
    data = res.data
    if isinstance(data, dict):
        if data.get("error"):
            raise RuntimeError(f"execute_readonly_sql: {data['error']}")
        return data.get("rows") or []
    return data or []


def batch_exists_today() -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    rows = (
        sb().table("decision_log")
        .select("id")
        .eq("decision_type", DECISION_TYPE)
        .gte("created_at", today)
        .execute()
        .data
    )
    return bool(rows)


def already_proposed_lead_ids() -> set[str]:
    """lead_ids présents dans un relance_batch des 14 derniers jours, tous statuts."""
    since = (datetime.now(timezone.utc) - timedelta(days=DEDUP_DAYS)).isoformat()
    rows = (
        sb().table("decision_log")
        .select("payload")
        .eq("decision_type", DECISION_TYPE)
        .gte("created_at", since)
        .execute()
        .data
    )
    ids: set[str] = set()
    for r in rows:
        for lead in ((r.get("payload") or {}).get("leads") or []):
            if lead.get("lead_id"):
                ids.add(str(lead["lead_id"]))
    return ids


def haiku_message(key: str, lead: dict) -> str | None:
    """1 SMS via Claude Haiku. Timeout 60s, 1 retry. None si échec → fallback."""
    body = {
        "model": HAIKU_MODEL,
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": json.dumps({
                "prenom": lead.get("first_name"),
                "anciennete_jours": lead.get("anciennete_jours"),
                "reponses_survey": {
                    "quand_demarrer": lead.get("quand_demarrer"),
                    "statut_onglerie": lead.get("statut_onglerie"),
                    "motivation": lead.get("motivation"),
                },
            }, ensure_ascii=False),
        }],
    }
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body).encode(),
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            text = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ).strip()
            # garde-fous format : placeholder présent + longueur SMS raisonnable
            if text and BOOKING_PLACEHOLDER in text and len(text) <= 600:
                return text
            print(f"[relanceur] WARN haiku output hors format (lead {lead.get('lead_id')}), fallback", file=sys.stderr)
            return None
        except Exception as e:  # HTTP, timeout, JSON — retry une fois puis fallback
            print(f"[relanceur] WARN haiku tentative {attempt}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


def fallback_message(lead: dict) -> str:
    prenom = ((lead.get("first_name") or "").strip().split() or ["toi"])[0].capitalize()
    quand = (lead.get("quand_demarrer") or "").lower()
    if "tout de suite" in quand:
        ref = "tu me disais que tu voulais démarrer tout de suite"
    elif "30" in quand:
        ref = "tu me disais que tu voulais démarrer dans les 30 prochains jours"
    else:
        ref = "tu me disais que tu voulais vivre de ta passion"
    return (
        f"Coucou {prenom} ! Alors, {ref} et du coup je voulais prendre de tes nouvelles, "
        "parce que t'as toujours pas réservé ton appel. T'inquiète pas, ta place est encore là — "
        f"clique juste ici pour choisir ton créneau : {BOOKING_PLACEHOLDER}"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="print la décision sans l'écrire")
    p.add_argument("--limit", type=int, default=BATCH_SIZE, help="nb max de leads dans le batch")
    args = p.parse_args()

    # 1 décision groupée max/jour (idempotence du run réel)
    if batch_exists_today():
        if args.dry_run:
            print("[relanceur] NOTE: un relance_batch existe déjà aujourd'hui — un run réel skiperait. Dry-run continue.")
        else:
            print("[relanceur] relance_batch déjà proposé aujourd'hui — skip")
            return 0

    leads = run_readonly_sql(LEADS_SQL)
    leads.sort(key=lambda r: r.get("submitted_at") or "", reverse=True)
    print(f"[relanceur] {len(leads)} leads chauds non bookés (30j, >48h)")

    seen = already_proposed_lead_ids()
    fresh = [l for l in leads if str(l.get("lead_id")) not in seen]
    n_dedup = len(leads) - len(fresh)
    print(f"[relanceur] dédup 14j: {n_dedup} déjà proposés · {len(fresh)} candidats")

    batch = fresh[: args.limit]
    if not batch:
        print("[relanceur] rien à proposer aujourd'hui")
        return 0

    key = anthropic_key()
    if not key:
        print("[relanceur] WARN ANTHROPIC_API_KEY introuvable — fallback template pour tous les messages", file=sys.stderr)

    payload_leads = []
    n_fallback = 0
    for lead in batch:
        msg = haiku_message(key, lead) if key else None
        if not msg:
            msg = fallback_message(lead)
            n_fallback += 1
        payload_leads.append({
            "lead_id": lead.get("lead_id"),
            "prenom": lead.get("first_name"),
            "email": lead.get("email"),
            "phone": lead.get("phone"),
            "anciennete_jours": int(lead.get("anciennete_jours") or 0),
            "reponses_survey": {
                "quand_demarrer": lead.get("quand_demarrer"),
                "statut_onglerie": lead.get("statut_onglerie"),
                "budget": lead.get("budget"),
                "motivation": lead.get("motivation"),
            },
            "message": msg,
        })

    today = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "title": f"Relance leads chauds — {today} ({len(payload_leads)} leads)",
        "summary": (
            f"{len(payload_leads)} leads chauds (survey qualifié <30j, aucun appel booké, >48h) à relancer. "
            f"{len(leads)} détectés au total, {n_dedup} exclus (déjà proposés <14j). "
            f"Messages voix Léa ({len(payload_leads) - n_fallback} Haiku, {n_fallback} template). "
            "Envoi manuel V1 : remplacer {LIEN_BOOKING} par le lien du calendrier VSL GHL avant envoi."
        ),
        "leads": payload_leads,
        "canal": "sms/whatsapp manuel V1",
    }

    if args.dry_run:
        print("[relanceur] DRY-RUN — décision non écrite:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    res = sb().table("decision_log").insert({
        "agent_name": AGENT_NAME,
        "decision_type": DECISION_TYPE,
        "payload": payload,
        "status": "proposed",
    }).execute()
    decision_id = (res.data or [{}])[0].get("id")
    print(f"[relanceur] décision #{decision_id} proposée — {len(payload_leads)} leads, statut proposed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
