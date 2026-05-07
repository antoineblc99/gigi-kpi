# Backfill RAW — Gigi KPI

Récupère l'historique **Meta Ads + GHL + vTurb** et remplit les sheets RAW du Google Sheet `KPI_Léa`.

## Structure

```
backfill/
├── auth.py                  # OAuth Google (token_pro.json)
├── backfill_meta.py         # Meta Ads → Meta_Ads_Raw, Meta_Ads_Raw_VSL, AdSet_Raw, Creative_Raw
├── backfill_ghl.py          # GHL → GHL_Calls_Raw, GHL_Optins_Raw, GHL_Surveys_Raw
├── backfill_vturb.py        # vTurb → VTurb_Raw, VTurb_Retention_Curve
├── run.py                   # Orchestrateur CLI
└── requirements.txt
```

## Usage

```bash
# Activer l'env
source .venv/bin/activate

# Backfill complet (depuis les dates de lancement par source)
python run.py

# Plage custom pour tout
python run.py --from 2026-03-05 --to 2026-04-11

# Skip certains backfills
python run.py --skip meta

# Forcer la ré-écriture
python run.py --force

# Un seul backfill
python backfill_meta.py --from 2026-03-05 --to 2026-04-11
```

## Env vars requises (~/.zshrc)

- `META_ACCESS_TOKEN` — token Meta Business
- `GHL_API_KEY` — Private Integrations token GHL (fallback si `GHL_Config!B2` vide)
- `VTURB_API_TOKEN` — Analytics API token vTurb

## Google auth

Utilise `~/.config/google/credentials.json` + `~/.config/google/token_pro.json`.
Si le token n'existe pas, OAuth flow local démarre au premier run.

## Sources

| Source | ID/URL |
|---|---|
| Sheet KPI_Léa | `1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo` |
| Meta campagne VSL | `120243478827620073` (depuis 2026-04-09) |
| Meta campagne Follow | `120241957177570073` (depuis 2026-03-05) |
| GHL Location | `TTzAZhJJwPHQobNiXjWJ` |
| GHL Calendriers | VSL `8ECqPVcPGz81JGlzCmoG` · Follow `AQ8RmdYw7iyru79Axymf` · Bienvenue `BCghpu5fgGfkROyaQge5` |
| GHL Survey post-VSL | `QMdJpJZx7K7Tl1oWieVw` |
| vTurb player VSL Lea | `69a583a3260b750c46a983fb` (1184s) |

## Notes

- Toutes les dates en colonne A sont normalisées en ISO `yyyy-mm-dd` (format Sheets `DATE`)
- Dédup par (Date, ID) pour AdSet/Creative/Calls
- Les scores type "10/10" (survey motivation) sont écrits en RAW pour éviter le parsing date de Sheets
