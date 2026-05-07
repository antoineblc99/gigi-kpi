# communicator-app

Page Vercel `gigi.scale-ia.app` qui génère, à chaque visite (cache 1h), un brief opérationnel humain à partir des données Supabase `gigi-data-os`.

## Stack
- Next.js 15 App Router (Node runtime, `maxDuration=300`)
- Tailwind v3 — palette Scale.IA Claude Mode
- Anthropic SDK — `claude-opus-4-7` (fallback `claude-opus-4-5`)
- Postgres direct (pg) — pool read-only `SET TRANSACTION READ ONLY`
- react-markdown + remark-gfm

## Architecture
```
app/
  page.tsx           Server component, charge le brief (cache 1h via agent_briefs)
  brief-view.tsx     Client : régénération, historique
  api/brief/route.ts GET ?force=1 = skip cache
  api/history/route.ts
lib/
  brief.ts           Tool-use loop Anthropic ↔ execute_supabase_sql
  sql.ts             Pool pg, SELECT-only, LIMIT 500 forcé
  store.ts           agent_briefs (création + insert + list)
```

## Env vars (Vercel)
| Variable | Source |
|---|---|
| `ANTHROPIC_API_KEY` | global |
| `SUPABASE_DB_URL` | string Postgres complet (`postgresql://postgres:PWD@HOST:5432/postgres?sslmode=require`) |
| `NEXT_PUBLIC_BASE_URL` | optionnel — défaut `http://localhost:3000` |

## Local dev
```bash
cp ../.env.local .env.local
# ajouter SUPABASE_DB_URL si pas déjà présent
npm install
npm run dev
```

## Deploy
```bash
vercel link
vercel env add ANTHROPIC_API_KEY production
vercel env add SUPABASE_DB_URL production
vercel --prod
```

## Comportement attendu
- 1ère visite : génère un brief, stocke dans `agent_briefs`.
- Visites suivantes < 1h : sert le brief stocké.
- Bouton "Régénérer" : `?force=1` → nouveau brief, nouveau row.
- Tables Supabase vides → le brief mentionne "data foundation in progress".

## Brand
Voir `~/.claude/projects/-Users-Antoine/memory/reference_scaleia_brand.md`.
