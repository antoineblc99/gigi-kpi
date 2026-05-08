# KPI Registry — Léa / Gigi Academy

**Source de vérité unique** pour tous les KPIs trackés. Validé Antoine 2026-05-08.

À consulter en cas de doute, d'incohérence dans le brief, ou pour onboarder un nouvel agent IA / collaborateur.

---

## Convention de lecture

| Colonne | Sens |
|---|---|
| **KPI** | Nom métier |
| **Source** | Table Supabase `gigi-data-os` + colonne |
| **Pipeline** | Script qui peuple cette source |
| **Fraîcheur** | À quelle vitesse la source est à jour |
| **Calcul** | Formule SQL ou logique |
| **Garde-fous** | Erreurs typiques à éviter |

---

## 1. Acquisition (Marketing — Meta Ads)

| KPI | Source | Pipeline | Fraîcheur | Calcul / Notes |
|---|---|---|---|---|
| **Spend ad** | `fact_ad_daily.spend` | `pull_meta.py` | Quotidien | `SUM(spend) WHERE date >= 'X'`. JAMAIS au niveau account. |
| **Impressions / clicks / CTR / CPC** | `fact_ad_daily.{impressions,clicks,ctr,cpc}` | idem | idem | Niveau ad direct |
| **Landing Page Views** | `fact_ad_daily.lpv` | idem | idem | Action `landing_page_view` Meta |
| **VSL_OptIn Pixel** ⚠️ | `fact_ad_daily.vsl_optin` | idem (event `offsite_conversion.custom.1345846300753703`) | idem | **Ne PAS utiliser comme proxy opt-in** : sur-compte (refresh page = +1) |
| **VSL_Call_Booked Pixel** ⚠️ | `fact_ad_daily.vsl_call_booked` | idem (event `offsite_conversion.custom.1297436282311547`) | idem | Sous-compte. Préférer `fact_call` calendrier |
| **Followers IG (par ad)** ❌ | n/a | n/a | n/a | Meta API ne l'expose pas. Voir `fact_ig_followers` macro |
| **Funnel détecté** | `dim_ad.name` | `pull_meta.py` | idem | `name ILIKE '%VSL%'` → VSL ; `name ILIKE '%BROAD%' OR '%LAL%' OR '%Follow%'` → Follow |
| **Ad → AdSet → Campaign hierarchy** | `dim_ad.adset_id`, `dim_adset.campaign_id`, `dim_campaign.name` | idem | idem | Pour drill-down |

## 2. Funnel VSL (Web)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Opt-in (lead)** | `fact_contact` | `pull_ghl.py` (GHL `/contacts/search`) | A soumis le **form 1** sur landing. `COUNT(DISTINCT lead_id)` |
| **VSL watched** | `fact_survey` | `pull_ghl.py` (GHL `/surveys/submissions`) | A regardé jusqu'au bout + rempli qualif post-VSL |
| **Lead chaud** | `fact_survey` filtré | calculé | `quand_demarrer ILIKE '%Tout de suite%' OR '%30 prochains%'` AND `budget ILIKE 'Oui%'` |
| **Réponses détaillées** | `fact_survey.{statut_onglerie, quand_demarrer, budget, motivation, temps_dispo}` | idem | Profilage par avatar |

## 3. Funnel Follow (IG)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Followers IG gagnés (compte total)** | `fact_ig_followers.follower_count_delta` | `pull_instagram.py` (IG Graph `/{ig_id}/insights?metric=follower_count`) | Quotidien. Macro = ads + organic mêlés. Pas attribuable par ad. |
| **Followers IG total compte** | `fact_ig_followers.follower_count_total` | idem | Snapshot du jour |
| **Limite** | — | — | API IG ne donne que 29 derniers jours pour le metric |

## 4. Bookings & Calls

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Calls bookés VSL** | `fact_call` calendar `8ECqPVcPGz81JGlzCmoG` | `pull_ghl.py` (GHL `/calendars/events`) | `status NOT IN ('cancelled')`. Source de vérité — **PAS le pixel** |
| **Calls bookés Follow→Setting** | `fact_call` calendar `AQ8RmdYw7iyru79Axymf` | idem | idem |
| **Calls Bienvenue (post-vente)** | `fact_call` calendar `BCghpu5fgGfkROyaQge5` | idem | Pas un funnel acquisition |
| **Statut appointment** ⚠️ | `fact_call.status` | idem | Reste `'confirmed'` par défaut. Closeuses ne mettent pas à jour le calendar. **NO-SHOW réel via `fact_sale.stage_name`** |

## 5. Pipeline Sales (GHL)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Stage opportunité** | `fact_sale.stage_name` | `pull_ghl.py` (`/opportunities/search` + `/opportunities/pipelines` pour résoudre stage_id → name) | "R1 Planifié", "R1 No show", "R2 Planifié", "Gagné", "Follow Up <2 sem", "Follow Up Long Terme", "New Lead (A appeler)", "Form filled" |
| **No-show réel** | `fact_sale.stage_name = 'R1 No show'` | idem | Source de vérité (closeuses updatent la pipeline) |
| **Won/Lost** | `fact_sale.is_won` | idem | true si stage = "Gagné" |
| **Pipeline value** | `fact_sale.monetary_value` | idem | Montant signé (€) |
| **source_funnel** | `fact_sale.source_funnel` | `classify_funnel(raw.source)` dans `pull_ghl.py` | VSL / Setting. Mapping :<br>VSL = source IN (Form Léa Optin, Form Léa, Form Lea, Survey VSL Lea, VSL, *(VSL)*)<br>Setting = source IN (Setting, Appel de découverte - Gigi Academy) |

