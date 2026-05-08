# SOP : Systeme de Reporting KPI Automatise

## Vue d'ensemble

Systeme complet de collecte, centralisation et reporting automatique des KPIs d'un business de coaching/formation qui utilise des funnels Meta Ads + GoHighLevel.

**Resultat final** : chaque matin les donnees sont collectees, chaque soir un report est envoye dans Slack avec les metriques cles des 2 funnels + le closing.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCES DE DONNEES                       │
├──────────────────┬──────────────────┬───────────────────────┤
│   Meta Ads API   │   GHL API        │   Formulaires manuels │
│   (2 campagnes)  │   (calendriers)  │   (closers/setters)   │
└────────┬─────────┴────────┬─────────┴───────────┬───────────┘
         │                  │                     │
         │ 6h00             │ 6h45                │ Fin de journee
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              GOOGLE SHEET — Couche RAW                      │
│                                                             │
│  Meta_Ads_Raw    AdSet_Raw    Creative_Raw                  │
│  GHL_Raw_Data    GHL_Optins_Raw    GHL_Surveys_Raw          │
│  GHL_Calls_Raw   KPI Closer    KPI Setter                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ 21h30 — Apps Script (DailyReport.gs)
                         │ Lecture + Jointure + Calcul des taux
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              GOOGLE SHEET — Couche BASE                     │
│                                                             │
│  Data_Funnel_VSL          Data_Funnel_Follow                │
│  (ads → optin → survey    (ads → follow → DM               │
│   → call → vente)          → call → vente)                  │
│                                                             │
│  Data_Closing                                               │
│  (par closer, par jour)                                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ 21h30 — Slack Webhook
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    SLACK REPORT                             │
│                                                             │
│  📊 Daily Report — 11/04                                   │
│  🎯 FUNNEL VSL : spend, optins, calls, ventes              │
│  📱 FUNNEL FOLLOW : spend, followers, calls, ventes        │
│  💰 CLOSING : par closer, cash contracte/collecte          │
└─────────────────────────────────────────────────────────────┘
```

---

## Pre-requis

### Outils necessaires
- **Google Sheets** (gratuit) — centralisation des donnees
- **Google Apps Script** (gratuit, integre a Sheets) — automatisation
- **Meta Business Suite** — acces API pour les donnees publicitaires
- **GoHighLevel** — CRM avec calendriers et formulaires
- **Slack** — canal de reporting (webhook gratuit)

### Acces API necessaires
| Service | Ce qu'il faut | Ou le trouver |
|---|---|---|
| Meta Ads | Access Token + Ad Account ID | Meta Business Suite > API |
| GoHighLevel | API Key (Private Integration) | Settings > Integrations > API Key |
| Slack | Webhook URL | api.slack.com > Create App > Incoming Webhooks |

---

## Etape 1 : Structurer le Google Sheet

### Principe des 4 couches

| Couche | Role | Qui ecrit | Qui lit |
|---|---|---|---|
| **DASHBOARDS** | Visualisation | Personne (lecture seule) | Toi, l'equipe |
| **BASE** | Jointure des donnees | Apps Script (formules/scripts) | Les dashboards |
| **RAW** | Donnees brutes | Scripts auto + equipe manuellement | Les sheets BASE |
| **CONFIG** | Parametrage | Toi manuellement | Les scripts |

### Onglets a creer

**DASHBOARDS (position 0-5)**
```
Dashboard Global        — Vue P&L globale, les 2 funnels cote a cote
Dashboard Funnel 1      — Metriques detaillees funnel 1
Dashboard Funnel 2      — Metriques detaillees funnel 2
Dashboard Closer        — Performance par closer
Dashboard Setter        — Performance par setter
Dashboard Creatives     — Ranking des creatives pub
```

**BASE (position 6-8)**
```
Data_Funnel_1           — Jointure ads + leads + calls + ventes (funnel 1)
Data_Funnel_2           — Jointure ads + leads + calls + ventes (funnel 2)
Data_Closing            — Agregation par closer par jour
```

**RAW (position 9+)**
```
Meta_Ads_Raw            — Donnees Meta agregees par jour
AdSet_Raw               — Donnees par ad set par jour
Creative_Raw            — Donnees par creative par jour
GHL_Calls_Raw           — Calls bookes (individuels)
GHL_Optins_Raw          — Opt-ins formulaire (individuels)
GHL_Surveys_Raw         — Surveys de qualification (individuels)
GHL_Raw_Data            — Donnees calendrier agregees par jour
KPI_Closer              — EOD report des closers (manuel)
KPI_Setter              — EOD report des setters (manuel)
```

**CONFIG (derniere position)**
```
GHL_Config              — Cle API, Location ID, date derniere sync
```

### Headers des sheets cles

**Data_Funnel (VSL/Lead)**
```
Date | Ad Spend | Impressions | Link Clicks | CTR | CPC | LPV |
Opt-ins | Taux Opt-in | Surveys | Taux Survey | Qualifies | Taux Qualif |
Calls Bookes | Taux Booking | Calls Recus | Taux Show |
Ventes | Taux Closing | Cash Contracte | Cash Collecte |
Cout/Opt-in | Cout/Call | Cout/Vente | ROAS
```

**Data_Funnel (Follow/Traffic)**
```
Date | Ad Spend | Impressions | Clicks | CTR | CPC | Reach |
Profile Visits | Cout/PV | New Followers | Cout/Follower |
DMs envoyes | Liens envoyes | Taux Lien |
Calls Bookes | Taux Booking | Calls Recus | Taux Show |
Ventes | Taux Closing | Cash Contracte | Cash Collecte |
Cout/Call | Cout/Vente | ROAS
```

**Data_Closing**
```
Date | Closer | Source Funnel | Calls Planifies | Calls Recus |
Follow-ups | Acomptes | Ventes | Cash Contracte | Cash Collecte |
Qualif Leads /10 | Taux Closing
```

---

## Etape 2 : Script Meta Ads (Meta Ads.gs)

### Ce qu'il fait
- Appelle l'API Meta Marketing chaque jour
- Recupere les donnees au niveau Campaign, Ad Set, et Creative
- Ecrit dans `Meta_Ads_Raw`, `AdSet_Raw`, `Creative_Raw`
- Recupere les vrais followers Instagram via l'API IG Insights

### Configuration
```javascript
var CONFIG = {
  ACCESS_TOKEN: 'ton_token_meta',
  API_VERSION: 'v22.0',
  ACCOUNTS: [{
    name: 'Mon Compte',
    adAccountId: 'act_XXXXXXXXXX',
    igAccountId: 'XXXXXXXXXX',
    pageId: 'XXXXXXXXXX',
    campaignSheet: 'Meta_Ads_Raw',
    adsetSheet: 'AdSet_Raw',
    creativeSheet: 'Creative_Raw'
  }]
};
```

### Trigger
- Quotidien a 6h00
- Fonction : `fetchMetaAdsData`

---

## Etape 3 : Script GHL Sync (GHL_Sync.gs)

### Ce qu'il fait
- Appelle l'API GoHighLevel chaque jour
- Recupere tous les events de tous les calendriers
- Agregge par statut (booked, confirmed, cancelled, showed, no show)
- Ecrit dans `GHL_Raw_Data`

### Configuration
- Cle API stockee dans le sheet `GHL_Config` (cellule B2)
- Location ID dans `GHL_Config` (cellule B3)

### Trigger
- Quotidien a 6h45
- Fonction : `syncGHLToday`

---

## Etape 4 : Script Daily Report (DailyReport.gs)

### Ce qu'il fait
1. **Lit** les donnees deja synchees dans `AdSet_Raw` et `GHL_Raw_Data`
2. **Separe** les donnees par funnel (en filtrant par Ad Set ID)
3. **Lit** le formulaire EOD des closers (`KPI Closer`)
4. **Calcule** les metriques derivees (taux de conversion, couts, ROAS)
5. **Ecrit** dans `Data_Funnel_VSL` et `Data_Funnel_Follow`
6. **Envoie** le report Slack via webhook

### Configuration
```javascript
// IDs des Ad Sets par funnel — A ADAPTER
var VSL_ADSET_IDS = ['ID_ADSET_1', 'ID_ADSET_2'];
var FOLLOW_ADSET_IDS = ['ID_ADSET_3', 'ID_ADSET_4'];

