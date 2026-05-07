# Session C — Blockers

## 🟠 Stripe non configuré
**Quoi :** `STRIPE_SECRET_KEY` absent de `.env.local` et `~/.zshrc`.
**Impact :** `pipelines/pull_stripe.py` log "skipping" et exit 0. `fact_payment` reste vide.
**Pour débloquer :** Antoine ajoute dans `.env.local` :
```
STRIPE_SECRET_KEY=sk_live_...
```
Stripe Dashboard → Developers → API keys → Reveal restricted key (lecture sur charges + customers + subscriptions suffit).
Une fois ajouté : `python -m pipelines.pull_stripe --days 90` → backfill 90j auto.

## 🟠 Custom fields GHL `attribution_ad_id` + `utm_*`
**Quoi :** API GHL `customFields` n'est pas exposée par le MCP installé (le tool `ghl_create_custom_field` ne couvre que les **custom objects**, pas les contact fields).
**Impact :** Les hidden fields du form passent dans GHL mais ne sont pas attachés à un custom field structuré → invisible dans la fiche contact tant qu'on n'a pas créé les fields.
**Pour débloquer :** Action manuelle Antoine (5 min) :
GHL > Settings > Custom Fields > **+ Add Field** (object = Contact, type = Text), créer :
- `attribution_ad_id`
- `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `fbclid`

Détails dans `docs/UTM_TRACKING.md` §5.

## 🟢 Tally — API non utilisée (CSV fallback OK)
**Quoi :** `TALLY_API_KEY` + `TALLY_FORM_ID` non set.
**Impact :** Pipeline lit le CSV le plus récent dans `~/Downloads/` — fonctionnel mais demande un export manuel.
**Pour automatiser :** Antoine génère une API key sur tally.so/settings/integrations > API et la met dans `.env.local` :
```
TALLY_API_KEY=tly-…
TALLY_FORM_ID=<id du form EOD>  # à récupérer dans l'URL d'édition du form
```
