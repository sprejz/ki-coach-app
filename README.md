# KI Coach App

iPhone-optimierte Progressive Web App (PWA) für den täglichen Triathlon-Coaching-Workflow von Hendrik Sprejz (Castle Triathlon Malbork, 6.9.2026, Zielzeit 10:50h).

Details zu Architektur, Entscheidungsregeln, API-Contract und Changelog stehen in [`CLAUDE.md`](./CLAUDE.md) — das ist die führende Doku für dieses Repo. Diese README ist der Einstiegspunkt.

## Overview

Die App begleitet zwei tägliche Checks (Abend-Check plant den nächsten Tag, Morgen-Override entscheidet direkt vor dem Training) sowie Workout-Analyse, Erholungs-Tracking, freien Coach-Chat und TrainingPeaks-Integration. Claude bewertet Körpersignale (Knie, Achilles, Waden, Muskelkater, Krankheit), Wetter und Trainingsbelastung und liefert GO/MOD/SKIP-Entscheidungen pro Sportart, die direkt in TrainingPeaks geschrieben werden können.

Backend: Python/FastAPI. Frontend: eine serverseitig gerenderte HTML-Datei (Jinja2), kein separates JS-Framework. Gehostet auf Railway.

## Folder-Struktur

```
ki-coach-app/
├── app.py               FastAPI Backend (Endpoints, Caching, Job-Queue)
├── orchestrator.py       Kontrollfluss der Agent-Pipeline
├── agents/               Ein Modul je Spezialist (Mediziner, Wetter, Chefcoach, Architekt, Periodisierer, Analyst, Chat, Ernährungsberater, ...)
├── prompts/de/           Statische Markdown-Prompts, die von den Agents geladen werden
├── translations.py       Alle UI-Texte und Claude-Prompts (de/en), inkl. Monolith-Fallback-Prompt
├── templates/index.html  Frontend, 7 Tabs, iPhone-optimiert
├── training_load.py      CTL/ATL/TSB aus TSS-Historie (deterministisch)
├── nutrition.py           Ernährungstabelle (deterministisch)
├── strava.py              Strava-Auto-Match für die Analyse (direkte httpx-Calls)
├── coach_mcp.py           MCP-Server für Claude Desktop/Code (stdio lokal, HTTP remote)
├── tests/                 fixtures.py, test_offline.py, test_wiring.py, test_live.py
├── athlete.json           Athletenprofil (über Profil-Tab editierbar)
├── baseline.json          Schlaf-Baseline (AutoSleep-Mediane)
├── sleep_history.json     Letzte 14 AutoSleep-Nächte
├── Dockerfile / Dockerfile.mcp   Zwei Railway-Services (App + MCP)
└── railway.toml
```

## Setup

Voraussetzungen: Python 3.11+, ein Anthropic API Key.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=...
# optional, siehe CLAUDE.md für die vollständige Liste:
# TP_MCP_URL, APP_LANG, COACH_AGENTS, DATA_DIR, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

uvicorn app:app --reload
```

Für den optionalen MCP-Server (separates venv, siehe `CLAUDE.md` → v2.7.5/v2.7.6):

```bash
python3 -m venv .venv-mcp
.venv-mcp/bin/pip install -r requirements-mcp.txt
```

Alle Umgebungsvariablen, Railway-Setup und die zwei Deploy-Services sind in `CLAUDE.md` unter „Umgebungsvariablen (Railway)" dokumentiert.

## Git-Workflow

- **`main`** — Production/Stable. Deployed auf Railway.
- **`develop`** — Active Development. Ziel für Feature-Branches.
- **`feature/<name>`** — von `develop` abgezweigt, per PR zurück nach `develop` gemergt.

```bash
git checkout develop
git pull
git checkout -b feature/mein-feature
# ... arbeiten, committen ...
git push -u origin feature/mein-feature
# PR gegen develop öffnen
```

`develop` wird regelmäßig per PR nach `main` gemergt, sobald ein Stand production-ready ist.
