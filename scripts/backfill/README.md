# Backfill RAW — Gigi KPI

Récupère l'historique Meta Ads + GHL et remplit les sheets RAW du Google Sheet `KPI_Léa`.

## Structure

```
backfill/
├── auth.py              # OAuth Google (credentials.json)
├── backfill_meta.py     # Meta API → Meta_Ads_Raw, AdSet_Raw, Creative_Raw
├── backfill_ghl.py      # GHL API → GHL_Optins_Raw, GHL_Surveys_Raw, GHL_Calls_Raw
├── run.py               # orchestrateur CLI
└── requirements.txt
```

## Usage

```bash
# Backfill complet depuis les dates de lancement
python run.py

# Plage custom
python run.py --from 2026-03-05 --to 2026-04-11

# Force réécriture
python run.py --force
```

## Env vars requises (déjà dans ~/.zshrc)

- `META_ACCESS_TOKEN`
- `GHL_API_KEY`

## Google auth

Utilise `~/.config/google/credentials.json` + token OAuth.

## Sources

- Meta campagne VSL : `120243478827620073` (depuis 2026-04-09)
- Meta campagne Follow : `120241957177570073` (depuis 2026-03-05)
- GHL Location ID : `TTzAZhJJwPHQobNiXjWJ`
- Sheet KPI_Léa : `1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo`
