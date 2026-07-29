# KI Coach App — v2.7.8

## Ziel
iPhone-optimierte Progressive Web App (PWA) für den täglichen Triathlon-Coaching-Workflow von Hendrik Sprejz (Castle Triathlon Malbork, 6.9.2026, Zielzeit 10:50h).

## Architektur
- **Backend:** Python FastAPI (`app.py`, ein File)
- **Frontend:** Single HTML-Datei mit Jinja2-Templating (`templates/index.html`), iPhone-optimiert (320–390px)
- **i18n:** alle UI-Texte *und* alle Claude-Prompts in `translations.py` (`de` / `en`), Sprache über `APP_LANG`
- **Hosting:** Railway (Docker)
- **Claude-Modelle:**
  - `claude-haiku-4-5-20251001` → Abend-Check, Morgen-Check, Coach-Chat, TP-MCP-Calls über Claude
  - `claude-sonnet-4-6` → Workout-Analyse (braucht Reasoning über FIT-Daten)
- **Wetter:**
  - Prognose heute/morgen → **wttr.in** (`?format=j1`, Codes über `WTTR_TO_WMO` auf WMO gemappt)
  - Vergangene Tage → **Open-Meteo** Forecast-API mit `past_days=7`
  - Stündliches Workout-Fenster → **Open-Meteo Archive-API**
- **TrainingPeaks:** eigener MCP-Server auf Railway, angesprochen per **direktem JSON-RPC** (`call_tp_mcp`, SSE-Parsing). Der Umweg über den Claude-MCP-Connector wird nur noch von `call_claude_tp_mcp` genutzt.

## Umgebungsvariablen (Railway)
- `ANTHROPIC_API_KEY` — Claude API Key (Pflicht)
- `TP_MCP_URL` — TrainingPeaks MCP: `https://trainingpeaks-mcp-production-1a4f.up.railway.app/mcp` (optional; ohne → TP-Endpoints liefern `{"available": false}` bzw. HTTP 400)
- `APP_LANG` — `de` (Default) oder `en`
- `COACH_AGENTS` — `1`/`true`/`on` aktiviert die Agent-Pipeline. **Default aus** → Monolith-Prompt
- `DATA_DIR` — Verzeichnis für schreibbaren Zustand (`athlete.json`, `baseline.json`, `sleep_history.json`). **Auf Railway `/data` mit gemountetem Volume**, sonst ist nach jedem Deploy alles weg. Ohne die Variable = Repo-Verzeichnis (lokal)
- `PORT` — Railway setzt automatisch

**MCP-Service (zweiter Railway-Service, `Dockerfile.mcp`):**
- `MCP_TRANSPORT` — `http` (im Dockerfile gesetzt) oder `stdio`
- `MCP_TOKEN` — Bearer-Token, **Pflicht im HTTP-Modus**, min. 32 Zeichen. Ohne startet der Server nicht
- `COACH_URL` — URL der App (Default: die Produktions-URL)
- `RAILWAY_DOCKERFILE_PATH` — `Dockerfile.mcp`

**Kein Auth-Layer.** Der PIN-Schutz aus v2.6.86 wurde in v2.6.87 wieder entfernt; Google OAuth ist geplant, aber nicht implementiert. Die App ist derzeit öffentlich erreichbar.

---

## Dateistruktur
```
ki-coach-app/
├── CLAUDE.md            ← diese Datei (v2.7.8)
├── app.py               ← FastAPI Backend (~2200 Zeilen)
├── coach_mcp.py         ← MCP-Server für Claude Desktop + Code (stdio lokal / HTTP remote)
├── requirements-mcp.txt ← nur für coach_mcp.py, eigenes venv (.venv-mcp)
├── Dockerfile.mcp       ← Image des MCP-Service (zweiter Railway-Service)
├── orchestrator.py      ← Kontrollfluss der Agent-Pipeline
├── nutrition.py         ← Ernährungstabelle (deterministisch, von beiden Pfaden genutzt)
├── training_load.py     ← CTL/ATL/TSB aus der TSS-Historie (deterministisch)
├── agents/              ← base, medic, allgemeinmedic, weather, periodizer, head_coach, architect, fueling, analyst, chat
├── prompts/de/          ← statische Agent-Prompts, einer je Agent
├── tests/               ← fixtures.py, test_offline.py, test_wiring.py, test_live.py
├── translations.py      ← UI-Texte + Monolith-Prompts (de/en)
├── templates/
│   └── index.html       ← Frontend, 7 Tabs
├── athlete.json         ← Athletenprofil (über Profil-Tab editierbar)
├── baseline.json        ← Schlaf-Baseline (über Profil-Tab berechenbar)
├── sleep_history.json   ← letzte 14 AutoSleep-Nächte (serverseitig)
├── Dockerfile
├── railway.toml
└── requirements.txt     ← fastapi, uvicorn, httpx, anthropic>=0.40, jinja2, fitdecode
```

---

## Tabs (Reihenfolge im Frontend)
1. **Morgen** — Morgen-Override (Go/No-Go vor dem Training)
2. **Abend** — Abend-Check (plant den nächsten Tag)
3. **Analyse** — abgeschlossene Einheiten der letzten 5 Tage bewerten lassen
4. **Erholung** — Erholungs-Index, HRV-Verlauf, Marker-Status
5. **Chat** — freier Coach-Chat mit TP- und Wetterkontext
6. **Profil** — Athletendaten, Rennen, Baseline-Manager
7. **About** — Version, Infos

**Checks laufen asynchron** (v2.7.4): `POST /api/check-abend` bzw. `check-morgen` liefern sofort eine `job_id`, das Frontend pollt `GET /api/check/{job_id}` und zeigt dabei die aktuelle Orchestrator-Stufe.

**Startverhalten:** `GET /api/startup` liefert Wetter heute + morgen parallel. TP-Workouts werden **beim Server-Start** für 7 Tage in einem einzigen MCP-Call geprefetcht und im Frontend als Inline-Spinner nachgeladen — Splash blockiert nicht mehr.

---

## Workflow 1 — Abend-Check (`POST /api/check-abend`)
1. AutoSleep CSV Upload (optional)
2. Wetter morgen (im Browser geladen, an Backend mitgeschickt; Backend hat Fallback)
3. TP-Workouts für morgen (aus Cache) als Kontext
4. Fragebogen: Waden, Knie, Achilles L, Achilles R (je 0–10), Müdigkeit (1–5), Muskelkater (Multi-Select), Symptome
5. Claude (Haiku) → JSON mit Status, Sportarten + Badges, Beschreibung, Ernährung, optional `tp_struktur`
6. Dark Card mit GO/MOD/SKIP-Badges, Regen-Timeline, Metriken
7. Optional: Wassertemperatur bei Schwimmeinheit
8. „In TP anwenden" (Button erscheint nur bei MOD/SKIP) → `POST /api/tp/apply`

## Workflow 2 — Morgen-Override (`POST /api/check-morgen`)
Multipart-Form (wegen CSV-Upload). Gleicher Fragebogen wie Abend (inkl. Waden, Müdigkeit, Muskelkater — v2.6.1/v2.6.49), Wetter **heute**. CSV wird geparst, geflaggt und in `sleep_history.json` geschrieben.

