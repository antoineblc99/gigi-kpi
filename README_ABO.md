# Gigi Data OS — Augmented Business Operator (Phase 1)

Pilote Scale.IA pour Gigi Academy. Premier déploiement de l'archi ABO :
data brute centralisée → agents IA flexibles → décisions tracées → patterns
cross-clients. Pas de dashboard, pas de Sheet d'analyse — la conversation
(Claude Code, Slack) est l'interface.

## Vision en 1 page

```
┌────────────────────────────────────────────────────────────────┐
│ 7. GOAL LAYER       Objectifs business explicites              │
│ 6. META-AGENT       Auto-amélioration, propose de nouveaux agents│
│ 5. AGENTS           Observer · Analyste · Stratège · Exécutant │
│                     · Communicateur — personnalités distinctes │
│ 4. PATTERN LIBRARY  Cross-client, anonymisé (effet réseau)     │
│ 3. SIMULATION       Monte-Carlo P10/P50/P90 avant décision     │
│ 2. ACTION LAYER     Meta API write, GHL, Slack — 1-clic valid. │
│ 1. DATA LAYER       Supabase, lead-id universel, webhooks      │
└────────────────────────────────────────────────────────────────┘
```

## État actuel — Phase 1 (Data foundation)

- [x] Projet Supabase `gigi-data-os` (`awfrzczcqemzwkjhlhfx`, eu-west-3)
- [x] Schéma SQL appliqué : 6 dim + 8 fact + 3 infra agents (RLS ON)
- [x] Lib pipelines : `lib/leadid.py`, `lib/supabase_client.py`, `lib/db.py`,
      `lib/meta_client.py`, `lib/ghl_client.py`
- [x] `.mcp.json` projet (Supabase MCP scope projet)
- [ ] Pipelines actifs : Meta + GHL + Tally + Stripe + vTurb
- [ ] Lead-id universel propagé end-to-end
- [ ] Critère succès Phase 1 : zéro export CSV sur 7 jours

## Schéma — 17 tables

**Dimensions** (6) — `dim_lead`, `dim_campaign`, `dim_adset`, `dim_ad`,
`dim_creative`, `dim_closer`.

**Faits** (8) — `fact_ad_daily`, `fact_survey`, `fact_contact`, `fact_call`,
`fact_sale`, `fact_payment`, `fact_setter_dm`, `fact_vsl_view`.

**Infra agents** (3) :
- `agent_memory` — souvenirs persistants (clé/valeur JSONB par agent).
- `decision_log` — audit trail complet (proposed → approved → executed → rolled_back).
- `pattern_signals` — ratios/deltas anonymisés cross-clients. Pas de PII,
  pas de chiffres absolus, uniquement deltas et metadata anonymisée.

Source : `schemas/supabase_init.sql`.

## Lead-id universel

```
lead_id = sha256(lower(email) || e164(phone))
```

Implémentation : `pipelines/lib/leadid.py`. Tous les `fact_*` et `dim_lead`
indexent là-dessus. Permet de joindre Meta ad → opt-in landing → survey GHL →
call → vente → paiement Stripe sans clés vendor-specific.

## Conventions

- `.env.local` (gitignored) : tous les secrets. `.env.local.template` =
  squelette public.
- Service-role uniquement pour les pipelines / agents internes. Anon key
  réservée à des surfaces publiques futures (à activer policy par policy).
- Anonymisation `pattern_signals` : `client_slug`, `metric`, `delta_pct`,
  `anonymized` (jsonb). Jamais de chiffres absolus, jamais de PII.

## Roadmap (rappel)

| Phase | Sem | Livrable | Critère succès |
|---|---|---|---|
| 1 | 1-2 | Data foundation | 0 CSV sur 7j |
| 2 | 3-4 | Observer + Analyste + Communicateur | 2 vraies anomalies / 1 sem, 0 faux+ |
| 3 | 5-6 | Exécutant Meta API | 1ʳᵉ décision auto-validée 1-clic, tracée |
| 4 | 7-8 | Simulation Monte-Carlo | 1 décision majeure simu vs réalité ≤30% |
| 5 | 9-10 | Méta-agent + pattern_signals | 1 agent auto-proposé construit |
| 6 | 11-12 | Réplication Alex/Valentin | Playbook plug & play |

Plan détaillé : `/Users/Antoine/.claude/plans/enchanted-plotting-platypus.md`.

## Workflow dev

```bash
cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi
# Variables et clés via .env.local (gitignored)
# Supabase MCP est déjà configuré dans .mcp.json (scope projet)
python3 -m pipelines.<module>   # exécuter un pipeline
```
