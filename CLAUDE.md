# Gigi KPI — Reporting automatisé Gigi Academy

## Objectif
Centraliser toutes les données des 2 funnels Gigi Academy dans un Google Sheet, avec dashboards, report Slack quotidien, et analyse IA.

## Les 2 funnels

### Funnel VSL (Lead) — depuis le 9 avril
Ads → Landing page → Opt-in (form 1) → VSL (11 min) → Survey qualif (form 2) → Calendrier booking → Call → Closing

### Funnel Follow (Traffic) — depuis le 5 mars
Ads → Profil Instagram → Follow → DM automatisé (setter) → Setting → Call → Closing

### Closing (commun)
- Offre : 2000€ (paiement en plusieurs fois possible)
- Closers : Mary Tregan, Audrey Cuni, Anaïs Bruneel

## Sources de données

| Source | Outil | ID |
|---|---|---|
| Meta Ads — Campagne VSL | MCP meta-ads | `120243478827620073` (OUTCOME_LEADS) |
| Meta Ads — Campagne Follow | MCP meta-ads | `120241957177570073` (OUTCOME_TRAFFIC) |
| AdSets VSL | MCP meta-ads | Broad `120243478853250073`, Retargeting `120243478850530073` |
| AdSets Follow | MCP meta-ads | Broad `120241964220250073`, Lookalike `120241957177550073` |
| GHL — Calendrier VSL | MCP gohighlevel | `8ECqPVcPGz81JGlzCmoG` |
| GHL — Calendrier Standard (Follow) | MCP gohighlevel | `AQ8RmdYw7iyru79Axymf` |
| GHL — Calendrier Bienvenue | MCP gohighlevel | `BCghpu5fgGfkROyaQge5` |
| GHL — Survey post-VSL | MCP gohighlevel | via survey submissions |
| KPI Closer (EOD form) | Google Sheet | Sheet `KPI Closer_Léa` |
| KPI Setter (EOD form) | Google Sheet | Sheet `KPI Setter Insta_Léa` |
| Suivi DMs | Google Sheet | Sheet `Suvi Setting` |
| Slack report | MCP Slack | `#sales-ghl-report` (channel ID: `C0ANCSMPX3L`) |

## Google Sheet central
- **ID** : `1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo`
- **Nom** : KPI_Léa

### Architecture des onglets

```
🟢 DASHBOARDS (pos 0-5) — lecture seule, visualisation
  0. Dashboard Global        → P&L global, split VSL vs Follow côte à côte
  1. DashBoard_Funnel VSL    → métriques VSL détaillées + taux conversion
  2. DashBoard_Funnel_Follow → métriques Follow détaillées + taux conversion
  3. DashBoard_Closer        → perf par closer + tendances
  4. DashBoard_Setter        → perf par setter + taux conv DM→call
  5. Dashboard Creatives     → ranking créas par CTR, CPC, CPL

🟡 BASE (pos 6-8) — données jointes, remplies par DailyReport.gs
  6. Data_Funnel_VSL    → jour | spend | opt-ins | surveys | qualifiés | calls | ventes | ROAS
  7. Data_Funnel_Follow → jour | spend | PV | followers | DMs | calls | ventes | ROAS
  8. Data_Closing       → jour | closer | source | calls | ventes | cash

🔴 RAW (pos 9-18) — données brutes, remplies par scripts auto ou manuellement
  9.  Meta_Ads_Raw       → données Meta agrégées/jour
  10. AdSet_Raw          → par adset/jour (les 2 campagnes)
  11. Creative_Raw       → par créa/jour (les 2 campagnes)
  12. GHL_Optins_Raw     → opt-ins form 1 (individuel)
  13. GHL_Surveys_Raw    → surveys post-VSL (individuel + qualif)
  14. GHL_Calls_Raw      → calls bookés par calendrier (individuel)
  15. GHL_Raw_Data       → ancien agrégé calendrier (historique)
  16. KPI Closer_Léa     → EOD closers (manuel)
  17. KPI Setter Insta_Léa → EOD setters (manuel)
  18. Suvi Setting       → suivi convos DM (manuel)

⚙️ CONFIG (pos 19-21)
  19. Data_Base_Funnel      → ancien, MASQUÉ (remplacé par 6+7)
  20. GHL_Config            → API keys, IDs, sync
  21. Transcripts_Creatives → scripts des créas
```