---

## Entscheidungsregeln

**Wichtig:** Seit v2.4.31–v2.4.33 arbeitet der Prompt **nicht mehr mit starren Zahlenschwellen**, sondern mit sportmedizinischem Reasoning. `pain_thresholds` in `athlete.json` ist faktisch toter Ballast — `build_pain_rules()` gibt `""` zurück.

Der System-Prompt (`translations.py` → `prompt_system`) bzw. im Agent-Pfad die Prompts von Sportmediziner und Allgemeinmediziner instruieren Claude qualitativ:
- **Knie:** Steifigkeit → Umfang/Intensität runter, flach. Schmerz unter Last/Treppe → Lauf STOP, Rad wenn schmerzfrei, Aquajogging. Schwellung/Instabilität/Ruheschmerz → Pause.
- **Achilles:** Morgensteifigkeit die sich löst → angepasst ok. Schmerz beim Zehenstand/unter Last → Lauf STOP, Rad/Schwimmen ok. Verschlechtert sich verzögert (12–24h) → im Zweifel konservativ.
- **Waden:** Vorläufer von Achilles-/Soleus-Problemen. Waden + Achilles kombiniert hoch → Lauf STOP.
- **Muskelkater:** Beine leicht → Z1–Z2 ohne Tempo. Beine stark → max 30min Einrollen. Oberkörper → Schwimmen auf Technik. Überall → Regenerationstag.
- **Weiche Signale:** Müdigkeit ≥4 → Intensität raus. **Schlafdauer ignorieren**, primär HRV + WachBPM.
- **Entscheidungsregel:** immer klar GO / MOD / STOP, keine Rückfragen an den Athleten, im Zweifel konservativ.

### Allgemeinmediziner (v2.7.7) — Krankheit, Fieber, Blutdruck, Medikamente, chronische Befunde
Eigener Spezialist (`agents/allgemeinmedic.py`), zuständigkeitsmäßig oberhalb des Sportmediziners (`agents/medic.py` beurteilt seither nur noch Knie/Achilles/Waden/Muskelkater, hat `gesamturteil`/`leitsymptom` verloren). Prüfreihenfolge: Fieber → Symptome-Pille → Blutdruck/Medikamente → chronische Befunde als Kontextmodifikator — es gewinnt immer der höchste Schweregrad, kein Mittelwert.
- **Symptome:** gleich leicht/neu leicht → `eingeschraenkt` (Schwimmen `stop`, Rad/Lauf `kein_tempo`). Schlechter/neu mittel/neu schwer → `pause`, **`stop` für jede Sportart, ausnahmslos**.
- **Fieber:** ≥ 38 °C → mindestens `eingeschraenkt`, ≥ 38.5 °C → `pause` — unabhängig davon, was die Symptome-Pille sagt, das strengere Signal gewinnt.
- **Blutdruck:** deutlich erhöht (Richtwert ≥160/100) → mindestens `reduziert`/`kein_tempo`, kein Automatismus bei leicht erhöhten Werten.
- **Medikamente** (Freitext) und **chronische Befunde** (Profil, `athlete.json` → `chronische_befunde`, gilt dauerhaft) fließen als Kontext ein, senken die Vorsichtsschwelle bei akuten Signalen, erzwingen aber für sich allein nichts.
- **`gesamturteil: pause` ist ein harter Code-Stop, keine Prompt-Regel:** der Orchestrator (`orchestrator.py`) überspringt Chefcoach und Architekt komplett und setzt jede geplante Sportart deterministisch auf SKIP. Zu sicherheitskritisch (Herzmuskelentzündungsrisiko), um es allein der Prompt-Disziplin eines Modells zu überlassen — dieselbe Art Regel war in v2.7.2 schon einmal beim Sportmediziner falsch gelaufen.
- Die Krankennotiz in `POST /api/tp/apply` (siehe unten) prüft unabhängig davon zusätzlich Fieber ≥ 38 °C — eigene, konservativere Schwelle ohne LLM-Beteiligung.

### Wetter-Reasoning (alle drei Sportarten)
- **Gewitter:** alle Outdoor sofort STOP (Laufen genauso gefährlich wie Rad), Freiwasser sofort raus.
- **Regen:** leicht + Laufen ok (Kühleffekt); stark + >60min → kürzen/indoor. Rad bei Regen → Zwift, besonders >60min oder Tempo. Freibad bei Regen ok.
- **Hitze:** Lauf ~4–5% langsamer pro Grad über 20°C, früh/abends. Rad nach HF/RPE statt Watt (cardiac drift). **Hallenbad und Indoor/Zwift sind von Hitze ausgenommen** (v2.6.75). Freibad profitiert.
- **Kälte:** Lauf 10–15min länger aufwärmen, <0°C Atemwege schützen. Rad <10°C Hände/Füße, <5°C → Zwift. Freibad unter `swim_outdoor_min_celsius` (15°C) → Hallenbad, unter 14°C Kälteschock-Risiko.

### Wetter-Schwellen im Code
| Flag | Bedingung | Wirkung |
|---|---|---|
| `is_hot` | `temp_max > 28°C` | ♨️-Präfix im TP-Titel |
| `is_cold` | `temp_max < 0°C` | ❄️-Präfix im TP-Titel |
| `is_rain` | Regencode oder `rain_prob > 60%` | Prompt-Kontext |
| `is_thunderstorm` | WMO 95/96/99 | Prompt-Kontext |

`heat_threshold_celsius` in `athlete.json` (28°C) steuert nur den Prompt-Text, nicht `is_hot`.

### Indoor (Zwift)
Auf 75–80% der Outdoor-Dauer kürzen, Titel „Zwift (KI)". Indoor-Einheiten (`zwift`, `indoor`, `laufband`, `trainer` im Titel) sind von jeder Wetterlogik ausgenommen.

---

## AutoSleep & Erholung

### Baseline (`baseline.json`, über Profil-Tab neu berechenbar)
| Marker | Median | Flag |
|---|---|---|
| SchlafHRV | 35,0 ms | ≤ 29 (Hauptmarker) |
| WachBPM | 55,0 | ≥ 60 |
| SchlafBPM | 64,5 | ≥ 69 bzw. Median+4,5 |
| Atmung | 15,8/min | ≥ 17,5 |
| Effizienz | 92% | < 82% |
| nights | 153 | Stand 15.6.2026 |

`POST /api/baseline/calculate` nimmt mehrere CSVs, bildet Mediane. Flag-Grenzen außer SchlafBPM sind fix.

**Schlafdauer wird bewusst nicht geflaggt und nicht als Entscheidungsfaktor genutzt** — kurze Nächte sind bei Hendrik normal.

### CSV-Spalten (deutsch, letzte Zeile wird gelesen)
`Schlafend` (HH:MM:SS → Stunden), `SchlafHRV`, `WachBPM`, `SchlafBPM`, `AtmungDurchschnitt`, `Effizienz`

### Erholungs-Index (Frontend, `calcRecoveryIndex`)
Gewichteter 0–100-Score, pro Marker linear zwischen Median (=100) und Flag-Grenze (=0):
**HRV 40% · WachBPM 25% · SchlafBPM 15% · Atmung 10% · Effizienz 10%**
HRV-Trend: letzter Wert vs. Mittel der 3 vorherigen, ±3ms → up/down/stable.

