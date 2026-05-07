# Dashboards Gigi KPI

6 dashboards + 1 BASE aggregation layer + Benchmarks config + Closers_Config.

## Structure

```
dashboards/
├── rebuild_data_funnel_follow.py  # BASE aggregation Follow (Meta + Manual)
├── rebuild_data_funnel_vsl.py     # BASE aggregation VSL (Meta + GHL + vTurb)
├── closers_config.py              # Mapping GHL userId ↔ nom closer
├── build_global.py                # Dashboard Global + Benchmarks tab
├── build_funnel_follow.py         # Dashboard Funnel Follow v2
├── build_funnel_vsl.py            # Dashboard Funnel VSL v2
├── build_closer.py                # Dashboard Closer v2
├── build_setter.py                # Dashboard Setter v2
├── build_creatives.py             # Dashboard Creatives v2
└── rebuild_all.py                 # Orchestrator: rebuild tout en 1 commande
```

## Run

```bash
# Tout rebuilder (BASE + dashboards) — à lancer après chaque backfill
cd ~/Dev/projets/gigi-kpi
./scripts/backfill/.venv/bin/python scripts/dashboards/rebuild_all.py
```

## Pipeline quotidien recommandé

```bash
# 1. Backfill data fraîche (Meta + GHL + vTurb)
./scripts/backfill/.venv/bin/python scripts/backfill/run.py

# 2. Rebuild BASE + dashboards
./scripts/backfill/.venv/bin/python scripts/dashboards/rebuild_all.py
```

## Scheduling

Pour tourner auto chaque matin à 7h (macOS launchd) :

```bash
# Créer ~/Library/LaunchAgents/com.gigi.kpi.plist :
cat > ~/Library/LaunchAgents/com.gigi.kpi.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.gigi.kpi</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd ~/Dev/projets/gigi-kpi &amp;&amp; ./scripts/backfill/.venv/bin/python scripts/backfill/run.py &amp;&amp; ./scripts/backfill/.venv/bin/python scripts/dashboards/rebuild_all.py</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/gigi-kpi.log</string>
  <key>StandardErrorPath</key><string>/tmp/gigi-kpi.log</string>
</dict>
</plist>
EOF

# Charger
launchctl load ~/Library/LaunchAgents/com.gigi.kpi.plist
```

Vérifier : `launchctl list | grep gigi` — doit apparaître.

## Onglets créés dans le Sheet KPI_Léa

| Onglet | Type | Rôle |
|---|---|---|
| Dashboard Global | Dashboard | P&L + comparaison VSL vs Follow |
| DashBoard_Funnel_Follow_v2 | Dashboard | Funnel IG → DM → Call → Vente |
| DashBoard_Funnel_VSL_v2 | Dashboard | Funnel Ads → LP → Opt-in → VSL → Call → Vente |
| DashBoard_Closer_v2 | Dashboard | Ranking par closer |
| DashBoard_Setter_v2 | Dashboard | Ranking par setter |
| DashBoard_Creatives_v2 | Dashboard | Top 20 créas + hook/hold rates |
| Data_Funnel_Follow | BASE | Agrégat quotidien Follow (25 cols) |
| Data_Funnel_VSL | BASE | Agrégat quotidien VSL (25 cols) |
| Benchmarks | Config | Seuils target/excellent par métrique (éditable) |
| Closers_Config | Config | Mapping GHL userId ↔ nom (éditable) |