// IDs des calendriers GHL — A ADAPTER
var CAL_VSL_ID = 'ID_CALENDRIER_VSL';
var CAL_FOLLOW_ID = 'ID_CALENDRIER_FOLLOW';
```

### Slack Webhook
```javascript
// Stocke dans les proprietes du script (securise)
PropertiesService.getScriptProperties().setProperty(
  'SLACK_WEBHOOK_URL',
  'https://hooks.slack.com/services/XXX/XXX/XXX'
);
```

### Trigger
- Quotidien a 21h30
- Fonction : `buildDailyReport`

---

## Etape 5 : Installation pas a pas

### 1. Creer le Google Sheet
- Creer un nouveau Google Sheet
- Creer tous les onglets (voir Etape 1)
- Ajouter les headers dans chaque onglet
- Figer la premiere ligne (ligne des headers) dans chaque onglet

### 2. Installer les scripts
- Menu `Extensions` > `Apps Script`
- Creer 3 fichiers : `Meta Ads.gs`, `GHL_Sync.gs`, `DailyReport.gs`
- Coller le code de chaque script

### 3. Configurer les tokens
- Lancer `setApiTokens()` (Meta) — une seule fois
- Remplir la cle API GHL dans l'onglet `GHL_Config`
- Lancer `setSlackWebhook()` — une seule fois

### 4. Tester
- Lancer `testManual()` pour tester Meta Ads
- Lancer `syncGHLToday()` pour tester GHL
- Lancer `testReport()` pour tester le Daily Report
- Verifier que les donnees apparaissent dans les sheets
- Verifier que le message Slack arrive

### 5. Activer les triggers
- Lancer `createDailyTrigger()` (GHL — 7h)
- Le trigger Meta Ads est deja configure dans le script
- Lancer `setupReportTrigger()` (Daily Report — 21h30)

---

## Etape 6 : Formulaires EOD (closers/setters)

### Formulaire Closer (a remplir chaque soir)
Champs :
- Prenom & Nom
- Nombre de calls planifies
- Nombre de calls recus
- Nombre de follow-ups
- Nombre d'acomptes
- Nombre de ventes
- Cash contracte
- Cash collecte
- Liens d'enregistrement des calls (Fathom, etc.)
- Estimation qualite des leads (/10)
- Debrief et commentaires sur la journee

### Formulaire Setter (a remplir chaque soir)
Champs :
- Prenom & Nom
- Nombre de conversations
- Nombre de liens envoyes
- Nombre de calls bookes
- Commentaires

> Ces formulaires peuvent etre crees dans GHL (survey/form) et connectes au sheet via webhook ou Zapier.

---

## Schema du flux de donnees

```
    META ADS                    GOHIGHLEVEL                EQUIPE
    ────────                    ───────────                ──────
   ┌─────────┐               ┌────────────┐          ┌──────────┐
   │Campagne │               │ Calendrier │          │ Form EOD │
   │  VSL    │               │    VSL     │          │  Closer  │
   └────┬────┘               └─────┬──────┘          └────┬─────┘
        │                          │                      │
   ┌────┴────┐               ┌─────┴──────┐          ┌───┴──────┐
   │Campagne │               │ Calendrier │          │ Form EOD │
   │ Follow  │               │   Follow   │          │  Setter  │
   └────┬────┘               └─────┬──────┘          └────┬─────┘
        │                          │                      │
        ▼                          ▼                      ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    GOOGLE SHEET (RAW)                       │
   │  AdSet_Raw  │  Creative_Raw  │  GHL_Raw_Data  │  KPI_Closer│
   └──────────────────────┬──────────────────────────────────────┘
                          │
                   DailyReport.gs
                   (jointure + calcul)
                          │
                          ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                   GOOGLE SHEET (BASE)                       │
   │     Data_Funnel_VSL    │    Data_Funnel_Follow              │
   │                 Data_Closing                                │
   └──────────────────────┬──────────────────────────────────────┘
                          │
                    Slack Webhook
                          │
                          ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                     SLACK REPORT                            │
   │  🎯 Funnel VSL    📱 Funnel Follow    💰 Closing           │
   └─────────────────────────────────────────────────────────────┘