### Sleep History
Serverseitig in `sleep_history.json`, max. 14 Einträge (v2.6.25/v2.6.26 — vorher localStorage, Migration läuft einmalig über `POST /api/sleep/history/sync`). Damit sind die Erholungswerte geräteübergreifend sichtbar.

---

## TrainingPeaks Integration

### Caching
- `_tp_cache`: `date_str` → Workouts. **TTL 1h**, **Stale nach 30min** → Stale-While-Revalidate, Hintergrund-Refresh.
- Prefetch beim Server-Start: 7 Tage in **einem** `tp_get_workouts`-Call, danach alle Workouts parallel per `tp_get_workout` „enriched" (Beschreibung + `subtype_id`).
- `_tp_events_cache`: Rennen, TTL 15min.
- `_history_wx_cache`: History-Wetter, TTL 6h.

### Genutzte MCP-Tools
`tp_get_workouts` · `tp_get_workout` · `tp_update_workout` · `tp_create_workout` · `tp_create_note` · `tp_get_events`

### Rennen kommen aus TP (v2.6.77–v2.6.80)
`tp_get_events` über max. **89 Tage** (TP-Limit 90). `atpPriority` → A/B/C. Zielzeiten werden per Namensabgleich aus `athlete.json` übernommen. Liefert TP 0 Events → Fallback auf `athlete.json`.

### `POST /api/tp/apply` — Konventionen
| Badge | Aktion in TP |
|---|---|
| **GO** | Nur Lauf/Rad/Golf und nur Outdoor: Wetterzeile wird der Beschreibung **vorangestellt** (Original bleibt erhalten). Titel bekommt ♨️/❄️ nur bei Extremwetter. |
| **MOD** | 1. Original umbenennen zu `↩️ {Titel} (KI)`. 2. Neues Workout `{Titel} – Angepasst (KI)` anlegen mit Dauer (aus Coach-Empfehlung geparst, sonst 75% des Originals, min. 20min), skalierter TSS, `subtype_id`, optional `structure` (`tp_struktur`) und `distance_km` (Schwimmen). Beschreibung = Wetter + Anpassungsgrund + Coach-Text + Original + Ernährung. |
| **SKIP / STOP** | Titel → `❌ {Titel} (KI)`. Original wird nicht gelöscht. |
| **Override** | „Trotzdem"-Button pro MOD/SKIP-Workout (v2.6.76): Titel wird bereinigt, Beschreibung bekommt „Athlete override – eigenes Gefühl" + Wetter, Originalbeschreibung bleibt darunter. |

Zusätzlich: bei SKIP/STOP **und** (Symptomen „neu schwer"/„schlechter" **oder** Fieber ≥ 38 °C) wird einmalig eine Kalendernotiz `🤧 Krank – Training gestrichen (KI)` mit den Körperwerten (plus Blutdruck/Medikamente, falls angegeben) angelegt — eigene, unabhängig vom Allgemeinmediziner geprüfte Schwelle, ohne LLM-Beteiligung (v2.7.7).

### Emoji-Handling
TP unterstützt kein Supplementary Unicode → 🔥 wurde durch ♨️ ersetzt (v2.6.58), das Hitze-Icon in Titeln später ganz entfernt (v2.6.92). Das Frontend strippt `❌ ↩️ 🔥 ❄️ ☀️ ♨️` und `(KI)`/`(AI)` aus TP-Titeln (`clean_title` bzw. v2.6.93).

`private_notes` wird **nicht** genutzt — TP ignoriert das Feld (v2.6.57).

### Backfill
`POST /api/admin/backfill-weather?days=30` (max 365) schreibt Wetter in vergangene Lauf/Rad/Golf-Einheiten. Bestehende Beschreibungen werden **angehängt, nicht überschrieben** (v2.6.71/72).

---

## Workout-Analyse (Analyse-Tab)

`GET /api/tp/workouts/history?days=5` → abgeschlossene Einheiten, nur Rad/Schwimmen/Lauf, SKIP-Einheiten ausgeblendet, mit Wettersymbol.

`POST /api/workout/analyze` (Multipart, optional FIT-Datei):
1. FIT-Datei sofort mit **fitdecode** parsen (v2.6.90 — `fitparse` verstand neuere Garmin-Protokolle nicht): Dauer, Distanz, Ø/Max Power, NP, Ø/Max HF, Kadenz, Pace, TSS, Arbeit + bis zu 20 Laps
2. Archiv-Wetter für das konkrete Workout-Zeitfenster (Priorität: TP-Startzeit → FIT-Startzeit → Tagesfallback)
3. TP-Workout direkt per MCP holen
4. Prompt bauen: unterscheidet **Ist-Daten** (`tssActual`, HF, Pace, `perceivedExertion`/RPE …) von reinen **Plan-Daten** und weist Claude an, auch ohne Ist-Werte zu bewerten (v2.6.94)
5. Job-Queue: Thread + `job_id`, Frontend pollt `GET /api/workout/analyze/{job_id}` (v2.6.5 — direkter Call lief in 60s-Timeouts)

Antwort-JSON: `{"bewertung":"gut|ok|verbesserungsbedarf","urteil":"…","naechster_schritt":"…","ernaehrung_einschaetzung":"…"}`
Prompt-Leitlinie: keine erfundenen Kritikpunkte, echte Zahlen statt Floskeln (v2.6.91).

`ernaehrung_einschaetzung` (v2.7.8) — Einschätzung, ob die Verpflegung zur Dauer/Intensität passte (Splits/HF-Drift, RPE, Dauer gegen die Tabellen-Basis aus `nutrition_for_duration()`), leer wenn die Datenlage nicht reicht. Erfindet keine eigenen Gramm-/ml-Zahlen — die kommen als `ernaehrung_basis` fertig berechnet in den Prompt.

---

## Coach-Chat (`POST /api/coach/chat`)
Freier Text, kein JSON. Kontext:
- System-Prompt mit Athletenprofil + Baseline
- TP-Workouts für **heute, morgen** und jeden im Text erwähnten Wochentag (bis 30 Tage voraus, `übermorgen` erkannt) — aus dem Cache
- Wetter heute + morgen
- **Ernährungstabelle + chronische Befunde** (v2.7.8) — Mix, Carbs/Flüssigkeit/Salz pro Stunde, die Dauer-Regeln aus `athlete.json` → `nutrition`, damit Ernährungsfragen mit echten Zahlen statt Rateversuchen beantwortet werden. Vorher fehlte das im Agent-Pfad komplett (der Monolith-Fallback hatte es schon).
- letzte 10 Nachrichten der Historie

Fehlt TP im Cache, wird ein Hintergrund-Refresh gestartet und Claude sagt dem Nutzer, dass die Daten in ~1 Minute da sind (v2.6.32). `max_tokens=1200`.

---