## Automatisation — Pipeline quotidien

### Apps Script (dans le Google Sheet)

3 scripts dans `Extensions > Apps Script` :

| Script | Trigger | Fonction | Ce qu'il fait |
|---|---|---|---|
| `Meta Ads.gs` | 6h00 | `fetchMetaAdsData` | Pull Meta API → Meta_Ads_Raw, AdSet_Raw, Creative_Raw |
| `GHL_Sync.gs` | 6h45 | `syncGHLToday` | Pull GHL API → GHL_Raw_Data |
| `DailyReport.gs` | 21h30 | `buildDailyReport` | Lit RAW, sépare VSL/Follow, écrit BASE, envoie Slack basique |

Config :
- Meta token : stocké dans Script Properties (`setApiTokens()`)
- GHL API key : dans l'onglet `GHL_Config` cellule B2
- Slack webhook : stocké dans Script Properties (`setSlackWebhook()`)

Code source : `~/Dev/projets/gigi-kpi/apps-script/DailyReport.gs`

### Agent Claude schedulé (remote)

- **ID** : `trig_01JBgSTVfJ1dUed34PbbYzTY`
- **Schedule** : tous les jours à 22h (Europe/Paris)
- **MCP** : Zapier (Google Sheets) + Slack
- **Modèle** : claude-sonnet-4-6
- **Ce qu'il fait** : lit les sheets BASE, analyse les performances, identifie les goulots, compare aux benchmarks, envoie un report intelligent dans `#sales-ghl-report` avec diagnostic et actions
- **Gérer** : https://claude.ai/code/scheduled/trig_01JBgSTVfJ1dUed34PbbYzTY

### Skill `/kpi` (à la demande)

- **Fichier** : `~/Dev/skills/kpi-analyzer/skill.md`
- **Trigger** : `/kpi` dans Claude Code
- **Ce qu'il fait** : pull les 5 sheets via Zapier MCP, analyse les 2 funnels + closing + setters, identifie les problèmes, donne les actions prioritaires

## Documentation

### SOP Notion (pour les clients Scale.IA)
- **Page** : [Reporting KPI Automatisé](https://www.notion.so/33fc89b26d7981a9ae89eeed78fdd5f0)
- **Base** : Playbooks & SOPs
- **Contient** : architecture, installation pas à pas, scripts, métriques, adaptation

### SOP locale
- **Fichier** : `~/Dev/projets/gigi-kpi/SOP-KPI-Automatise.md`

## GHL Config
- Location ID : `TTzAZhJJwPHQobNiXjWJ`
- 3 team members sur les calendriers discovery

## Benchmarks de référence

| Métrique | Objectif | Excellent |
|---|---|---|
| CPL | < 5€ | < 2€ |
| Taux opt-in → call | > 10% | > 20% |
| Show rate | > 70% | > 85% |
| Taux closing | > 20% | > 30% |
| ROAS | > 3x | > 5x |
| Coût/vente | < 20% du prix offre | < 10% |

## Statut

### Fait
- [x] Architecture Google Sheet (21 onglets organisés)
- [x] Sheets RAW créés avec headers
- [x] Sheets BASE créés avec headers
- [x] Dashboard Creatives créé
- [x] Ordre des onglets réorganisé
- [x] Données VSL injectées (9-11 avril)
- [x] Données closing injectées (18-21 mars)
- [x] Apps Script Meta Ads.gs (existant, fonctionne)
- [x] Apps Script GHL_Sync.gs (existant, fonctionne)
- [x] Apps Script DailyReport.gs (nouveau, testé, trigger actif 21h30)
- [x] Slack webhook configuré → #sales-ghl-report
- [x] Report Slack basique (Apps Script) — testé OK
- [x] Agent Claude schedulé (22h daily) — report intelligent
- [x] Skill /kpi créé (analyse à la demande)
- [x] SOP Notion créée dans Playbooks & SOPs
- [x] SOP locale dans le projet

### A faire
- [ ] Remplir les RAW avec l'historique complet (backfill Meta + GHL)
- [ ] Designer les DASHBOARDS dans le Google Sheet (graphiques, mise en forme)
- [ ] Ajouter les données setter dans Data_Funnel_Follow (DMs, liens envoyés)
- [ ] Surveiller le premier run automatique (demain 6h + 21h30 + 22h)