⚠️ **Volumes par funnel : `COUNT(DISTINCT lead_id)` PAS `COUNT(*)`** — un lead peut avoir 2 opps (capté Setting puis re-bookée via calendar). Pour les stages, `COUNT(*)` OK.

## 6. Closing (EOD closeuses)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Calls programmés agenda du jour** | `fact_eod_closeuse.calls_planifies` | Webhook Typeform → Edge Function `tally-eod` | RDV de la closeuse pour ce jour (bookés J-1 ou avant). PAS "planifiés par elle" |
| **Calls reçus (show)** | `fact_eod_closeuse.calls_recus` | idem | Closeuse a effectivement eu le call |
| **Show rate** | `calls_recus / calls_planifies` | calculé | Cible : 70-85% |
| **Ventes Setting / VSL** | `ventes_setting`, `ventes_vsl` | idem | Split par funnel d'origine |
| **Cash contracté** | `fact_eod_closeuse.cash_contracte` | idem | Total contrat signé (€) |
| **Cash collecté master** ⭐ | `fact_eod_closeuse.cash_collecte` | idem | **Source de vérité cash global** — carte + virement consolidé. Premier paiement encaissé. |
| **Encaissement initial** | `cash_collecte / cash_contracte` | calculé | Cible : >70% (sinon recouvrement à durcir) |
| **Fathom recordings** | `fact_eod_closeuse.fathom_urls[]` | idem | URLs des calls enregistrés |

## 7. Paiements (granularité)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Whop card payments** | `fact_payment` source='whop' | `pull_whop.py` (CSV manuel) | Subset carte uniquement. ~Mensuel |
| **Virements bancaires** | n/a | n/a | Pas tracké individuellement (consolidé dans EOD) |
| **Cash global master** | `fact_eod_closeuse.cash_collecte` | EOD | **JAMAIS additionner Whop + EOD = double comptage** |

## 8. Attribution lead → ad

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **utm_source** | `fact_contact.utm_source` | Auto Meta tag → GHL contact creation | 89% couverture (ig/fb) |
| **utm_content (= ad_id Meta)** | `fact_contact.utm_content` | idem | 89% couverture. JOIN `dim_ad.ad_id` pour résoudre nom |
| **utm_campaign** | `fact_contact.utm_campaign` | — | 0% couverture. Résoudre via `dim_ad.campaign_id` |
| **fbclid** | `fact_contact.fbclid` | idem | 91%. Utile pour CAPI futur (boost attribution iOS) |
| **Attribution Follow funnel** | n/a | n/a | Le clic ad → IG profile → DM ne porte pas l'utm_content. Ad-level attribution impossible sans modifier ManyChat |

## 9. Capacity closeuses (calendars)

| KPI | Source | Pipeline | Calcul / Notes |
|---|---|---|---|
| **Slots libres par jour** | `fact_calendar_capacity.slots_free` | `pull_calendar_capacity.py` (GHL `/calendars/{id}/free-slots`) | Snapshot quotidien |
| **Slots bookés par jour** | `fact_calendar_capacity.slots_booked` | dérivé de `fact_call` (status != cancelled) | idem |
| **Utilization %** | `slots_booked / (slots_booked + slots_free)` | calculé | Cible : 70-85% optimal |
| **Agrégation 2 calendars** ⚠️ | `MAX(slots_free) + SUM(slots_booked)` par date | calculé | Anaïs partage les 2 calendars VSL+Standard. **JAMAIS `SUM(slots_free)` = double comptage**. Voir `feedback_lea_capacity_shared.md` |

## 10. Validator (data health)

| Check | Source | Sévérité |
|---|---|---|
| Freshness fact_ad_daily | `MAX(date) < 36h` | red si stale |
| Freshness fact_contact / fact_sale | `MAX(date_added/updated_at) < 36h` | red |
| Freshness fact_call | `< 168h` (futur dominant) | yellow |
| Freshness fact_survey | `< 72h` | yellow |
| Freshness fact_eod_closeuse | `< 48h` | yellow |
| Freshness fact_payment | `< 168h` (CSV manuel) | yellow |
| Volume fact_ad_daily | `today_n vs 7d avg`, red si <-50% | yellow/red |
| Coherence calendar VSL ≈ EOD calls | tolerance 3× | yellow |
| Coherence Whop ≤ EOD cash | sinon double-comptage | yellow |
| Coherence GHL won ≈ EOD ventes | tolerance 30% | yellow |
| NULLs critiques | stage_name, lead_id, contact.lead_id | yellow si >0 |
| Capacity 72h | 70-85% optimal, <50% lead-constrained, >90% sales-constrained | yellow/red |

---

## Bibliographie mémoire associée

- `feedback_lea_cash_sources.md` — Master cash = EOD, jamais Whop+EOD
- `feedback_meta_ads_cost_calc.md` — Pas Cost per Action niveau account
- `feedback_lea_capacity_shared.md` — Capacity Anaïs partagée 2 calendars
- `feedback_chat_data_source_justify.md` — IA doit citer source SQL + poser question si vocab ambigu
- `reference_meta_ads_app.md` — App Meta + tokens
- `reference_claude_routines.md` — Best practices routines

---

## En cas de divergence

Si un brief, dashboard, ou agent IA donne un chiffre qui semble faux :

1. Identifier le KPI dans ce registre
2. Aller à la source SQL exacte (table.colonne)
3. Vérifier la fenêtre temporelle / les filtres / les jointures
4. Si bug pipeline → re-pull la source concernée
5. Si bug interpretation → mettre à jour ce registre

**Ce fichier = canonical. Toute correction métier doit y atterrir avant d'être propagée ailleurs.**