## Claude JSON-Contract (Abend/Morgen)
```json
{
  "status": "green|orange|red",
  "status_text": "Alles grün",
  "sportarten": [{
    "sport": "Rad",
    "badge": "GO|MOD|SKIP|STOP",
    "details": "1-2 Sätze Coach-Hinweis",
    "beschreibung": "Text für das TP-Beschreibungsfeld",
    "ernaehrung": "…",
    "tp_struktur": {"steps": [...], "primaryIntensityMetric": "percentOfFtp"},
    "distanz_m": 1500
  }],
  "autosleep_summary": null,
  "wetter_hinweis": "…",
  "prep": "…"
}
```

**Beschreibungs-Regeln im Prompt (v2.6.11–v2.6.14):**
- GO → Originalbeschreibung **exakt** übernehmen
- MOD mit Original → Originaltext nehmen und **nur die Werte** ändern, Satzstruktur behalten, Anpassungsgrund als Zeile anhängen
- MOD ohne Original → vollständige Struktur bauen
- Fundamentale Umstellung → erste Zeile `⚠️ Einheit komplett umgestellt`
- **Niemals** eine Aufwärmen/Hauptteil/Auslaufen-Struktur erfinden, die das Original nicht hat
- Sportspezifisch: Ein-/Ausschwimmen · Ein-/Ausrollen · Ein-/Auslaufen
- Schwimmen: Gesamtdistanz als erste Zeile, Teilblöcke müssen aufgehen

**`tp_struktur`** nur bei MOD mit echten Intervallen. Rad → `percentOfFtp`, Lauf/Schwimm → `percentOfThresholdPace`. `intensityClass`: `warmUp|active|rest|coolDown`. Wiederholungsblock: `{"type":"repetition","reps":N,"steps":[…]}`.

