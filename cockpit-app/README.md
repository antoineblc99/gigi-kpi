# Cockpit — Gigi Academy (AIOS Léa)

Une page (Home), Next.js 15 App Router, Server Components, ISR 300 s.
Le cockpit **affiche** — la validation des décisions passe par Hermes/WhatsApp.

## Contenu

1. Header + badge santé global ("Tout roule" / "X points d'attention")
2. Brief du jour en langage naturel (template strings server-side, pas de LLM)
3. Jauge palier : cash contracté mois courant × 0,8 vs 30 000 € (paliers 30k → 60k → 100k, `context/strategy.md`)
4. 3 KPI : cash collecté 30 j · show rate 7 j · opt-ins 30 j (verdicts ✅⚠️🔴)
5. Décisions en attente (`decision_log` status=proposed, badge "validation via WhatsApp")
6. Fil d'activité agents (decision_log + fraîcheur pipelines + signaux inline, silence-si-vert)

## Garde-fous KPI (cf. `../KPI_REGISTRY.md`)

- Cash master = `fact_eod_closeuse.cash_collecte` — jamais Whop + EOD
- Filtre sentinel EOD identique à `communicator-app/lib/signals.ts`
- Opt-ins = `COUNT(DISTINCT lead_id)` sur `fact_contact`
- Attribution ad limitée au funnel VSL (Follow non attribuable ad-level)
- Chaque KPI porte sa source SQL en tooltip (`title=`)

## Env (Vercel + `.env.local`)

```
SUPABASE_PROJECT_URL=
SUPABASE_SERVICE_ROLE_KEY=   # server-side only, jamais exposée client
```

## Dev / build

```
npm install
npx next build
npm run dev
```
