# Backlog — Léa / Gigi Academy

Idées d'amélioration trackées. Update libre par Antoine ou par les agents IA.

**Convention** :
- Status : `🆕 idea` · `🟢 next` · `🚧 doing` · `✅ done` · `🚫 wontfix`
- Effort : XS (<30min) · S (1-2h) · M (1/2 jour) · L (1-2 jours) · XL (>2 jours)
- Impact : 🔴 critical · 🟠 high · 🟡 medium · ⚪ low

---

## 🆕 Idées en attente

| Statut | Idée | Why / impact | Effort | Lien source |
|---|---|---|---|---|
| 🆕 | **Microsoft Clarity** sur landing + booking page | Comprendre où les leads cliquent / scrollent / drop. Heatmaps + session recordings. IA peut analyser via API les sessions des leads non-bookés. **Niveau de précision en +** : voir exactement où l'opt-in échoue (formulaire trop long ? CTA pas vu ?) | M (setup script + integration API) | Antoine 2026-05-08 |
| 🆕 | **vTurb** pull retention curve VSL | Savoir où les viewers drop la VSL (8min30 ? 3min ?). Métrique critique funnel VSL. Token déjà dispo `$VTURB_API_TOKEN`. Donnera le %watch en plus du fact_survey (qui = "watched + qualif rempli") | S | Antoine 2026-05-08 |
| 🆕 | **Bouton Chat data** sur gigi-communicator.vercel.app | Q&A on-demand : "combien de no-show Anaïs ce mois ?" → réponse 5 sec. Garde-fou : citer source SQL + poser question si vocab ambigu | M | Plan ABO |
| 🆕 | **Voice brief Telegram via Hermes + ElevenLabs** | Brief 90s audio quotidien sur Telegram (voix clonée). Tu écoutes en faisant ton café | M | Plan ABO |
| 🆕 | **Fathom transcripts pull** pour calls fermés | Analyser les objections + phrases qui closent + patterns par avatar. URLs déjà dans `fact_eod_closeuse.fathom_urls`, faut MCP Fathom sur compte Léa | L | Diagnostic 6 mai |
| 🆕 | **Orsay integration** (DM IG setting) | Pull volumes DMs envoyés/répondus + taux conversion par séquence. MCP Orsay déjà configuré. Funnel Setting actuellement aveugle pré-call | M | Antoine 2026-05-07 |
| 🆕 | **CAPI Meta avec fbclid** | +20-30% attribution Meta récupérée (Pixel cassé iOS 14+). fbclid déjà capturé 91% (`fact_contact.fbclid`) | L | KPI Registry §8 |
| 🆕 | **UTM dans DM IG (ManyChat)** | Permettrait attribution Follow funnel ad-level. Aujourd'hui 0 lead Follow attribué via UTM | M | Brief 8 mai |
| 🆕 | **Form Typeform EOD Setteuses** | Anaïs/Audrey/Mary remplissent un EOD setting (DMs envoyés, leads contactés, calls bookés). Webhook → Edge Function existante | S | Antoine 2026-05-07 V2 |
| 🆕 | **AI Board of Directors hebdo** | Podcast 10 min Sunday matin avec 4 voix IA (Observer/Stratège/Analyste/CEO) qui débattent du business. Premier mover absolu | XL | Plan ABO |
| 🆕 | **Live coaching closeuses** pendant calls | Fathom realtime API + Hermes ping privé à la closeuse pendant le call ("re-engage sur le budget vers 12min") | XL | Plan ABO |
| 🆕 | **Simulateur contrefactuel** | "Si tu coupes ces 3 ads et scale ces 2, projection ROAS P10/P50/P90" avant de prendre la décision | XL | Plan ABO |
| 🆕 | **Notion auto-sync warm leads** | Push les leads warm de `setting-app` vers une DB Notion accessible aux closeuses (alternative à l'app Vercel) | S | — |

## 🟢 Next (à faire en priorité)

| Statut | Idée | Why | Effort |
|---|---|---|---|
| 🟢 | **Routine `lea-daily`** sur claude.ai/code/scheduled | Récap soirée auto Slack + brief regéneré. Prompt validé prêt à coller | XS (toi) |
| 🟢 | **Audrey + Mary** aux 2 calendars GHL | Débloque la capacity (Anaïs seule actuellement). Sans ça scaler les ads = leak | XS (Mahdy) |
| 🟢 | **Modifs ads BM** : couper FOLLOW_STORY_80EUROS + scaler oVSL_Retargeting +180% | Couper drain 80€/sem, capter le ROAS retargeting (49x sur winner) | XS (toi) |

## 🚧 En cours

| Statut | Idée | Effort | Note |
|---|---|---|---|
| 🚧 | Standardiser AI Data System (template playbooks/) | L | Session dédiée à lancer |
| 🚧 | Vidéo YouTube explicative ABO | M | Session dédiée à lancer |

## ✅ Done

- ✅ Supabase project gigi-data-os (18 tables)
- ✅ 6 pipelines Python (Meta/GHL/Tally/Whop/Instagram/Capacity)
- ✅ Edge Function tally-eod (webhook Typeform real-time)
- ✅ Validator agent (15 checks)
- ✅ Brief BriefData JSON live (gigi-communicator.vercel.app)
- ✅ Composants React design template (Claude design)
- ✅ KPI Registry canonical
- ✅ Memory feedback Lea (cash sources, capacity shared, chat justify, etc.)
- ✅ Sentinel filter EOD + Validator rule
- ✅ Cleanup _legacy + branches mergées

## 🚫 Wontfix / skipped

- 🚫 Stripe pipeline (Léa utilise Whop + virements, pas Stripe)
- 🚫 Sub-domain `lea.scale-ia.app` (cf memory `feedback_no_subdomain_for_client_tools.md`)
- 🚫 Followers IG par ad attribution (Meta API ne l'expose pas, on a fact_ig_followers macro)

---

## Comment ajouter une idée

1. Open ce fichier
2. Ajouter une ligne dans la table `🆕 Idées` avec : nom court / why / effort / source
3. Si l'idée est claire et impact élevé, la déplacer en `🟢 Next`
4. Commit (optionnel mais recommandé)

```bash
cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi/
# edit BACKLOG.md
git add BACKLOG.md && git commit -m "backlog: add <idée>"
```

OU laisser un agent IA gérer : "Ajoute dans le BACKLOG l'idée X" → l'agent edit + commit.
