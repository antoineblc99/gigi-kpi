# Pipelines — gigi-data-os

Pulls ETL Meta / GHL / Tally / Stripe / vTurb → Supabase `gigi-data-os`.

## Setup

```bash
cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi
source .venv/bin/activate
# .env.local doit contenir SUPABASE_* + META_* + GHL_*
```

## pull_meta.py

Pull complet Meta Ads → Supabase. Idempotent (upsert sur PK).

| Table | PK | Contenu |
|---|---|---|
| `dim_campaign` | `campaign_id` | Campagnes actives + objectif + statut |
| `dim_adset` | `adset_id` | AdSets + campaign_id |
| `dim_ad` | `ad_id` | Ads + hook_text + thumbnail (depuis creative) |
| `dim_creative` | `creative_id` | video_id, hook_transcript (1ère ligne body), body, cta |
| `fact_ad_daily` | `(ad_id, date)` | spend / imp / clicks / lpv / results / cost_per_result / ctr / cpc / cpm / reach / followers_ig / vsl_optin / vsl_call_booked |

### Usage

```bash
# Dry-run (n'écrit rien) sur 7 jours
python pipelines/pull_meta.py --days 7 --dry-run

# Backfill 90 jours (default)
python pipelines/pull_meta.py

# Période custom
python pipelines/pull_meta.py --since 2026-03-01 --until 2026-04-30

# Compte ad spécifique (default = META_AD_ACCOUNT_ID env)
python pipelines/pull_meta.py --account-id act_912497154802623
```

### Mapping events Meta → colonnes

Configurable via `.env.local` :

| Var | Default | Colonne |
|---|---|---|
| `META_EVENT_VSL_OPTIN` | `VSL_OptIn` | `vsl_optin` |
| `META_EVENT_VSL_CALL_BOOKED` | `VSL_Call_Booked` | `vsl_call_booked` |
| `META_EVENT_LEAD` | `offsite_conversion.fb_pixel_lead` | utilisé pour `results` (fallback) |
| `META_EVENT_COMPLETE_REGISTRATION` | `complete_registration` | (réservé Phase 2) |

`results` = priorité `vsl_optin` > `leads` > `link_clicks`. Aligné sur l'objective de la campagne.
`followers_ig` = action_type `onsite_conversion.follow` (pas `post`). Cf. `feedback_meta_ads_cost_calc`.

### Anti-erreurs coûts

- **Jamais** Cost per Action au niveau account.
- `cost_per_result` est calculé par ad : `spend / results`. Toujours filtrer par campaign_id avant agrégation.
- Source de vérité finale : CSV export Ads Manager > pull_meta > MCP API.

### Rate limiting

- Backoff exponentiel (5s → 300s) sur Meta error code 17 (user req limit) et 429.
- Max 8 retries par appel.
- Si 90j de pull saturent l'API, refaire en 2 fois : `--days 45` puis `--since`.

## Idempotence

Toutes les tables ont un PK. Upsert avec `on_conflict=<pk>`. Une relance ne duplique pas.

## Vérification SQL

```sql
SELECT count(*), min(date), max(date) FROM fact_ad_daily;
SELECT campaign_id, count(*) FROM dim_ad GROUP BY 1;
```
