# UTM Tracking — Gigi Academy

End-to-end attribution: Meta ad → landing page → GHL contact → fact_payment.

## Vue d'ensemble

```
Meta Ad (URL params)
  → Landing page giginails.com (utm-tracker.js capture)
  → Form submit (hidden fields auto-rempli)
  → GHL contact (custom field attribution_ad_id)
  → Supabase dim_lead.utm_* + fact_call.lead_id
  → fact_payment (via Stripe sync, lead_id matché par email)
```

## 1. Convention UTM Meta Ads

À configurer dans **chaque ad** (Ads Manager → URL parameters → Build a URL parameter) :

| Param         | Valeur                          | Sens                          |
|---------------|---------------------------------|-------------------------------|
| `utm_source`  | `facebook` ou `instagram`       | Plateforme                    |
| `utm_medium`  | `paid`                          | Toujours `paid` côté ads      |
| `utm_campaign`| `{{campaign.id}}`               | ID Meta de la campagne        |
| `utm_content` | `{{ad.id}}`                     | **= attribution_ad_id**       |
| `utm_term`    | `{{adset.id}}`                  | ID Meta de l'adset            |

Meta remplace `{{ad.id}}` etc. au runtime — un seul template suffit pour toutes les ads.

URL exemple servie au browser :
```
https://giginails.com/vsl?utm_source=facebook&utm_medium=paid&utm_campaign=120243478827620073&utm_content=120243478827700073&utm_term=120243478853250073&fbclid=IwAR…
```

## 2. Installation du tracker sur giginails.com

### Option A — Script externe (recommandé si on contrôle le hosting)

Upload `static/utm-tracker.js` à la racine du site, puis dans le `<head>` des pages landing + VSL :

```html
<script src="/utm-tracker.js" defer></script>
```

### Option B — Script inline (Webflow, GHL, ClickFunnels)

Coller le contenu intégral de `static/utm-tracker.js` entre `<script>…</script>` dans le **header tracking code** du site.

### Option C — GHL Funnel (cas Gigi actuel)

GHL > Settings > Funnel/Website > **Tracking Code (Header)** > coller le script en inline.
Refresh les funnels concernés (LP + page VSL + page survey + page TY).

## 3. Vérification

1. Ouvre `https://giginails.com/?utm_source=facebook&utm_medium=paid&utm_campaign=test&utm_content=ad_test&utm_term=adset_test`
2. Console DevTools → `window.gigiAttribution.get()` doit retourner :
   ```js
   { utm_source: 'facebook', utm_medium: 'paid', utm_campaign: 'test',
     utm_content: 'ad_test', utm_term: 'adset_test', first_seen_at: '…' }
   ```
3. `document.cookie` doit contenir `gigi_attribution=…`.
4. Soumets le form — vérifie dans GHL que les champs `utm_source/medium/campaign/content/term` sont remplis sur le contact.

## 4. Hidden fields à ajouter dans les forms

Sur chaque form (LP opt-in **et** survey post-VSL) :

```html
<input type="hidden" name="utm_source"   value="">
<input type="hidden" name="utm_medium"   value="">
<input type="hidden" name="utm_campaign" value="">
<input type="hidden" name="utm_content"  value="">
<input type="hidden" name="utm_term"     value="">
<input type="hidden" name="fbclid"       value="">
<input type="hidden" name="attribution_ad_id" value="">  <!-- alias = utm_content -->
```

Le tracker auto-remplit ces inputs au `DOMContentLoaded` si le visiteur a une attribution stockée.

## 5. Custom field GHL

Créer un custom field sur le contact GHL :

| Field name             | Type | Source                        |
|------------------------|------|-------------------------------|
| `attribution_ad_id`    | text | hidden field form = utm_content |
| `utm_source`           | text | hidden field form             |
| `utm_medium`           | text | hidden field form             |
| `utm_campaign`         | text | hidden field form             |
| `utm_content`          | text | hidden field form (= ad_id)   |
| `utm_term`             | text | hidden field form (= adset_id)|
| `fbclid`               | text | hidden field form             |

### Création via API GHL

Si tu as `$GHL_API_KEY` (Private Integration) en env :

```bash
curl -X POST 'https://services.leadconnectorhq.com/locations/TTzAZhJJwPHQobNiXjWJ/customFields' \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json' \
  -d '{"name":"attribution_ad_id","dataType":"TEXT","model":"contact"}'
```

Sinon :
> **Action manuelle Antoine :** GHL > Settings > Custom Fields > Add Field
> name = `attribution_ad_id`, type = Text, object = Contact.
> Idem pour `utm_source/medium/campaign/content/term/fbclid`.

## 6. Pipeline aval

Les pulls GHL (`pipelines/pull_ghl.py`, à venir) liront ces custom fields et popleront `dim_lead.utm_*` + `fact_lead.ad_id_first_touch`.

Le pull Stripe (`pipelines/pull_stripe.py`) matche `customer.email → dim_lead.email` et écrit `fact_payment.lead_id`. À partir de là, on a la chaîne complète : `ad_id → lead_id → payment_id` pour calculer un ROAS par ad / par campagne.

## 7. Edge cases

- **Multi-touch** : on garde le `first_touch` (premier ad cliqué). Si nouveau click avec `utm_source` présent → overwrite (last paid touch wins).
- **Refresh sans UTM** : on conserve l'attribution stockée (cookie + localStorage 30j).
- **Attribution croisée** : cookie scopé sur `.giginails.com` → fonctionne entre subdomains.
- **iOS/Safari ITP** : localStorage purgé après 7j, cookie 1st-party persiste 30j → backup OK.