JSON wird über `_extract_json()` robust geparst (Markdown-Fences, `raw_decode` gegen „Extra data", Regex-Fallback). `max_tokens=3000` gegen abgeschnittenes JSON (v2.6.73).

---

## API-Endpoints
| Endpoint | Zweck |
|---|---|
| `GET /` | Frontend (no-cache Header) |
| `GET /api/version` | Version + Pipeline-Diagnose (`agents`: importable/enabled/env/import_error/anthropic_version) |
| `GET /api/load` | CTL/ATL/TSB + Wochenstruktur + Tage bis A-Rennen (für den MCP-Server) |
| `GET /api/startup` | Wetter heute + morgen parallel |
| `GET /manifest.json` | PWA-Manifest |
| `GET /api/athlete` · `POST /api/athlete/update` | Profil lesen/schreiben (GET inkl. TP-Rennen) |
| `GET /api/baseline` · `POST /api/baseline/calculate` | Baseline lesen / aus CSVs berechnen |
| `GET /api/sleep/history` · `POST /api/sleep/history/sync` | Schlafverlauf |
| `GET /api/weather?day=today\|tomorrow` | Wetter |
| `GET /api/tp/workouts?day=…` · `POST /api/tp/refresh` | TP-Workouts / Force-Refresh |
| `GET /api/tp/workouts/history?days=5` | Abgeschlossene Einheiten |
| `POST /api/tp/apply` | GO/MOD/SKIP/Override in TP schreiben |
| `POST /api/check-abend` · `POST /api/check-morgen` | Die zwei Checks — liefern sofort `{"job_id": …}` |
| `GET /api/check/{job_id}` | Job-Status der Checks (`pending`/`done`/`error` + `stage`) |
| `POST /api/coach/chat` | Coach-Chat |
| `POST /api/workout/analyze` · `GET /api/workout/analyze/{job_id}` | Analyse + Polling |
| `POST /api/admin/backfill-weather?days=30` | Wetter-Backfill |
| `POST /api/debug/fit-parse` · `POST /api/debug/coach-beschreibung` | Debug |

---

## Design — Style-A Dark Card
```css
background: #0f0f13;
card: #1a1a24;
border-radius: 12px;
accent-green: #1D9E75;
accent-orange: #EF9F27;
accent-red: #E24B4A;
text-primary: #e8e8e8;
text-secondary: #666;
```

**Status-Badges:** `GO` grün · `MOD` orange · `SKIP`/`STOP` rot (STOP wird wie SKIP behandelt, v2.4.12)

**Dark Card Inhalt:** Countdown bis Malbork · Status-Pill · Race-Strip (Priorität + Datum, alle 4 Rennen passen auf iPhone) · AutoSleep-Übersicht · Wetter (Icon + große Temp + farbige Badges) · stündliche Regen-Timeline · Metriken-Grid · Workout-Liste mit Badges und „Trotzdem"-Button · Prep-Zeile

**Splash:** Fortschrittsbalken, verschwindet sobald Wetter da ist; TP lädt als Inline-Spinner nach.

---

## Ernährung (automatisch in Empfehlung eingebaut)
| Dauer | Empfehlung |
|---|---|
| < 60 min | Nüchtern oder kleines Frühstück, danach normale Mahlzeit |
| 60–90 min | Leichtes Frühstück 2h vorher, Wasser reicht |
| 90 min – 3h | KH-Frühstück 2h vorher, 90g Carbs/h + 1 Saltstick/h, 25g Protein nachher |
| > 3h | Renntag-Protokoll: 100g Carbs 2h vorher, 90g/h + 1–2 Saltstick/h, Recovery-Mahlzeit |

Regeln stehen in `athlete.json` → `nutrition.rules`, werden von `nutrition_for_duration()` nach Dauer gematcht und bei MOD in die TP-Beschreibung geschrieben.
**Eigenes Gemisch:** Maltodextrin 19 + Fruchtzucker 2:1, 90g Carbs/h, 600ml/h (750ml/h bei Hitze).

**Ernährungsberater (v2.7.8, `agents/fueling.py`).** Ergänzt die Tabelle um Kontext, den eine reine Dauer-Tabelle nicht kennt — Hitze/Kälte, chronische Befunde, Renntag — als ein angehängter Satz. **Ändert nie die Zahlen selbst** und läuft nur, wenn es einen Grund gibt (Hitze/Kälte-Flag, chronische Befunde gesetzt, Dauer ≥ 90 min oder Renntag); sonst bleibt `ernaehrung` exakt der Tabellenstring, kein zusätzlicher Claude-Call. Ein Fehler dort wird lokal abgefangen und kippt nie den ganzen Check auf den Monolith-Fallback. `POST /api/tp/apply` verwendet für MOD-Workouts die im Check bereits berechnete `ernaehrung` weiter, statt sie mit einem zweiten Live-Call neu zu berechnen.

---

## Athleten-Profil
- **Name:** Hendrik Sprejz · **Gewicht:** 84 kg
- **FTP:** 286W · **Laufschwelle:** 5:20/km · **CSS:** 2:20/100m
- **Schwellen-HF:** Rad 145, Lauf 150
- **A-Rennen:** Castle Triathlon Malbork, 6.9.2026, 10:50h (Swim 1:20 / Bike 5:20 / Run 4:01)
- **B-Rennen:** Altmark-Triathlon 12.7.2026 (Olympisch), GEWOBA Bremen 9.8.2026 (70.3)

### HR-Zonen Rad (Schwelle ~145)
Z1 <117 · Z2 117–130 · Z3 131–137 · Z4 138–145 · Z5 146+

### Pace-Zonen Lauf
Z1 >6:30/km · Z2 6:00–6:30 · Z3 5:45–6:00 · Z4 5:10–5:30

---

## Changelog (verdichtet)

### v1.0 — Schritt 1
Abend-/Morgen-Check mit Claude-Auswertung, AutoSleep-CSV, Tageswetter, Dark Card.

### v2.0 — Schritt 2
Stündliche Regenprognose, TrainingPeaks MCP (Workouts laden + anwenden), PWA-Manifest.

### v2.1 — Profil & Baseline
Profil-Tab mit editierbaren Metriken, Baseline-Manager (Multi-CSV-Upload → Mediane).

### v2.2–v2.3 — Ladeperformance
Auto-Load beim Tab-Öffnen, `/api/startup` für parallele Calls, httpx Connection-Pooling, Cache-Busting, animierter Splash.

### v2.4 — TP-Konventionen & Wetter-Reasoning
Vollständige `tp_apply`-Konventionen (MOD = umbenennen + neu anlegen, SKIP-Rename, Krankennotiz). Direkter JSON-RPC-MCP-Call statt Claude-Umweg, SSE-Parsing. i18n-Extraktion nach `translations.py`. Haiku statt Sonnet für die Checks. Wetter-Provider Open-Meteo → wttr.in (ConnectTimeouts), Wetter im Browser laden. Waden-Slider ergänzt. **Starre Schmerzschwellen ersetzt durch sportmedizinisches Reasoning.**

### v2.5 — Erholung
Erholungs-Tab mit Erholungs-Index, HRV-Verlauf, Marker-Status. Sleep History. Splash mit Fortschrittsbalken, TP im Hintergrund.

### v2.6.0–v2.6.30 — Analyse, FIT, Chat
Analyse-Tab mit Coach-Urteil pro Einheit, Job-Queue gegen 60s-Timeouts, FIT-Upload. Coach-Chat-Tab. TP-Caching mit Stale-While-Revalidate, Non-Blocking Startup. Sleep History von localStorage auf Server. MOD adaptiert die originale TP-Struktur statt neu zu erfinden.

### v2.6.31–v2.6.60 — TP-Robustheit & Wetter in TP
7-Tage-Prefetch in einem MCP-Call. TP-Details direkt fetchen statt über Haiku. Wetter in TP-Workouts (Beschreibung + ♨️/❄️ bei Extremwetter), Backfill-Endpoint. `private_notes` verworfen. Chat mit Wochentag-Erkennung bis 30 Tage voraus.

### v2.6.61–v2.6.95 — Feinschliff
Hitze-Schwelle auf 28°C, Hallenbad/Indoor von Hitze ausgenommen. Athlete-Override-Button. Rennen aus TP-Events statt `athlete.json` (89-Tage-Limit, Fallback). Race-Strip iPhone-tauglich. PIN-Schutz eingeführt und wieder verworfen. FIT-Analyse auf Sonnet, `fitparse` → `fitdecode`. Analyse unterscheidet Ist- von Plan-Daten und liest RPE. Emoji-Präfixe werden im Frontend gestrippt.

### v2.7.8 — Ernährungsberater
Ernährung bleibt deterministisch (`nutrition.py`, seit v2.6.99 bewusst so — ein Modell hatte vorher Mengen erfunden). Ein neuer Agent ergänzt das um Kontext, den eine reine Dauer-Tabelle nicht kennt, an drei Stellen — aber nur die erste bekommt einen echten neuen Claude-Call, die anderen zwei werden nur angereichert, um nicht gegen die eigene Kosten-/Latenzdisziplin zu verstoßen (Architekt nur bei MOD, Periodisierer nur mit Belastungsdaten, Checks als Hintergrund-Job wegen der Laufzeit):

- **Tages-Check** — `agents/fueling.py` (neu) läuft pro Einheit nur bei Hitze/Kälte, chronischen Befunden, Renntag oder Dauer ≥90min, hängt dann einen Satz an die Tabellen-Basis an. Ohne einen dieser Gründe: kein Call, `ernaehrung` bleibt der reine Tabellenstring. Ein Fehler im Ernährungsberater wird lokal abgefangen statt den ganzen Check auf den Monolith umzuleiten — ein fehlender Zusatzsatz darf nicht so viel kosten wie ein fehlgeschlagener Mediziner-Call.
- **`POST /api/tp/apply`** verwendet für MOD-Workouts die im Check schon berechnete `ernaehrung` weiter, statt sie mit einem zweiten Live-Call neu zu rechnen — das Frontend schickt sie jetzt in der `operations`-Payload mit.
- **Coach-Chat** (`agents/chat.py`) — bekommt die Ernährungstabelle (Mix, Carbs/Flüssigkeit/Salz pro Stunde, Dauer-Regeln) und **chronische Befunde** in den Kontext. Nebenbefund: Der Agent-Pfad hatte `chronische_befunde` bisher gar nicht im Chat-Kontext, obwohl der Monolith-Fallback das schon konnte — als kleiner additiver Fix mitgezogen.
- **Analyse-Tab** (`agents/analyst.py`) — neues Feld `ernaehrung_einschaetzung`: bewertet anhand Splits/HF-Drift/RPE gegen die Tabellen-Basis, ob die Verpflegung während der Einheit gepasst hat. Bleibt leer statt zu spekulieren, wenn die Datenlage nicht reicht — spiegelt dieselbe Ehrlichkeitsregel, die für `datenlage: nur_plan` schon galt.
- **Bugfix im eigenen Code entdeckt:** `chronische_befunde: "keine"` ist ein nicht-leerer String und damit in Python *truthy* — ohne Fix hätte das Gate bei jedem Athleten, der im Profil schlicht „keine" einträgt, unnötig einen Claude-Call ausgelöst. Platzhalter wie „keine"/„keine bekannt"/„-" zählen jetzt explizit nicht als chronischer Befund.

Keine neue Fragebogen-Frage (z.B. Magen-Darm-Symptome während des Trainings) — bewusst außen vor gelassen, um den Umfang klein zu halten.

### v2.7.7 — Allgemeinmediziner (Krankheit als eigener Spezialist)
Der Sportmediziner behandelte Krankheit (die „Symptome"-Pille) bisher als bindenden Ganzkörper-Befund mit — fachlich vermischt das Sportverletzungs- mit Allgemeinmedizin. Sauber getrennt:

- **Sportmediziner** (`agents/medic.py`) ist jetzt rein muskuloskelettal — nur noch Knie/Achilles/Waden/Muskelkater. Verliert `gesamturteil`/`leitsymptom`, die es nur für die Krankheits-Logik brauchte.
- **Allgemeinmediziner** (`agents/allgemeinmedic.py`, neu) übernimmt Krankheit (migrierte Symptome-Pille) und bekommt vier neue Eingaben: **Fieber**, **Blutdruck**, **Medikamente** (alle drei pro Check im Fragebogen) und **chronische Befunde** (einmalig im Profil-Tab, `athlete.json` → `chronische_befunde`, gilt dauerhaft).
- **`gesamturteil: pause` ist die stärkste Regel der ganzen App** (Herzmuskelentzündungsrisiko bei Training mit Infekt) — durchgesetzt als **harter Code-Stop** im Orchestrator, nicht nur per Prompt-Disziplin: Chefcoach und Architekt werden komplett übersprungen, jede geplante Sportart deterministisch auf SKIP gesetzt. Genau diese Art Regel war beim Sportmediziner in v2.7.2 schon einmal falsch gelaufen, bevor der Prompt nachgeschärft wurde — diesmal sitzt die Garantie im Code.
- Chefcoach bekommt eine neue, prominenteste Sektion „Urteil des Allgemeinmediziners" — stärker als der Sportmediziner, in der Praxis bekommt er `pause` aber nie zu Gesicht, weil der Orchestrator dann längst selbst entschieden hat.
- Krankennotiz in `POST /api/tp/apply` erweitert: Fieber ≥ 38 °C löst sie jetzt auch allein aus, unabhängig von der Symptome-Pille — eigene, konservative Schwelle ohne LLM-Beteiligung, absichtlich niedriger als der Agenten-Pause-Wert (38.5 °C), da eine überflüssige Notiz weniger schadet als ein übersehenes Fieber.
- Ernährungsberater (Ernährung als weiterer möglicher Spezialist) war zu diesem Zeitpunkt bewusst noch nicht Teil der Änderung — siehe v2.7.8.

Tests: `test_offline.py`/`test_wiring.py` prüfen das neue Schema, dass der Sportmediziner keine Krankheits-Referenz mehr sieht (Migrations-Regression), und vor allem, dass `pause` wirklich Chefcoach und Architekt überspringt und jede Sportart auf SKIP zwingt.

### v2.7.6 — Persistenter Zustand + MCP aus dem Internet

**1. Railway-Volume (`DATA_DIR`).** Railway-Container haben ein flüchtiges Dateisystem: jeder Deploy startet einen neuen Container, und alles Geschriebene ist weg. Damit verlor die App bei jedem Deploy still `sleep_history.json`, über den Profil-Tab geänderte `athlete.json` und eine neu berechnete `baseline.json` — das Ziel von v2.6.25 (Schlafverlauf geräteübergreifend) war faktisch nie erfüllt.

- Alle drei Zustandsdateien liegen jetzt unter **`DATA_DIR`** (Default = Repo-Verzeichnis, lokal ändert sich nichts).
- **Seeding beim Start:** fehlt eine Datei im Volume, wird sie einmalig aus dem Repo kopiert. Ohne das hätte ein frisches Volume kein Athletenprofil und `load_athlete()` würde beim ersten Request fehlschlagen. Beim zweiten Start wird **nicht** erneut geseedet — sonst würden Änderungen überschrieben.
- `GET /api/version` liefert einen `storage`-Block (`dir`, `persistent`, `writable`, `seeded`, `error`). **`persistent: false` heißt: Volume fehlt.** Gleiche Idee wie der `agents`-Block aus v2.7.3.

Railway-Setup: Service → *Volumes* → Mount auf `/data`, dann `DATA_DIR=/data` setzen.

**2. MCP-Server aus dem Internet erreichbar.** `coach_mcp.py` kann jetzt beides, mit **denselben Tools**:

| Modus | Wann | Schutz |
|---|---|---|
| `stdio` (Default) | lokal auf dem Mac | keine offene Fläche |
| `MCP_TRANSPORT=http` | Railway-Service, weltweit | Bearer-Token (`MCP_TOKEN`) |

- **Ohne `MCP_TOKEN` (min. 32 Zeichen) startet der HTTP-Modus nicht.** Ein offener MCP-Server würde Gesundheitsdaten preisgeben und über `coach_frage` den Anthropic-Key verbrennen. Token-Vergleich über `secrets.compare_digest`.
- `/health` bleibt ohne Token erreichbar (Railway-Healthcheck), verrät aber nichts.
- Auth als **rohes ASGI-Wrapper**, nicht als Starlette-Middleware — unabhängig davon, welche starlette-Version `mcp` gerade mitbringt.
- `stateless_http=True`: jeder Request steht für sich, robuster hinter dem Railway-Proxy.

**Eigener Service, eigenes Image (`Dockerfile.mcp`).** `mcp` verlangt `starlette>=0.49`, `fastapi 0.111` erlaubt `<0.38`. Ein gemeinsames Image würde einen FastAPI-Sprung in der App erzwingen — geprüft, `fastapi 0.140` funktioniert, aber die App entscheidet morgens um 6 über echtes Training, also bleibt sie unangetastet. Zweiter Service = Abschalten ist ein Klick. In Railway: gleiches Repo, `RAILWAY_DOCKERFILE_PATH=Dockerfile.mcp`.

Anbinden nach dem Deploy:
```
claude mcp add -s user ki-coach-remote --transport http \
  https://<mcp-service>.up.railway.app/mcp --header "Authorization: Bearer <MCP_TOKEN>"
```
Claude Desktop über `mcp-remote` (wie beim TrainingPeaks-MCP), zusätzliche args: `--header "Authorization: Bearer <MCP_TOKEN>"`.

**Weiterhin nur lesend** — kein `tp/apply` über MCP.

### v2.7.5 — Der Coach ist aus Claude Desktop und Claude Code abfragbar
Ein MCP-Server macht die App außerhalb der PWA nutzbar. **`coach_mcp.py` läuft lokal auf dem Mac über stdio** und spricht die Railway-App per HTTPS an — bewusst *nicht* als Endpoint in `app.py`: ein öffentlicher MCP-Server wäre eine zweite ungesicherte Angriffsfläche, solange es kein Auth gibt.

**Acht Tools, zwei Sorten:**
- **Datentools** — `training(tag)` · `belastung()` · `erholung()` · `wetter(tag)` · `profil()` · `einheiten_historie(tage)` · `app_status()`. Liefern Rohdaten; das Modell in Desktop/Code denkt selbst darüber nach und ist stärker als das Haiku hinter dem App-Chat.
- **`coach_frage(frage)`** — fragt den Coach der App selbst, mit dem getunten Sportmediziner-Prompt. Jeder Aufruf steht für sich (keine Historie), nötiger Kontext gehört in den Fragetext.

Die Tool-Beschreibungen tragen die Auslegungsregeln mit: `erholung` warnt explizit, dass **Schlafdauer kein Entscheidungsfaktor** ist, `belastung` nennt die TSB- und Ramp-Rate-Schwellen. Ohne das würde ein Modell ohne Projektkontext falsche Schlüsse ziehen.

**Neu im Backend:** `GET /api/load` legt CTL/ATL/TSB offen — bisher lief das nur intern zum Periodisierer. Ohne TP liefert es `{"available": false}` statt zu failen.

**Kein `mcp` in `requirements.txt`.** Das Paket zieht ein neueres `starlette` nach, als `fastapi 0.111` erlaubt — es in den Railway-Build zu legen würde die App brechen. Deshalb `requirements-mcp.txt` und ein eigenes venv `.venv-mcp` (gitignored). Der Wiring-Test importiert `coach_mcp` bewusst nicht und prüft nur die Quelle.

**Nur lesend.** Keine Schreibzugriffe auf TrainingPeaks über MCP — `tp/apply` bleibt der PWA vorbehalten.

Einrichten:
```
python3 -m venv .venv-mcp && .venv-mcp/bin/pip install -r requirements-mcp.txt
claude mcp add -s user ki-coach -- <abs>/.venv-mcp/bin/python <abs>/coach_mcp.py
```
Claude Desktop: Eintrag unter `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json` (`command` = venv-Python, `args` = `[coach_mcp.py]`), danach Desktop neu starten. Andere App-URL → `COACH_URL` setzen.

### v2.7.4 — Checks laufen als Hintergrund-Job
Die Agent-Pipeline braucht 11–19 s. Ein so lange offener Request überlebt weder Proxy-Timeouts noch wechselnden Mobilfunk — dieselbe Begründung wie beim Analyse-Tab in v2.6.5.

- **`POST /api/check-abend` / `check-morgen`** antworten jetzt in ~20 ms mit `{"job_id": …}`. Der Check läuft als Hintergrund-Task, das Frontend pollt `GET /api/check/{job_id}` alle 1,2 s. **Am Ergebnis-JSON ändert sich nichts** — `showResult` und `applyToTP` bekommen dasselbe wie vorher.
- **Fortschrittsanzeige.** `run_check` nimmt einen `progress`-Callback und meldet vor jeder Stufe einen Schlüssel aus `orchestrator.STUFEN` (`spezialisten` → `chefcoach` → `architekt`, letzteres nur wenn es MOD-Einheiten gibt). Der Job trägt ihn als `stage`, das Frontend zeigt den Text aus `translations.py` (`stage_*`). Der Orchestrator kennt weiterhin keine UI-Texte.
- **Der Monolith-Pfad läuft jetzt über `asyncio.to_thread`.** `call_claude` ist synchron und hätte im Hintergrundtask den Event-Loop und damit das Polling blockiert. Vorher fiel das nicht auf, weil der Request ohnehin wartete.
- **Zwei Fallstricke, bewusst behandelt:** die CSV des Morgen-Checks wird noch im Request gelesen (im Task wäre der Stream zu), und laufende Tasks liegen in `_check_tasks` — `asyncio` hält nur schwache Referenzen, der GC dürfte einen laufenden Check sonst einsammeln.
- **Jobs sind prozesslokal** (`_check_jobs`, TTL 15 min). Ein Railway-Neustart verliert sie; das Polling bekommt dann 404 und bricht mit klarer Meldung ab statt ewig zu drehen. Dazu ein Deckel von 5 min im Frontend.

Keine Verhaltensänderung an den Urteilen. Die Wartezeit wird **nicht kürzer** — sie ist nur nicht mehr an einen offenen Request gebunden und sichtbar belegt.

### v2.7.3 — Läuft die Pipeline? Ohne Logs beantwortbar
Nach dem Aktivieren von `COACH_AGENTS=1` in Railway war nicht feststellbar, ob die Pipeline wirklich läuft — der Fallback auf den Monolith ist absichtlich still und schreibt nur ins Log. Zwei Diagnosepunkte in der App selbst:

- **`GET /api/version`** liefert jetzt einen `agents`-Block: `importable`, `enabled`, `env` (Rohwert von `COACH_AGENTS`), `import_error`, `anthropic_version`. Die drei Zustände haben verschiedene Ursachen: `importable: false` = Deploy kaputt (meist `anthropic < 0.120.0`, das `output_config` braucht), `enabled: false` bei `importable: true` = ENV fehlt. Im **About-Tab** steht das im Klartext.
- **`_pipeline`** (`agents` | `monolith`) hängt jetzt an *jeder* Antwort — Abend, Morgen, Chat, Analyse. Vorher setzten nur die Agent-Pfade das Feld, ein Fallback war von außen nicht von „ENV aus" zu unterscheiden. Unter der Dark Card und unter dem Coach-Urteil steht dazu eine Punkt-Zeile (grün = Agents, orange = Monolith).

Keine Verhaltensänderung an den Checks. Der Wiring-Test prüft beide Zustände von `agents_status()`, das Monolith-Marking in allen vier Pfaden und die Frontend-Anzeige.

### v2.7.2 — Zwei Prompt-Fehler aus dem ersten Live-Test
Erster Lauf gegen die echte API: 8 von 9 Fixtures grün, zwei inhaltliche Fehler gefunden, die offline unsichtbar waren.

- **Krankheit wurde nur auf Schwimmen angewendet.** Bei „neu mittel" (plus HRV 26, WachBPM 62, Müdigkeit 4/5) lieferte der Mediziner `eingeschraenkt` statt `pause` und für Rad/Laufen nur `kein_tempo` — der Chefcoach hätte einen kranken Athleten auf 60 min Rad geschickt. Ursache: der Prompt nannte Schwimmen bei „neu leicht" explizit und stiftete so das Muster „Krankheit betrifft Schwimmen". Jetzt ist Krankheit ein Ganzkörper-Befund, der zuerst geprüft wird und die sportartspezifische Logik überschreibt; bei `pause` muss jede Sportart `stop` tragen.
- **Falscher Rechenwert im Wetter-Prompt.** „Pro Grad über 20 °C etwa 4–5 % langsamere Pace" ist als lineare Regel falsch — das Modell rechnete korrekt 4,5 % × 11 Grad = 44–55 % Pace-Verlust. Ersetzt durch eine Gesamtverlust-Orientierung (25 °C ≈ 2–3 %, 30 °C ≈ 4–6 %, 35 °C ≈ 8–10 %) plus explizites Hochrechnen-Verbot.
- **Schwimmen ist jetzt eindeutig hitze-ausgenommen.** Der Taktiker hatte eine Schwimmeinheit wegen Mittagshitze in ein Zeitfenster verlegt. Zeitfenster oder Indoor-Wechsel beim Schwimmen nur noch bei Gewitter oder zu kaltem Wasser.

**Wichtig für künftige Prompt-Arbeit:** die Urteile sind nicht deterministisch. Derselbe Hitze-Fall war grün, dann rot, dann dreimal grün. Ein einzelner Durchlauf beweist nichts — kritische Fixtures mehrfach fahren.

### v2.7.1 — Analyst und Chat (Agent-Architektur vollständig)
Die letzten beiden Claude-Aufrufe wandern in die Architektur. Sechs Agents, alle hinter `COACH_AGENTS`.

- **Performance-Analyst** (`agents/analyst.py`) — ersetzt `_run_analysis_job_fast`. Dort machte ein JSON-Parse-Fehler stillschweigend `{"bewertung": "ok", "urteil": <Rohtext>}` daraus — der Athlet sah ein Urteil, das keines war. Mit erzwungenem Schema unmöglich; ein Fehler schlägt jetzt sichtbar fehl. Neu: Feld `datenlage` (fit / tp_ist / nur_plan) und die Belastungslage des Trainingstags als Kontext — dieselbe Einheit bei TSB −28 liest sich anders als bei TSB +5.
- **Coach-Chat** (`agents/chat.py`) — der einzige Agent **ohne** Schema, weil die Antwort direkt an den Athleten geht (`call_agent_text` in `base.py`). Bekommt jetzt zusätzlich CTL/ATL/TSB.
- **Bugfix:** `tomorrow_str` war im Chat-Pfad nie definiert. Der `NameError` landete im `except` und der Chat bekam **seit v2.6.35 immer** „Wetterdaten nicht verfügbar" — er hatte nie Wetter. Behoben in beiden Pfaden, mit Regressionstest.

### v2.7.0 — Periodisierer (Stufe 4)
Die App denkt erstmals in Wochen statt nur in Tagen.

- **`training_load.py`** rechnet CTL/ATL/TSB aus der TSS-Historie (42 Tage `completed` aus TP). Der MCP liefert kein fertiges PMC, aber `tssActual` pro Workout reicht für die Standardformeln. Deterministisch — ein Modell könnte hier nur Zahlen halluzinieren. Zusätzlich: Ramp Rate, 7d/28d-TSS, Wochenstruktur, Tage bis A-Rennen.
- **Periodisierer** (`agents/periodizer.py`) — liest Kennzahlen, Wochenplan und Renndatum und liefert `phase` (grundlage/aufbau/spitze/taper/wettkampfwoche/erholung), `heute_rolle` (schluesseleinheit/unterstuetzung/erholung/ruhetag/wettkampf), `belastungsurteil`, `spielraum` und optional eine `warnung`. Läuft **parallel** zu Mediziner und Wetter.
- **Chefcoach** wägt damit anders ab: eine `schluesseleinheit` wird bei nur `reduziert` gerettet statt gestrichen, eine `unterstuetzung` darf großzügig fallen, bei `zuruecknehmen` greift er das auf, auch wenn Körper und Wetter unauffällig sind. Rangfolge bleibt: **Mediziner schlägt Periodisierer** — Form lässt sich nachholen, eine Achillessehne nicht.
- **Ohne TP-Daten läuft alles weiter** — der Periodisierer wird dann gar nicht erst aufgerufen und der Chefcoach bekommt `block=None` statt erfundener Zahlen. Belastungsdaten sind 6 h gecacht.

### v2.6.99 — Workout-Architekt (Stufe 3)
Der Chefcoach entscheidet nur noch, das Ausformulieren übernimmt ein eigener Agent.

- **Workout-Architekt** (`agents/architect.py`) — bekommt einen strukturierten Auftrag (`dauer_min`, `zone`, `kein_tempo`, `indoor`, `sportwechsel`, `hinweis`) und schreibt daraus Beschreibung, `tp_struktur` und `distanz_m`. Läuft **nur bei MOD**, alle MOD-Einheiten parallel.
- **Chefcoach** liefert statt Fließtext ein Feld `anpassung` + `begruendung`. Keine Formulierungsregeln mehr im Prompt (64 → 45 Zeilen).
- **Zwei Fälle brauchen kein Modell mehr:** GO übernimmt die Original-Beschreibung zeichengenau per Code (vorher eine Prompt-Anweisung, die verletzt werden konnte — vgl. v2.6.13/.71), SKIP bekommt gar keine.
- **Ernährung ist deterministisch** — `nutrition.py`, Tabellenlookup nach der *fertigen* Dauer. Vorher schrieb das Modell die Mengen.
- Den Frontend-Vertrag baut jetzt der Orchestrator zusammen; für `index.html` und `applyToTP` ändert sich nichts.

### v2.6.98 — Agent-Architektur (Stufe 1+2)
Der Monolith-Prompt wird durch typisierte Spezialisten ersetzt. **Hinter `COACH_AGENTS`, Default aus.**

- **Sportmediziner** (`agents/medic.py`) — beurteilt nur Körpersignale, liefert pro Sportart `frei`/`reduziert`/`kein_tempo`/`stop`
- **Wetter-Taktiker** (`agents/weather.py`) — liefert pro Sportart `outdoor_ok`/`zeitfenster`/`indoor_wechsel`/`gestrichen`
- **Chefcoach** (`agents/head_coach.py`) — synthetisiert beide Urteile zur Entscheidung, sieht keine Rohwerte mehr
- **Orchestrator** — Mediziner und Wetter laufen parallel (`asyncio.gather`), dann der Chefcoach. Agents reden nicht miteinander.
- **Structured Outputs** (`output_config`) erzwingen das JSON-Schema hart → `_extract_json` ist für diese Agents überflüssig, die Bug-Klasse aus v2.6.21/.37/.73/.74 entfällt
- Prompts sind statische Markdown-Dateien ohne `.format()`-Platzhalter (kein Escaping-Risiko mehr wie v2.6.41); Athletendaten gehen in die User-Message
- Fallback: schlägt die Pipeline fehl, übernimmt automatisch der Monolith-Prompt. Ein Agent-Fehler blockiert den Morgen-Check nie.
- `anthropic` auf `>=0.120.0` (für `output_config`)
- Tests: `test_offline.py` (Schemas + Frontend-Vertrag), `test_wiring.py` (Verdrahtung mit Attrappen), `test_live.py` (5 Fixtures gegen die echte API)

### v2.6.97 — Repo-Hygiene
`.gitignore` erweitert (`__pycache__/`, `*.py[cod]`, `.DS_Store`, `railway.log.json`, `*.log`), eingecheckte `.pyc` aus dem Index entfernt.

### v2.6.96 — Doku
CLAUDE.md aus Code + Commit-History neu aufgebaut (stand noch auf v2.1.0). Korrigiert: Modelle (Haiku für Checks, Sonnet nur für FIT-Analyse), Wetter-Provider (wttr.in statt Open-Meteo für Prognose), Hitze 28°C / Kälte <0°C, 7 statt 3 Tabs, Rennen aus TP-Events. Entfernt: die starren Schmerzschwellen, die seit v2.4.32 nicht mehr im Prompt stehen.

---

## Offene Punkte

### Public Release (GitHub, Self-hosted Single-User) — noch nicht begonnen
1. Personal Data raus: `athlete.json` → Template, `setup_complete`-Flag, About-Tab dynamisch
2. **Auth: Google OAuth 2.0** (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS`) — PIN war zu schwach, aktuell gibt es **keinen** Schutz
2b. TP-Cookie-Extractor-Script (`rookiepy`) für Enduser
3. Onboarding-Wizard bei `setup_complete: false`
4. README + „Deploy on Railway"-Button

### MyFitnessPal MCP — explizit auf „später"
MFP MCP auf Railway (`MFP_USERNAME`/`MFP_PASSWORD`), Kalorienbilanz im Abend-Check gegen Trainingsverbrauch.

### Sicherheit — der MCP-Token schützt nicht die App
Der MCP-Service hat seit v2.7.6 einen Bearer-Token. **Die App selbst hat weiterhin keinen.** Wer die App-URL kennt, kann `POST /api/coach/chat` direkt aufrufen und damit denselben Anthropic-Key verbrennen und dieselben Daten lesen — der MCP-Token ist also nicht die schwächste Stelle, sondern die App. Das bleibt der Google-OAuth-Punkt unten. Der Token liegt außerdem im Klartext in `~/.claude.json` bzw. der Claude-Desktop-Config.

### Technische Altlasten
- `build_pain_rules()` gibt `""` zurück → `pain_thresholds` in `athlete.json` ist ungenutzt
- `_run_analysis_job()` (MCP-Pfad der Analyse) ist definiert, wird aber nie aufgerufen — nur `_run_analysis_job_fast()` läuft
- `CLAUDE_14.md` ist eingecheckt, aber veraltet (Vorgängerspec)