```

---

## Metriques cles a suivre

### Par funnel
| Metrique | Formule | Objectif |
|---|---|---|
| CPL (cout par lead) | Ad Spend / Opt-ins | < 5€ |
| Taux opt-in → call | Calls / Opt-ins | > 10% |
| Taux show | Calls recus / Calls bookes | > 70% |
| Taux closing | Ventes / Calls recus | > 20% |
| Cout par call | Ad Spend / Calls bookes | < 50€ |
| Cout par vente | Ad Spend / Ventes | < 500€ |
| ROAS | Cash Collecte / Ad Spend | > 3x |

### Par closer
| Metrique | Formule | Objectif |
|---|---|---|
| Taux closing | Ventes / Calls recus | > 20% |
| Cash moyen par vente | Cash / Ventes | Proche du prix de l'offre |
| Qualite des leads | Moyenne qualif /10 | > 6 |

---

## Adaptation a d'autres business

Ce systeme fonctionne pour tout business qui a :
- Des **ads payantes** (Meta, Google, TikTok...)
- Un **CRM** avec calendrier (GHL, Calendly, HubSpot...)
- Un **processus de vente** (calls, DMs, closing)

### Pour adapter :
1. **Changer les IDs** des campagnes, ad sets, calendriers
2. **Adapter les headers** des sheets selon ton funnel
3. **Modifier le DailyReport.gs** pour calculer les bonnes metriques
4. **Adapter le format Slack** selon tes KPIs prioritaires

### Exemples de funnels supportes :
- Ads → VSL → Formulaire → Call → Closing
- Ads → Follow Instagram → DM → Call → Closing
- Ads → Webinaire → Call → Closing
- Ads → Lead Magnet → Email sequence → Call → Closing
- Ads → Application form → Call → Closing

---

## Maintenance

### Tokens Meta Ads
- Le token Meta expire regulierement (60-90 jours)
- Pour generer un token longue duree : Meta Business Suite > System Users
- Quand le token expire : lancer `setApiTokens()` avec le nouveau token

### Ajout de nouvelles campagnes/ad sets
- Ajouter les IDs dans `DailyReport.gs` (arrays `VSL_ADSET_IDS` / `FOLLOW_ADSET_IDS`)
- Les nouvelles creatives sont detectees automatiquement

### Debugging
- Verifier les logs : Apps Script > Execution log
- Tester manuellement : lancer `testReport()`
- Verifier les triggers : Apps Script > Declencheurs
