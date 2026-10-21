# KI Coach App — v3.0.0

## Ziel
iPhone-optimierte Progressive Web App (PWA) für den täglichen Triathlon-Coaching-Workflow von Hendrik Sprejz (Castle Triathlon Malbork, 6.9.2026, Zielzeit 10:50h).

## Architektur
- **Backend:** Python FastAPI (`app.py`, ein File)
- **Frontend:** Single HTML-Datei mit Jinja2-Templating (`templates/index.html`), mobile-first (320–390px) mit Desktop-Breakpoint ab 1024px (v2.8.0)
- **i18n:** alle UI-Texte *und* alle Claude-Prompts in `translations.py` (`de` / `en`), Sprache über `APP_LANG`
- **Hosting:** Railway (Docker)
- **Claude-Modelle:**
  - `claude-haiku-4-5-20251001` → Abend-Check, Morgen-Check, Coach-Chat, TP-MCP-Calls über Claude
  - `claude-sonnet-4-6` → Workout-Analyse (braucht Reasoning über FIT-Daten)
- **Wetter:**
  - Prognose heute/morgen → **Open-Meteo** (seit v2.7.27 Primärquelle), **wttr.in** nur noch als Rückfall; beide durchlaufen eine Plausibilitätsprüfung
  - Vergangene Tage → **Open-Meteo** Forecast-API mit `past_days=7`
  - Stündliches Workout-Fenster → **Open-Meteo Archive-API**
- **TrainingPeaks:** eigener MCP-Server auf Railway, angesprochen per **direktem JSON-RPC** (`call_tp_mcp`, SSE-Parsing). Der Umweg über den Claude-MCP-Connector ist in v2.7.18 entfallen — er hatte keinen Aufrufer mehr.

## Umgebungsvariablen (Railway)
- `ANTHROPIC_API_KEY` — Claude API Key (Pflicht)
- `TP_MCP_URL` — TrainingPeaks MCP: `https://trainingpeaks-mcp-production-1a4f.up.railway.app/mcp` (optional; ohne → TP-Endpoints liefern `{"available": false}` bzw. HTTP 400)
- `APP_LANG` — `de` (Default) oder `en`
- `COACH_AGENTS` — `1`/`true`/`on` aktiviert die Agent-Pipeline. **Default aus** → Monolith-Prompt
- `DATA_DIR` — Verzeichnis für schreibbaren Zustand (`athlete.json`, `baseline.json`, `sleep_history.json`, `strava_token.json`). **Auf Railway `/data` mit gemountetem Volume**, sonst ist nach jedem Deploy alles weg. Ohne die Variable = Repo-Verzeichnis (lokal)
- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` — Strava-API-App (optional; ohne → Analyse-Tab bleibt beim manuellen FIT-Upload wie bisher)
- `STRAVA_REFRESH_TOKEN` — einmaliger Seed aus der manuellen OAuth-Autorisierung (siehe „Workout-Analyse"). Die App verwaltet danach ihren eigenen, aktuellen Stand in `DATA_DIR/strava_token.json` — Strava tauscht das Refresh-Token bei jedem Refresh potenziell aus
- `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` — Webshare-Proxy-Zugangsdaten (optional; ohne → `POST /api/research/video` liefert `err_video_not_configured`, alles andere bleibt unberührt). Nötig, weil YouTube Transkript-Abrufe von Cloud-Server-IPs (Railway, AWS, GCP, …) grundsätzlich anhand der ASN blockieren kann. **Live getestet (v2.9.2): das kostenlose Webshare-Kontingent (10 IPs) hat gereicht** — kein bezahlter „Residential"-Plan zwingend nötig, entgegen der ursprünglichen Annahme beim Bau dieses Features. Reicht das Gratis-Kontingent künftig nicht mehr (IPs erschöpft/gesperrt), ist ein bezahlter Plan die Rückfalloption — dann ausdrücklich „Residential", nicht „Proxy Server"/Datacenter oder „Static Residential", da beide dieselbe Cloud-IP-Blockade träfe.
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
├── CLAUDE.md            ← diese Datei (v2.7.29)
├── app.py               ← FastAPI Backend (~2200 Zeilen)
├── coach_mcp.py         ← MCP-Server für Claude Desktop + Code (stdio lokal / HTTP remote)
├── requirements-mcp.txt ← nur für coach_mcp.py, eigenes venv (.venv-mcp)
├── Dockerfile.mcp       ← Image des MCP-Service (zweiter Railway-Service)
├── orchestrator.py      ← Kontrollfluss der Agent-Pipeline
├── nutrition.py         ← Ernährungstabelle (deterministisch, von beiden Pfaden genutzt)
├── training_load.py     ← CTL/ATL/TSB aus der TSS-Historie (deterministisch)
├── strava.py            ← Strava-Auto-Match für die Analyse (OAuth direkt per httpx, kein MCP)
├── knowledge.py         ← Wissensdatenbank für Recherche-Funde (deterministisch, kein File-I/O, seit v2.9.0)
├── youtube.py           ← YouTube-Transkript-Abruf für Video-Recherche (Webshare-Residential-Proxy, seit v2.9.2)
├── agents/              ← base, medic, allgemeinmedic, weather, periodizer, head_coach, architect, architect_run, architect_bike, architect_swim, fueling, analyst_run, analyst_bike, analyst_swim, chat, research (je eigener Ordner, seit v2.7.12; Prompt-.md direkt daneben statt zentral, seit v2.7.13; Analyst-Disziplin-Split seit v2.7.28, generischer Analyst-Fallback entfernt seit v2.7.29 — anders als beim Architekten braucht die Analyse keinen; research seit v2.9.0, einziger Agent mit serverseitigem web_search-Tool, seit v2.9.2 auch `run_video()` für Podcast-/Vlog-Transkripte)
├── tests/               ← fixtures.py, test_offline.py, test_wiring.py, test_live.py
├── translations.py      ← UI-Texte + Monolith-Prompts (de/en)
├── templates/
│   └── index.html       ← Frontend, 7 Tabs
├── athlete.json         ← Athletenprofil (über Profil-Tab editierbar)
├── baseline.json        ← Schlaf-Baseline (über Profil-Tab berechenbar)
├── sleep_history.json   ← letzte 14 AutoSleep-Nächte (serverseitig)
├── knowledge.json       ← Recherche-Funde: Vorschlag/akzeptiert/abgelehnt (serverseitig, seit v2.9.0)
├── Dockerfile
├── railway.toml
└── requirements.txt     ← fastapi, uvicorn, httpx, anthropic>=0.120, jinja2, fitdecode, youtube-transcript-api
```

---

## Tabs (Reihenfolge im Frontend)
1. **Morgen** — Morgen-Override (Go/No-Go vor dem Training)
2. **Abend** — Abend-Check (plant den nächsten Tag)
3. **Fueling** — Ernährung für heute und morgen, pro Einheit aufklappbar (v2.7.21)
4. **Analyse** — abgeschlossene Einheiten der letzten 5 Tage bewerten lassen
5. **Erholung** — Erholungs-Index, HRV-Verlauf, Marker-Status
6. **Chat** — freier Coach-Chat mit TP- und Wetterkontext
7. **Recherche** — Themen-/Video-Recherche, Fundliste zur Prüfung (eigener Tab seit v2.9.3, vorher Teil von Profil)
8. **Profil** — Athletendaten, Rennen, Baseline-Manager, Info (Version, Pipeline-Status)

**Tab-Leiste scrollt horizontal (v2.9.3).** Acht Tabs bei 11px Schrift auf 320-390px Breite hätten mit der alten `flex:1`-Gleichverteilung wieder Labels abgeschnitten (dasselbe Problem, das v2.7.21/22 durch Tab-Entfernen gelöst hatte). Jetzt: `.tabs { overflow-x: auto }`, Buttons behalten ihre natürliche Breite (`flex: 0 0 auto`) — ein Tap scrollt den Button per `scrollIntoView` vollständig ins Bild. Löst das Problem strukturell, ein künftiger neunter Tab gefährdet keine bestehenden Labels mehr.

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

**Wichtig:** Seit v2.4.31–v2.4.33 arbeitet der Prompt **nicht mehr mit starren Zahlenschwellen**, sondern mit sportmedizinischem Reasoning. `pain_thresholds` in `athlete.json` fließt **nicht** in den Prompt — die dafür gebaute `build_pain_rules()` gab `""` zurück und ist in v2.7.18 entfallen. Die Werte bleiben trotzdem im Profil: `buildModReason()` im Frontend leitet daraus den MOD-Grund für TrainingPeaks ab.

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
1. **Datenquelle bestimmen** (v2.7.9), Priorität: hochgeladene FIT-Datei (bewusste Nutzerentscheidung, gewinnt immer) → **Strava-Auto-Match** → nur TP-Ist/-Plan. FIT-Datei sofort mit **fitdecode** parsen (v2.6.90 — `fitparse` verstand neuere Garmin-Protokolle nicht): Dauer, Distanz, Ø/Max Power, NP, Ø/Max HF, Kadenz, Pace, TSS, Arbeit + bis zu 20 Laps. Ohne Upload versucht `strava.py` per Datum+Sportart die passende Strava-Aktivität zu finden und in **dieselbe Dict-Form** zu bringen — der Analyst sieht keinen Unterschied zwischen FIT-Upload und Strava-Treffer, beides sind echte Gerätemesswerte. Ohne `STRAVA_CLIENT_ID` oder ohne Treffer bleibt alles wie vor v2.7.9.
2. Archiv-Wetter für das konkrete Workout-Zeitfenster (Priorität: TP-Startzeit → FIT-Startzeit → Tagesfallback)
3. TP-Workout direkt per MCP holen
4. Prompt bauen: unterscheidet **Ist-Daten** (`tssActual`, HF, Pace, `perceivedExertion`/RPE …) von reinen **Plan-Daten** und weist Claude an, auch ohne Ist-Werte zu bewerten (v2.6.94)
5. Job-Queue: Thread + `job_id`, Frontend pollt `GET /api/workout/analyze/{job_id}` (v2.6.5 — direkter Call lief in 60s-Timeouts)
6. **Disziplin-Dispatch, kein generischer Fallback** (v2.7.28/v2.7.29): `app._ANALYST_BY_SPORT` schickt Lauf/Rad/Schwimmen an `agents/analyst_run`/`_bike`/`_swim` — denselben Coach, der die Einheit auch anpasst (Finn Adler/Nils Brandt/Pia König aus `T["agenten"]`). Andere Sportarten lehnt der Endpoint mit HTTP 400 ab, statt still auf einen generischen Analysten zu fallen — der Analyse-Tab bietet im Frontend ohnehin nur diese drei Sportarten zur Auswahl an (SPORT_OK-Filter in `templates/index.html`).

Antwort-JSON: `{"bewertung":"gut|ok|verbesserungsbedarf","urteil":"…","naechster_schritt":"…","ernaehrung_einschaetzung":"…","quelle":"fit_upload|strava|null","analyst_agent":"architect_run|architect_bike|architect_swim"}`
Prompt-Leitlinie: keine erfundenen Kritikpunkte, echte Zahlen statt Floskeln (v2.6.91).

`ernaehrung_einschaetzung` (v2.7.8) — Einschätzung, ob die Verpflegung zur Dauer/Intensität passte (Splits/HF-Drift, RPE, Dauer gegen die Tabellen-Basis aus `nutrition_for_duration()`), leer wenn die Datenlage nicht reicht. Erfindet keine eigenen Gramm-/ml-Zahlen — die kommen als `ernaehrung_basis` fertig berechnet in den Prompt.

### Strava-Integration (v2.7.9)
`strava.py` — kein eigener MCP-Service wie bei TrainingPeaks, sondern direkte `httpx`-Calls (Stravas REST-API ist dafür einfach genug), analog zur Wetter-Anbindung. Strava-Werte laufen als derselbe `fit`-Parameter durch die bestehende Analyst-Logik.

- **Auth:** OAuth2 mit Refresh-Token. Einmalige Browser-Autorisierung (`https://www.strava.com/oauth/authorize?...&redirect_uri=http://localhost&scope=activity:read_all`, Code aus der (absichtlich fehlschlagenden) Redirect-URL kopieren, gegen Tokens tauschen) liefert den initialen `STRAVA_REFRESH_TOKEN`. Danach verwaltet die App ihren eigenen, aktuellen Stand in `DATA_DIR/strava_token.json` — bewusst **nicht** in `_STATE_FILES` (`app.py`), damit diese Secret-Datei nie aus dem Repo geseedet wird.
- **Matching:** Aktivitäten des Zieldatums (±1 Tag Zeitzonen-Puffer) nach Sportart-Gruppe gefiltert (`Run`/`Bike`/`Swim`). Bei mehreren Kandidaten zählt die Abweichung zur TP-Startzeit **und/oder** zur geplanten TP-Dauer (`totalTimePlanned`), je nachdem was vorhanden ist — bei diesem Account kennt TP fast nie eine Startzeit, aber oft zwei separate Einheiten am selben Tag (z.B. Hin-/Rückfahrt), die nur über die Dauer zu unterscheiden sind. Ganz ohne Signal: die längste Aktivität, als letzte ehrliche Notlösung.

**Nebenbefund beim Live-Testen — TP-Feldnamen in `agents/analyst.py` waren falsch.** `_TP_LABELS` las TPs eigene camelCase-API-Namen (`totalTime`, `tssActual`, `averageHeartRateInBeatsPerMinute`, …), aber `tp_get_workout` (der MCP-Server) liefert tatsächlich snake_case, größtenteils unter `metrics` verschachtelt (`metrics.tss_actual`, `metrics.avg_hr`, `rpe`/`feeling` auf oberster Ebene). Nur `description` traf zufällig — der Analyst bekam bei **jeder** Analyse (nicht nur Strava-Fällen) praktisch keine TP-Zahlen zu Gesicht, unabhängig von der Datenquelle. Korrigiert auf die echten Feldnamen; zusätzlich wird jetzt `structured_workout.structure` gerendert (Ziel-Pace/-Watt pro Schritt und Wiederholung, aus `primaryIntensityMetric` + Athleten-Schwellen berechnet) — ein Titel wie „3x16 min" verrät nicht, dass das intern 4× (1 min hart / 3 min locker) sein kann, die echte Struktur schon.
- **Datenquelle nie erfunden:** ohne Treffer, ohne Credentials oder bei einem Fehler (abgelaufenes Token, Netzwerk) fällt die Analyse lautlos auf den bisherigen Ablauf zurück (TP-Ist/-Plan) — blockiert nie.

---

## Coach-Chat (`POST /api/coach/chat`)
Freier Text, kein JSON. Kontext:
- System-Prompt mit Athletenprofil + Baseline
- TP-Workouts für **heute, morgen** und jeden im Text erwähnten Wochentag (bis 30 Tage voraus, `übermorgen` erkannt) — aus dem Cache
- Wetter heute + morgen
- **Ernährungstabelle + chronische Befunde** (v2.7.8) — Mix, Carbs/Flüssigkeit/Salz pro Stunde, die Dauer-Regeln aus `athlete.json` → `nutrition`, damit Ernährungsfragen mit echten Zahlen statt Rateversuchen beantwortet werden. Vorher fehlte das im Agent-Pfad komplett (der Monolith-Fallback hatte es schon).
- letzte 10 Nachrichten der Historie

Fehlt TP im Cache, wird ein Hintergrund-Refresh gestartet und Claude sagt dem Nutzer, dass die Daten in ~1 Minute da sind (v2.6.32). `max_tokens=1200`.

**Chat kann TP-Änderungen vorschlagen (v2.8.1, seit v2.8.3 auch Streichen, seit v2.9.1 auch neue Einheiten/Serien), nie direkt ausführen.** Nur im Agent-Pfad (`agents_enabled()`): Claude bekommt vier Anthropic-Tools (`propose_workout_update` — Titel/Beschreibung einer bestehenden Einheit, `propose_calendar_note` — neue Kalendernotiz, `propose_workout_skip` — Einheit streichen, dieselbe ❌-Titel-Konvention wie SKIP im Check, kein echtes Löschen, `propose_workout_series` — eine oder mehrere NEUE Einheiten anlegen, seit v2.9.1; `agents/chat/chat.py` → `CHAT_TOOLS`). Ruft es eins auf, wird **nichts ausgeführt** — der Server löst `date`+`workout_hint` serverseitig gegen den `_tp_cache` zu einer echten `workout_id` auf (Claude sieht nie eine `workout_id` und soll auch nie eine raten), legt bei genau einem Treffer eine `pending action` an (`app.py` → `_pending_tp_actions`, TTL 30min) und gibt der Antwort ein `proposal`-Feld mit. Bei 0 oder >1 Treffern: keine pending action, sondern eine deterministische Rückfrage (kein zweiter Claude-Call). Das Frontend zeigt eine Karte mit dem **tatsächlich gematchten** Titel/Sportart — das ist der eigentliche Sicherheits-Backstop, nicht die Matching-Logik. Erst ein Klick auf „Übernehmen" (`POST /api/chat/tp-action/{pending_id}/confirm`, pop-before-execute) ruft `call_tp_mcp` mit denselben Parametern auf, die `tp_apply` auch nutzt (`propose_workout_series` → 1..N `tp_create_workout`-Aufrufe, jeder mit eigenem ✓/✗-Status, kein Alles-oder-nichts); „Verwerfen" (`.../cancel`) ist idempotent. Der Monolith-Fallback bekommt strukturell kein `tools=`, kann also nie einen Tool-Call erzeugen, unabhängig vom Prompt-Text. `propose_workout_series` verschiebt/ändert **keine** bestehende Einheit — nur Neuanlage, kein `structure`/`subtype_id` (keine Intervalle, dafür bleibt der Check zuständig).

**Chat kann seit v2.9.1 Fachkollegen konsultieren, lesend, ohne Bestätigung nötig.** Fünf weitere Tools (`consult_medic`, `consult_allgemeinmedic`, `consult_weather`, `consult_periodizer`, `consult_fueling`; `CONSULT_TOOLS`) lösen — anders als die `propose_*`-Tools — **sofort** einen echten Aufruf des jeweiligen Spezialisten aus (`app.py` → `_build_consult_executor`), weil sie nichts in TP schreiben und deshalb kein Klick nötig ist. Dafür reicht `call_agent_with_tools` (ein Anthropic-Call, kein Tool-Result-Loop) nicht — neue Funktion `agents/base.py` → `call_agent_with_consult`: Runde 1 sammelt alle Tool-Uses ein, führt bis zu `MAX_CONSULTS_PER_TURN` (=2) Consults über den Executor aus und spielt das Ergebnis als `tool_result` zurück, Runde 2 liefert die finale Textantwort (darf noch ein `propose_*`-Tool aufrufen). Kein Consult-Tool im Spiel → identisches Verhalten zu `call_agent_with_tools`, keine Mehrkosten. Ein gleichzeitig aufgerufenes `propose_*`-Tool wird in derselben Antwort **nicht** aufgelöst (`chat.md`: ein Tool pro Antwort) — die pending-action-Logik bleibt exklusiv in `app.py`, nicht in `base.py` dupliziert. `medic`/`allgemeinmedic` bekommen ihre Fragebogen-Werte direkt aus dem vom Modell befüllten Tool-Input (alle Felder optional, dieselbe Extraktion-aus-Fließtext-Fähigkeit wie bei `date`/`workout_hint`); `weather`/`periodizer` nutzen die im Chat ohnehin schon geladenen Daten (`woche` aus `_fetch_training_load` wird seither mitgenommen statt verworfen); `fueling` matcht wie die propose-Tools über `_match_tp_workouts`.

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
| `GET /api/nutrition` | Ernährung heute + morgen pro Einheit (deterministisch, kein Claude-Call) |
| `POST /api/research/run` · `GET /api/research/{job_id}` | Recherche-Agent starten + Polling (v2.9.0) |
| `POST /api/research/video` | Video-/Podcast-Transkript auswerten (Webshare-Proxy nötig), liefert dieselbe `job_id` wie `research/run` (v2.9.2) |
| `GET /api/knowledge` · `POST /api/knowledge/{id}/accept\|reject` | Recherche-Funde lesen/entscheiden (v2.9.0) |
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

**Gesamtmengen zum Selbstanmischen (v2.7.19).** Ab 90min (`carbs_during` in der Regel) hängt `nutrition_for_duration()` eine Zeile mit den absoluten Mengen für die **ganze** Einheit an: `🥤 Selbst anrühren für 2:45 h: 165 g Maltodextrin + 85 g Fruchtzucker (250 g Carbs) · 3 Saltstick · 1650 ml`. Das Verhältnis kommt aus `nutrition.mix_ratio` (explizit, **nicht** aus dem Freitext von `mix` geparst) — fehlt es, bleibt die Aufteilung weg statt geraten zu werden. Gerundet wird auf 5 g, und der zweite Zucker ist der Rest zur Gesamtmenge, damit die Teile exakt aufgehen. Bei Hitze rechnet die Zeile mit `salt_heat_per_hour`/`fluid_heat_per_hour_ml`; die Carbs bleiben gleich.

**Carbs pro Sportart (v2.7.19).** `nutrition.carbs_per_hour_by_sport` überschreibt die Basisrate je Disziplin — beim Laufen ist die Magenverträglichkeit geringer als auf dem Rad (aktuell **Laufen 60 g/h**, alles andere 90 g/h). Die Rate wird auch im Regeltext ersetzt, damit dort nicht weiter „90g Carbs/h" für eine Laufeinheit steht.

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

Ältere Versionen (v2.7.29 und älter, v1.0–v2.6.x) stehen in [`CHANGELOG.md`](CHANGELOG.md).

### v2.10.0 — Wissensbasis (RAG): Transkripte persistent speichern, Vektorsearch nutzen

Umstrukturierung der Recherche: statt einzelne Erkenntnisse zu speichern und später zu vergessen, wird eine persistente Vektor-Wissensbasis aufgebaut — Videos/Transkripte/Artikel werden einmalig gechankt und embeddet, dann bei Fragen relevante Stellen gesucht und mit Quelle/Zeitstempel zur Verfügung gestellt. Anfrage ohne Nachfrage möglich, da Open-Source-Komponenten (Chroma + fastembed) lokal auf dem Railway-Volume laufen.

- **`wissensbasis.py`** (neu, Blattmodul) — `WissensbasisStore` mit Chroma (PersistentClient auf `DATA_DIR/chroma`) + fastembed (lokal, ONNX, mehrsprachig: `paraphrase-multilingual-MiniLM-L12-v2`). `chunk_segments()` mit Overlap und Zeitstempel-Tracking, `add_source()` zum Hochladen (YouTube oder Text), `search()` für Vektorsearch, `list_sources()` / `delete_source()` für Verwaltung. Lazy Embedder-Loading (Modell nicht beim Start).

- **`youtube.py`** — neue Funktion `fetch_transcript_segments()` mit Zeitstempeln (ungekürzt, keine 60k-Zeichenbegrenzung wie die alte `fetch_transcript_and_title()`, die Längenkontrolle macht jetzt `wissensbasis.py`).

- **`app.py`** — fünf neue Endpoints + Job-Handler:
  - `POST /api/wissen/quelle` — YouTube-Link oder Text hochladen (Job starten, Embedding im Hintergrund)
  - `GET /api/wissen/quellen` — Quellen-Metadaten (Chunk-Zähler, Titel, Quelle)
  - `GET /api/wissen/quelle/{job_id}` — Job-Status abfragen (pending/done/error)
  - `POST /api/wissen/suche` — Frage stellen, Vektorsearch über alle Quellen, Top-5 Treffer mit Relevanz-Score
  - `DELETE /api/wissen/quelle/{source_id}` — Quelle + alle Chunks löschen
  
  `_get_wissensbasis_store()` für Lazy-Init, `_run_wissen_job_embed()` für Embedding-Jobs (fastembed ist synchron, läuft in `asyncio.to_thread`).

- **Chat-Integration** — neues `consult_wissen`-Tool in `CONSULT_TOOLS` (agents/chat/chat.py), searcht die Wissensbasis und gibt Top-3 Treffer mit Quelle + Zeitstempel zurück. Executor in `app.py` ruft `/api/wissen/suche` auf.

- **MCP-Tool** — `wissen_suche(frage)` in `coach_mcp.py` (dünner HTTP-Call, kein chromadb im MCP-Image nötig).

- **Frontend** (templates/index.html) — Quellen-Manager im Recherche-Tab: YouTube-Link eingeben, Text/Transkript paste, Quelle-Liste mit Löschen-Buttons. Job-Status-Polling renutzt existing `research-progress`-Animation.

- **`requirements.txt`** — `chromadb>=0.4.24`, `fastembed>=0.2.0`.

- **Tests** — Fake-Embedder + Fake-Chroma in `test_offline.py`, Endpoint-Checks in `test_wiring.py`.

**Architektur-Notiz:** RAG vs. Monolith-Prompt. Der alte Weg (v2.9.x): Podcast hochladen → Transkript kürzen → Claude denkt sich 5 Erkenntnisse aus → speichern → vergessen. Neuer Weg: einmalig chunken/embedden → persistent → bei jeder Frage nur relevante Stellen suchen (kein kostspieliger Claude-Call pro Frage, kein Kontext-Limit). Wissensbasis wächst, ohne dass der Check langsamer wird (Suche ist 0ms + Embedding-Kosten beim Upload, nicht beim Abruf).

**Open-Source-Wahl**: fastembed ist leicht, Chroma ist Produktions-bewährt, beide haben keine Zweit-Dependencies auf PyTorch/CUDA. Modell (~220MB) wird beim ersten Gebrauch nach `/data/models` gecacht; Container-FS ist flüchtig, daher der Volume. Deployment-Test fehlt noch (Abhängigkeits-Konflikte mit `fastapi==0.111` / `pydantic` theoretisch möglich, beim ersten Live-Run sichtbar).

### v2.9.3 — Recherche als eigener Tab, Fortschritts-Animation statt Button-Spinner
Nutzerwunsch nach v2.9.2: die Recherche sollte einen eigenen Menüpunkt statt im Profil-Tab zu stecken, und der Lade-Zustand während des 1-4-minütigen Laufs sollte auffälliger sein als der kleine Button-Spinner ("langweilige Animation").

- **Neuer Tab „Recherche"** (`data-tab="recherche"`/`data-panel="recherche"`) — das komplette Formular (Themen-Eingabe, YouTube-Link, Fundliste) ist unverändert aus dem Profil-Tab herausgelöst in ein eigenes Panel gewandert, zwischen Chat und Profil. `initTabs()`s Lazy-Load-Bedingung (`loadKnowledge()`) ist entsprechend von `einstellungen` auf `recherche` umgezogen.
- **Die Sieben-Tabs-Grenze aus v2.7.21/22 ist strukturell aufgehoben, nicht nur verschoben.** Ein achter Tab hätte mit der alten `flex:1`-Gleichverteilung bei 11px wieder Labels abgeschnitten — statt wie damals einen Tab zu opfern (Info → Profil), scrollt `.tabs` jetzt horizontal (`overflow-x:auto`, Buttons behalten ihre natürliche Breite über `flex:0 0 auto`) und `initTabs()`s Klick-Handler holt den angetippten Button per `scrollIntoView({inline:'nearest'})` vollständig ins Bild. Ein künftiger neunter Tab gefährdet damit keine bestehenden Labels mehr. Desktop (v2.8.0-Sidebar) war nie betroffen — dort ist `.tabs` ohnehin eine vertikale Spalte; `recherche` musste dort nur in die `display:none`-Liste der Nicht-Dashboard-Panels aufgenommen werden (`#form-section.dashboard-mode .tab-panel[data-panel="recherche"]`).
- **Neue Fortschritts-Anzeige** (`.research-progress`, `#research-progress`) ersetzt den kleinen Button-Spinner: rotierende Statustexte (`T.research_phasen`, neue Übersetzungsliste de/en, 5 Phrasen à ~4,5s Anzeigedauer) plus ein hochzählender `mm:ss`-Timer seit Laufbeginn. Visuell die **Splash-Screen-Radar-Ringe wiederverwendet** (`@keyframes splashPulse`, schon für den Ladebildschirm gebaut) statt eine neue Animation zu erfinden — bleibt im selben visuellen Stil der App. Bewusst **kein** vorgetäuschter Fortschrittsbalken oder Stufen-Zähler ("Schritt 2 von 5") — der Backend-Job ist ein einzelner opaker Claude-Call ohne echte Zwischenstufen, ein exakter Fortschritt wäre erfunden; die rotierenden Phrasen behaupten keine bestimmte Reihenfolge oder einen Prozentsatz.
- **Beide Buttons (Thema + Video) werden während eines Laufs gemeinsam gesperrt** (`_researchButtons()`), nicht mehr nur der jeweils geklickte — verhindert zwei gleichzeitige Läufe, die sich denselben Job-Store streitig machen könnten.
- Test `test_wiring.py` „es bleiben sieben Tabs" (v2.7.21) ist auf „acht Tabs, Leiste scrollt horizontal" umgeschrieben — die alte Prüfung wäre mit diesem Commit zurecht fehlgeschlagen.

### v2.9.2 — Recherche-Agent wertet YouTube-Podcasts/-Vlogs aus
Nutzerfrage: könnte der Coach auch aus Podcasts/Vlogs zu Sportthemen lernen? Klarstellung vorab: Claude hat keine native Audio-/Video-Eingabe — der einzig funktionierende Weg ist ein **Transkript** (Text) zu analysieren. Auf Nachfrage wollte Hendrik den bequemsten Einstieg: nur den YouTube-Link einfügen, das Transkript automatisch abrufen lassen.

**Wichtiger Fund während der Umsetzung:** YouTube blockiert Transkript-Abrufe von Cloud-Server-IPs (Railway, AWS, GCP, …) zuverlässig anhand der ASN — nicht nach mehreren Versuchen, sondern beim allerersten Aufruf. Ein Datacenter-Proxy hätte dieselbe Blockade, hilft also nicht. Auf Nachfrage hat sich Hendrik trotzdem für den automatischen Abruf entschieden, mit einem **residentiellen Rotating-Proxy** (Webshare) als Voraussetzung — bewusst kein Zurückweichen auf „Transkript von Hand einfügen", obwohl das ohne jede Zusatzinfrastruktur funktioniert hätte.

- **`youtube.py`** (neu, Blattmodul nach dem Vorbild von `strava.py`) — `extract_video_id()` (watch/`youtu.be`/`shorts`/`embed`/`live`-URLs), `fetch_transcript_and_title()` über `youtube-transcript-api` mit `WebshareProxyConfig` aus `WEBSHARE_PROXY_USERNAME`/`PASSWORD`. Fehlen die ENV-Vars: `YoutubeNotConfigured` — derselbe „klarer Fehler statt kryptischer Absturz"-Reflex wie bei fehlendem `TP_MCP_URL`/`STRAVA_CLIENT_ID`. Titel kommt best-effort über YouTubes öffentlichen oEmbed-Endpoint (kein Scraping-Ziel, kein Proxy nötig, ein Fehler dort ist nie fatal — der Titel ist nur ein Anzeigedetail). Transkript wird bei 60.000 Zeichen gekappt (`_MAX_TRANSCRIPT_CHARS`, reine Funktion `_kuerzen()`) — Kostendeckel analog zu „maximal 5 Erkenntnisse" in `research.md`, ein 3h-Podcast-Transkript wäre sonst weder bezahlbar noch sinnvoll auswertbar.
- **`agents/research/research.py`** — neue Funktion `run_video()` neben `run()`, **dasselbe `SCHEMA`** (keine Änderung an `knowledge.py` nötig) und derselbe `call_agent_with_search()`-Helper — der Agent darf beim Verifizieren einer Video-Behauptung weiterhin die Websuche nutzen.
- **`agents/research/research_video.md`** (neuer Prompt, eigene Datei statt Wiederverwendung von `research.md`): ein Podcast-Host, der überzeugend klingt, hat damit nichts belegt — der Prompt verlangt, Behauptungen aus dem Transkript aktiv per Websuche zu verifizieren, und macht `konfidenz: hoch` **strenger** als bei der offenen Themenrecherche: nur bei unabhängig bestätigten Aussagen, nie allein weil der Sprecher selbstsicher auftritt. `quelle` ist die tatsächliche Evidenzquelle — bei unverifizierten Aussagen ausdrücklich die Video-URL selbst, damit sichtbar bleibt, dass es nur eine mündliche Behauptung ohne externe Bestätigung ist.
- **`app.py`** — neuer Endpoint `POST /api/research/video` **ohne neuen Job-Store**: nutzt `_research_jobs`/`_research_job_start()` weiter, das Ergebnis hat dieselbe Form wie bei der Themen-Recherche, also bleibt das Frontend-Polling (`pollResearch()`) unverändert. Der Transkript-Abruf läuft **synchron vor dem Job-Spawn** (schnelle, deterministische I/O, kein Claude-Call) — schlägt er fehl (keine Untertitel, Proxy nicht konfiguriert, YouTube blockt trotzdem), entsteht gar kein Job, sondern sofort ein 400 mit klarer Fehlermeldung. Nur der langsame Claude-Teil (`_run_video_job()`, analog `_run_research_job()`) läuft im Hintergrund.
- **`templates/index.html`** — zweites Eingabefeld (YouTube-Link + Button) in derselben Recherche-Karte im Profil-Tab, per gestrichelter Linie vom Themen-Feld abgesetzt. Neue JS-Funktion `startVideoResearch()` neben `startResearch()` — nutzt **dasselbe** `pollResearch()` unverändert.
- **`requirements.txt`** — `youtube-transcript-api==1.2.4` (neue Abhängigkeit).

**Live gegen echtes YouTube + Webshare getestet, noch am selben Tag:** Hendriks kostenloses Webshare-Kontingent (10 IPs) hat direkt funktioniert — drei aufeinanderfolgende Transkript-Abrufe erfolgreich (~5–6s je Abruf), Titel per oEmbed korrekt erkannt, und ein kompletter Lauf über `POST /api/research/video` gegen die echte Anthropic-API. Als Testvideo bewusst ein sportfremdes Musikvideo gewählt (Rick Astley) — die Ehrlichkeitsregel aus `research_video.md` griff korrekt: leere `erkenntnisse`-Liste mit der zutreffenden Begründung „kein sport-/trainingswissenschaftlicher Inhalt", statt eine Sport-Verbindung zu erzwingen. Ein **bezahlter** Webshare-Plan ist damit vorerst nicht nötig — nur falls das Gratis-Kontingent künftig erschöpft/gesperrt wird, ist der „Residential"-Plan (siehe Umgebungsvariablen oben) die Rückfalloption.

### v2.9.1 — Coach-Chat: Fachkollegen konsultieren + neue Trainingseinheiten/Serien anlegen
Nutzerwunsch, zwei Lücken im Chat: (1) der Chat sollte bei entsprechenden Themen auch die anderen spezialisierten Agenten (Mediziner, Wetter-Taktiker, Periodisierer, Ernährungsberater) befragen können, nicht nur aus dem allgemeinen Kontext heraus antworten; (2) es sollte möglich sein, in TrainingPeaks neue Trainingseinheiten bzw. ganze Serien davon anzulegen — nicht nur bestehende umbenennen/streichen wie bisher. Explizit **nicht** im Scope: bestehende Einheiten verschieben/umplanen — dafür bleibt der Abend-/Morgen-Check zuständig.

- **`agents/base.py`** — neue Funktion `call_agent_with_consult()` neben `call_agent_with_tools` (die unverändert bleibt, keine der drei bestehenden propose-Tools ist betroffen). Löst ein Problem, das `call_agent_with_tools`s bewusstes Ein-Call-Design (kein Tool-Result-Loop, siehe v2.8.1) für Feature 1 ungeeignet macht: ein `consult_*`-Tool-Call soll nicht nur Name+Input zurückgeben (wie bei `propose_*`), sondern eine ECHTE fachliche Einschätzung, die in dieselbe Antwort einfließt — das braucht einen zweiten Anthropic-Call mit dem `tool_result` des ausgeführten Spezialisten. Ruft die Antwort kein Consult-Tool, verhält sich die Funktion identisch zu `call_agent_with_tools` (ein Call, keine Mehrkosten im Normalfall). Kostendeckel `MAX_CONSULTS_PER_TURN = 2`: weitere Consult-Aufrufe in derselben Runde bekommen einen synthetischen Limit-Fehler statt ausgeführt zu werden. Ruft das Modell gleichzeitig ein `consult_*`- und ein `propose_*`-Tool auf, wird nur der Consult ausgeführt — der `propose_*`-Call bekommt einen synthetischen Hinweis zurück, damit ihn Claude bei Bedarf in der finalen Antwort erneut stellt. Grund: die pending-action-Logik für Schreibzugriffe lebt bewusst exklusiv in `app.py`, nicht in `base.py` dupliziert.
- **`agents/chat/chat.py`** — fünf neue `CONSULT_*_TOOL`-Schemas (`consult_medic`, `consult_allgemeinmedic`, `consult_weather`, `consult_periodizer`, `consult_fueling`, zusammengefasst in `CONSULT_TOOLS`/`CONSULT_TOOL_NAMES`) sowie `propose_workout_series` (ergänzt `CHAT_TOOLS`, jetzt vier statt drei Einträge). Alle Consult-Tool-Felder sind bewusst optional — dieselbe Extraktion-aus-Fließtext-Fähigkeit, die das Modell bei `date`/`workout_hint` in den bestehenden Tools schon zeigen muss, füllt hier z.B. `knie`/`waden` nur, wenn der Athlet sie im Gespräch tatsächlich erwähnt (`medic.build_input` defaultet den Rest ohnehin auf neutral). `propose_workout_series` nimmt bewusst KEIN `structure`/`subtype_id` — neue Chat-Einheiten sind einfache Einheiten ohne Intervallstruktur, dafür bleibt der Verweis auf den Check (der zuständige Disziplin-Coach hat dort den nötigen Auftragskontext, der Chat nicht). `run()` bekommt einen neuen optionalen Parameter `consult_executor` — gesetzt, laufen `CHAT_TOOLS+CONSULT_TOOLS` über `call_agent_with_consult`; ungesetzt (Default) bleibt das alte Verhalten unverändert.
- **`app.py`** — `_build_consult_executor()` dispatcht jeden `consult_*`-Namen auf den ECHTEN Spezialisten (`medic.run`/`allgemeinmedic.run`/`weather.run`/`periodizer.run`/`fueling.run`, direkt importiert statt nur über `orchestrator.py`) und gibt sein Ergebnis zurück — strikt lesend, kein Zweig ruft `call_tp_mcp` auf. `coach_chat()` nimmt dafür `woche` aus `_fetch_training_load()` jetzt mit (wurde vorher verworfen, obwohl schon geladen) und baut zusätzlich `workouts_by_date`, um `sportarten`/`titel` für `consult_weather`/`consult_medic`/`consult_allgemeinmedic` abzuleiten. Schlafdaten für `consult_medic`/`consult_allgemeinmedic` kommen best-effort aus dem letzten `sleep_history.json`-Eintrag (`_consult_sleep()`) — können also älter sein, `chat.md` macht das dem Modell transparent. Für `propose_workout_series`: `_resolve_workout_series_proposal()` (analog zu `_resolve_calendar_note_proposal`, aber für 1..N Einträge — EIN ungültiger Eintrag verwirft die GANZE Anfrage vor der Bestätigung) und ein neuer `workout_series`-Zweig in `chat_tp_action_confirm` (mehrere `tp_create_workout`-Aufrufe, kein Alles-oder-nichts — ein fehlgeschlagenes Workout in der Serie blockiert die übrigen nicht, jede Zeile bekommt ihren eigenen Status, wie bei mehreren Operationen in `tp_apply`).
- **`templates/index.html`** — neuer expliziter `workout_series`-Zweig in `appendProposalCard` (musste vor den bestehenden generischen `else`-Zweig, der sonst fälschlich als Kalendernotiz gerendert hätte); zeigt bei mehreren Einheiten einen Zähler in der Kopfzeile. `confirmChatProposal` brauchte keine Änderung — rendert `data.actions` bereits generisch als Liste.
- **`agents/chat/chat.md`** — neuer Abschnitt „FACHKOLLEGEN KONSULTIEREN" (Positivliste: welches Thema → welches Consult-Tool, Ein-Tool-pro-Antwort-Regel, Hinweis dass Consult-Ergebnisse echte Einschätzungen sind und in eigenen Worten einzubauen statt zu zitieren). GRENZEN-Abschnitt aktualisiert: vier statt drei TP-Tools, `propose_workout_series` erklärt, Verschieben bleibt weiterhin explizit ausgeschlossen.
- **Kein neues Root-`anyOf`/`oneOf`/`allOf`** in irgendeinem der neuen Tool-Schemas (die v2.8.2-Fehlerklasse) — `propose_workout_series`s Array-in-`properties` ist davon nicht betroffen, „mindestens ein gültiger Eintrag" wird wie bei den bestehenden Tools serverseitig durchgesetzt, nicht im Schema. Trotzdem bleibt ein Live-Test mit echtem Key zwingend, da ein Root-Schema-Fehler nur dort auffliegt (v2.8.2-Lehre) — mit Attrappen in `tests/test_wiring.py` abgesichert (Root-Schema-Check, Tool-Result-Loop inkl. Kostendeckel, Executor-Dispatch ohne `call_tp_mcp`-Aufruf, Serien-Resolver inkl. Teil-Fehler-Fall), aber noch nicht gegen die echte API gefahren.

### v2.9.0 — Recherche-Agent: Chefcoach bekommt Kontext aus frei verfügbarer Literatur
Nutzerfrage: kann der Chefcoach „automatisch lernen" und frei verfügbare Literatur lesen/auswerten? Klarstellung vorab: echtes Lernen (Gewichte-Update) gibt es über die Claude-API nicht — jeder Call ist zustandslos. Was jetzt geht: ein neuer Agent recherchiert auf Zuruf ein von Hendrik vorgegebenes Thema per Claudes serverseitigem `web_search`-Tool. Erster Entwurf sah „Vorschlag, erst nach Klick wirksam" für jeden Fund vor (analog zum Chat-Vorschlags-Flow, v2.8.1) — Hendrik wollte explizit **ohne seine Zustimmung** lernen. Kompromiss statt Wegfall jeder Absicherung: **Funde mit Konfidenz `hoch` werden automatisch akzeptiert und wirken sofort im nächsten Check, `mittel`/`niedrig` bleiben Vorschlag zur Prüfung im Profil-Tab** — eine deterministische Code-Regel statt Zustimmung pro Fund, im selben Stil wie der harte Pause-Stop beim Allgemeinmediziner (v2.7.7): keine Prompt-Disziplin, sondern eine Schwelle im Code, die eine schwach belegte Einzelstudie nicht ungefiltert an den Chefcoach durchlässt.

- **`agents/base.py`** — neuer Helper `call_agent_with_search()` neben `call_agent`/`call_agent_text`/`call_agent_with_tools`: ruft Claude mit dem serverseitigen `web_search_20260209`-Tool **und** erzwungenem `output_config`-Schema in einem Request. Anders als bei `call_agent` zählt hier der **letzte** Text-Block, nicht der erste — vor dem finalen JSON stehen noch die `server_tool_use`/`web_search_tool_result`-Blöcke der Suche.
- **`agents/research/`** (neu) — eigener Agent (Dr. Mara Lindqvist, Sportwissenschaftliche Recherche) auf Sonnet, analog zur FIT-Analyse die einzige andere Stelle im Projekt, die „echtes Reasoning" statt Haiku braucht. Bekommt ein Freitext-Thema, liefert `zusammenfassung` + eine Liste `erkenntnisse` (Titel, Aussage, Quelle, Konfidenz hoch/mittel/niedrig, `betrifft`-Stichwort). Der Prompt verlangt ehrliche Konfidenz-Einschätzung und verbietet erfundene Quellen — eine leere Fundliste mit ehrlicher Zusammenfassung ist ausdrücklich ein besseres Ergebnis als erfundener Inhalt.
- **`knowledge.py`** (neu, Blattmodul ohne File-I/O) — `new_entry()`/`accept()`/`reject()`/`accepted_context()`/`add_findings()`. Jeder Fund startet bei `status: "vorschlag"`; `add_findings()` — die einzige Stelle, die einen kompletten Recherche-Lauf entgegennimmt — akzeptiert Funde mit `konfidenz == AUTO_ACCEPT_KONFIDENZ` ("hoch") sofort automatisch, alles andere bleibt Vorschlag. `entschieden_von` (`"system"`|`"hendrik"`) hält fest, welcher Weg es war, sichtbar im Profil-Tab als Zusatzhinweis. `accepted_context()` rendert nur `status: "akzeptiert"`-Einträge als Markdown-Block, leer wenn nichts akzeptiert ist — unabhängig davon, ob automatisch oder manuell.
- **`knowledge.json`** (neu, `DATA_DIR`-persistiert wie `athlete.json`/`baseline.json`, in `_STATE_FILES` aufgenommen) — dauerhafter Speicher für Recherche-Funde inkl. Entscheidungsstatus.
- **`app.py`** — Job-Queue fürs Recherchieren (`_research_jobs`/`_research_job_start()`/`_run_research_job()`), exakt das `_check_jobs`-Muster (Sonnet + Websuche brauchen zu lange für einen offenen Request), aber ein eigener Store. Neue Endpoints: `POST /api/research/run` (Thema → `job_id`), `GET /api/research/{job_id}` (Polling), `GET /api/knowledge` (Liste), `POST /api/knowledge/{id}/accept|reject`. Vor jedem Check lädt `_try_agent_check()` die akzeptierten Funde (`knowledge.accepted_context()`, reines File-Lesen, kein Modell-Call) und reicht sie als `wissen` durch.
- **`orchestrator.py`/`agents/head_coach/head_coach.py`** — `run_check()`/`head_coach.run()`/`build_input()` bekommen einen neuen optionalen Parameter `wissen`. Ist er gesetzt, hängt `build_input()` eine Sektion „Erkenntnisse aus der Literatur (von Hendrik geprüft, ergänzend)" an — analog zur bestehenden `block`-Sektion (Periodisierer). Kein Schema-Change: `wissen` ist reiner Input-Kontext, kein neues Output-Feld.
- **`agents/research/research.md`** macht dem Modell die Tragweite von `konfidenz: "hoch"` explizit: anders als bei `mittel`/`niedrig` liest das **niemand mehr gegen**, bevor es wirkt — die Vergaberegel („mehrere unabhängige Studien oder eine Metaanalyse, keine bekannte widersprechende Evidenz") ist entsprechend strenger formuliert als vorher, mit der Anweisung „im Zweifel `mittel`, nicht `hoch`".
- **Bewusste Scope-Entscheidungen fürs MVP:** (1) kein Cron — „automatisch" heißt hier auf Klick ausgelöst, nicht periodisch (siehe „Offene Punkte"), die Auto-Accept-Regel gilt aber ab dem ersten Lauf ohne weiteres Zutun; (2) das Thema kommt von Hendrik, der Agent sucht sich nicht selbst aus, was er recherchiert; (3) nur der Chefcoach bekommt akzeptierte Funde zu sehen, Periodisierer/Fueling/Mediziner separat anzureichern wäre dieselbe Mechanik, aber nicht in diesem Schritt gebaut; (4) kein neuer Auth-Layer — der neue Endpoint hat dieselbe (fehlende) Absicherung wie `POST /api/admin/backfill-weather`; (5) jeder Recherche-Lauf ist ein zusätzlicher Kostenfaktor (Sonnet + pro Suche abgerechnetes `web_search`-Tool), bewusst nur auf Zuruf, nie Teil des täglichen Checks.
- **`templates/index.html`** — neuer Abschnitt „🔬 Recherche" im Profil-Tab: Themeneingabe + Button, darunter die Fundliste mit Übernehmen/Verwerfen-Buttons (offene Vorschläge) bzw. Status-Badge inkl. „(automatisch, hohe Konfidenz)"-Hinweis bei `entschieden_von: "system"` (bereits entschiedene). Kein neuer Top-Level-Tab — die Tableiste ist an ihrer Breitengrenze (v2.7.21/22).

Live gegen die echte API getestet (Thema „Carb-Intake pro Stunde bei Ironman-Distanz"): ein Lauf dauert **3–4 Minuten** (mehrere Websuchen + Sonnet-Reasoning in einem einzigen Request) — spürbar länger als die Checks, aber unkritisch, weil er als Hintergrund-Job läuft und niemand darauf wartet, um trainieren zu gehen. **Nebenbefund beim Live-Testen:** `max_tokens=3000` reichte nicht — eine gründliche Antwort mit mehreren Funden lief in „Antwort zu lang" (derselbe abgeschnitten-JSON-Fehler wie bei jedem anderen Agenten mit erzwungenem Schema). Der Job landete dabei korrekt als `status: error` statt hängen zu bleiben — das Job-Queue-Fehlerhandling hat sich bewährt. Behoben durch `max_tokens=6000` plus eine explizite Obergrenze „maximal 5 Erkenntnisse" im Prompt (`research.md`) — bei mehr Funden würde ohnehin niemand jeden einzeln prüfen wollen. Der zweite Lauf mit dem exakt gleichen Thema lieferte danach 5 Funde mit echten, dereferenzierbaren PubMed-/Coaching-Quellen und ehrlich unterschiedlicher Konfidenz (u.a. eine Einzelfallstudie korrekt als „niedrig" markiert).

### v2.8.9 — Ladeanzeige der Checks wieder zentriert mit gedimmtem Hintergrund
Nutzerbeobachtung: während Abend-/Morgen-Check laufen, erscheint der Lade-Hinweis nur als kleine Zeile unten im Formular (direkt unter dem Submit-Button), ohne den Rest der Seite abzudunkeln — wirkt unauffällig und leicht zu übersehen. Ursache: `.check-status` war seit v2.8.0 bewusst kein globales Overlay mehr, sondern eine inline `display:flex`-Zeile im Formular, damit zwei gleichzeitig laufende Checks (Desktop-Dashboard) sich nicht denselben Spinnertext/dieselbe Position streitig machen.

- **`templates/index.html`** — `.check-status` bleibt weiterhin **pro Check ein eigenes Element** (`check-status-abend`/`-morgen`, keine Rückkehr zum einen globalen `#loading-overlay`), ist jetzt aber wie dieses als `position:fixed; inset:0` mit gedimmtem, geblurrtem Hintergrund (`rgba(15,15,19,.85)`, `backdrop-filter: blur(4px)`) und zentriertem Spinner+Text gestaltet, statt als inline Zeile im Formularfluss. Löst beides: die Anzeige sitzt wieder in der Bildschirmmitte, und die Seite tritt währenddessen optisch in den Hintergrund. Die Unabhängigkeit der beiden Checks (Kern des v2.8.0-Fixes) bleibt erhalten — bei einem seltenen gleichzeitigen Lauf beider Checks überlappen sich zwei Overlays, statt dass sich Text/Zustand vermischt.
- Der Fehlerbanner (`.check-error`, dauerhaft sichtbar bis Antippen, v2.7.17) ist unverändert inline im Formular — nur die Lade-Anzeige war betroffen.
- Kein JS geändert: `setCheckLoading`/`setCheckLoadingText` togglen weiterhin nur `display:flex`/`none` auf demselben Element.

### v2.8.8 — Desktop-Dashboard: Morgen vor Abend
Nutzerbeobachtung: im Desktop-3-Spalten-Dashboard (v2.8.0) stand „Abend" links von „Morgen" — falsch herum für den Tagesablauf. Ursache: das Grid ordnet ohne explizites CSS nach DOM-Reihenfolge der `.tab-panel`-Elemente, und die liegen historisch als abend/morgen/ernaehrung im Template (die mobile Tab-Leiste selbst war schon immer korrekt Morgen-vor-Abend sortiert, v2.7.22 — das Dashboard-Grid folgte dem nicht).

- **`templates/index.html`** — drei `order`-Regeln auf die `dashboard-mode`-Panels (`morgen:1`, `abend:2`, `ernaehrung:3`) statt die große Markup-Reihenfolge im Body zu verschieben — kleinere, risikoärmere Änderung als die beiden Panel-Blöcke (je hunderte Zeilen) im Quelltext zu vertauschen.

### v2.8.7 — Periodisierer muss CTL/ATL immer neben TSB nennen, nicht isoliert
Nutzerfrage nach v2.8.6: „warum nutzt du nicht CTL und ATL zur Analyse?" — berechtigt: `agents/periodizer/periodizer.py` bekam CTL/ATL im Prompt-Kontext zwar schon immer mitgeliefert, aber `periodizer.md` instruierte nur TSB-Schwellen als Entscheidungsgrundlage und im Beispielsatz („TSB −22 nach neun Tagen ohne Erholung"), nie CTL/ATL selbst zu nennen. Der Chefcoach sieht von Periodisierer ohnehin nur die fertige Text-Begründung (`heute_begruendung`/`hinweis`), keine Rohzahlen — stand dort nur TSB, tauchten CTL/ATL im gesamten Entscheidungsweg nirgends mehr auf.

Fachlich relevant: TSB als reine Differenz sagt ohne CTL-Niveau wenig — TSB −15 bei CTL 50/ATL 65 (schwach ausgebildeter Athlet) ist ein anderes Signal als TSB −15 bei CTL 108/ATL 123 (sehr hohes Grundniveau, tolerantfähig für tiefere Werte in einem Aufbaublock).

- **`agents/periodizer/periodizer.md`** — neue Regel: CTL und ATL immer zusammen mit TSB nennen, nie isoliert; die TSB-Schwellentabelle ist relativ zum CTL-Niveau zu lesen, nicht absolut. `zuruecknehmen`-Begründung und der Beispielsatz am Ende verlangen jetzt explizit alle drei Zahlen.
- Reine Prompt-Änderung, kein Code — die Kennzahlen waren immer schon im Input, nur die Formulierungspflicht fehlte.

Nebenbefund beim Testen: der Test für die alte Formulierung „Zähle Ruhetage ab" (`"Ruhetage ab" in per_prompt`) war seit v2.8.5 kaputt, ohne dass es aufgefallen ist — die Zeile wurde dort durch die Trainingsstreak-Anweisung ersetzt, der Test aber nicht mitgezogen (die Sandbox, in der getestet wurde, konnte `tests.test_offline` wegen eines `httpx`-Importhängers nicht komplett durchlaufen lassen). Jetzt auf die aktuelle Formulierung („fertig gezählt") korrigiert und die neue CTL/ATL-Regel mitgeprüft.

### v2.8.6 — CTL/ATL/TSB kommen jetzt direkt von TP, nicht mehr aus eigener Nachrechnung
Live-Rückmeldung: „TSB stimmt nicht — TP zeigt −19 (letzte Woche) und −17 (aktuelle Woche), die App −38,8." Gegenprobe direkt gegen die Produktionsdaten: unsere `letzte_einheiten`-Liste zeigte am 23.8. **zwei** Lauf-Einträge mit exakt identischer Dauer (87min) und identischem TSS (96) — „KPL" und „Ludwigsfelde", offenbar derselbe Lauf einmal manuell benannt und einmal per Geräte-Sync automatisch betitelt, in TP nicht miteinander verknüpft. Unsere Summe zählte beide (192 TSS statt 96), was `training_load.compute_pmc()` über die exponentielle ATL-Glättung zu einem deutlich zu niedrigen TSB hochrechnete.

Der eigentliche Fehler war der Architekturentscheid selbst: „TSS ist TSS, egal welche Disziplin" (v2.8.4) stimmt, aber **TSS ist nicht TSS, wenn TP dieselbe Einheit zweimal zählt** — ein Duplikat in TPs eigenen Daten kann unsere Nachrechnung nicht erkennen, TP selbst (mit Zugriff auf die komplette Rohhistorie und eigener Sync-Logik) offenkundig schon, denn TPs eigene Anzeige war korrekt.

- **Der TrainingPeaks-MCP-Server** (separates Repo `trainingpeaks-mcp`, eigener Railway-Service) hat bereits ein passendes Tool: **`tp_get_fitness`** — ruft TPs eigenen `/fitness/v1/.../performancedata`-Endpoint auf und liefert TPs bereits fertig gerechnetes CTL/ATL/TSB pro Tag. Live gegen Produktion geprüft: liefert für den 23.8. TSS 95,95 (nicht 191,9) und aktuell TSB −14,9 — nah an den von Hendrik genannten TP-Werten, unsere eigene Rechnung war die Abweichung.
- **`training_load.pmc_von_tp(daily_data, bis)`** (neu) baut aus `tp_get_fitness`s Antwort denselben Kennzahlen-Vertrag (`ctl`/`atl`/`tsb`/`ramp_7d`/`ctl_vor_28d`/`tss_7d`/`tss_28d`/`tage_mit_daten`/`verlauf`), den vorher `compute_pmc()` selbst berechnet hat — **übernimmt** TPs Zahlen, statt sie nachzurechnen. Die gemeinsame Aggregation (Ramp Rate, 7d/28d-Summen, 14-Tage-Ausschnitt) ist in `_pmc_zusammenfassung()` ausgelagert, damit `compute_pmc` und `pmc_von_tp` nicht auseinanderlaufen können.
- **`app._fetch_training_load()`** ruft jetzt `tp_get_workouts` (für Titel/Sportart-Kontext: `letzte_einheiten`/`trainingsstreak`/`wochenstruktur`) und `tp_get_fitness` (für CTL/ATL/TSB) parallel per `asyncio.gather`. Schlägt `tp_get_fitness` fehl, läuft der Check wie bisher bei jedem TP-Fehler ohne Periodisierer weiter (`None, None`) — kein stiller Rückfall auf die alte, jetzt als unzuverlässig erkannte Eigenrechnung.
- **`compute_pmc()`/`tss_pro_tag()` bleiben im Code** (weiterhin von Tests abgedeckt) — als dokumentierte deterministische Referenzrechnung, aber **nicht mehr im Live-Pfad**. Bewusst nicht gelöscht: eine größere Aufräumentscheidung, die getrennt von diesem Bugfix ansteht, falls gewünscht.

Tests (`test_offline.py`): `pmc_von_tp()` übernimmt TPs Werte unverändert (mit den echten 23.8.-Produktionszahlen als Fixture), ignoriert Tage nach dem Stichtag, stürzt ohne Daten nicht ab; `compute_pmc()` bleibt unverändert grün (Regressionsschutz für die weiterhin vorhandene Referenzrechnung); `app.py` referenziert nachweislich `tp_get_fitness`.

### v2.8.5 — Periodisierer verzählte sich, Trainingsstreak jetzt vorgerechnet
Live-Rückmeldung: die App zeigte „Erholungstag nach 13 Tagen ohne Pause" (TSB −38,8, ATL 119,4) — tatsächlich lag die letzte Pause laut TP nur 6 Tage zurück. Gegenprobe über `/api/load`: `letzte_einheiten` zeigt genau einen Ruhetag am 17.8., danach durchgehend Training bis zum 23.8. — 6 Tage, nicht 13. `periodizer.md` instruierte das Modell zwar schon seit v2.7.14 „zähle ab, statt zu vermuten", aber genau dieses Nachzählen aus der Tages-Tabelle war die Fehlerquelle, nicht die Datenlage — dieselbe Klasse Fehler, wegen der `training_load.py` CTL/ATL/TSB von Anfang an deterministisch statt vom Modell rechnen lässt.

- **`training_load.trainingsstreak()`** (neu) — zählt aufeinanderfolgende Tage mit `load_sports`-TSS (siehe v2.8.4) rückwärts ab **gestern** (heute zählt nicht mit, dessen Rolle wird gerade erst bestimmt), bis der erste Tag ohne TSS auftaucht oder `PMC_TAGE` erreicht ist. Bewusst dieselbe `load_sports`-Filterung wie `letzte_einheiten`/`wochenstruktur` — ein reiner Kraft-Tag unterbricht den Streak nicht, weil er für die Ausdauerplanung ohnehin ein Ruhetag ist.
- **`app._fetch_training_load()`** reicht `load["trainingsstreak"]` durch, **`agents/periodizer/periodizer.py`** hängt die fertig gezählte Zahl **als erste Kennzahl, fett hervorgehoben** an den Prompt: „diese Zahl exakt übernehmen, nicht selbst nachzählen".
- **`periodizer.md`** — die alte Anweisung „Zähle Ruhetage ab, statt sie zu vermuten" war Teil des Problems, nicht die Lösung: sie forderte eigenes Nachzählen, statt die jetzt mitgelieferte Zahl zu nennen. Ersetzt durch die Anweisung, ausschließlich die mitgelieferte Zahl zu verwenden. Die `warnung`-Schwelle „kein Erholungstag in den letzten 10 Tagen" ist entsprechend auf „Trainingsstreak ≥ 10" umformuliert.

Tests (`test_offline.py`): `trainingsstreak()` zählt anhand der echten Produktionszahlen (17.8. Pause, 18.–23.8. durchgehend) korrekt 6, nicht 13; ohne Daten kein Absturz; der Periodisierer-Prompt referenziert `trainingsstreak` nachweislich.

### v2.8.4 — Ruhetag-Erkennung ignoriert Kraft/Sonstiges, konfigurierbar
Nutzerbeobachtung: der Periodisierer erkannte einen Tag mit ausschließlich Kraft (oder Golf/Sonstiges) nicht als Ruhetag — `training_load.letzte_einheiten()`/`wochenstruktur()` markierten jeden Tag mit **irgendeiner** TP-Einheit als Trainingstag, unabhängig von der Sportart. Für die Ausdauerplanung ist ein reiner Stabi-Tag aber ein Ruhetag.

- **`training_load.py`** — neuer Parameter `load_sports` bei `letzte_einheiten()`/`wochenstruktur()`, Default `DEFAULT_LOAD_SPORTS = ["Rad", "Laufen", "Schwimmen"]`. Nur Einheiten, deren `normalize_sport()`-Ergebnis in dieser Liste steht, zählen als „Trainingstag" — ein Tag mit nur Kraft/Golf/Sonstiges liefert jetzt eine leere `einheiten`-Liste und erscheint dem Periodisierer korrekt als Ruhetag. `normalize_sport` kommt aus `nutrition.py` (bereits Blattmodul, keine neue Abhängigkeit).
- **Konfigurierbar statt hartkodiert**, analog zu `no_fuel_sports`: neues Feld `load_sports` in `athlete.json` (Default `["Rad", "Laufen", "Schwimmen"]`). `app._fetch_training_load()` reicht `athlete.get("load_sports")` an beide Funktionen durch — ohne Eintrag (oder leere Auswahl) greift der Code-Default.
- **Profil-Tab** — vier Checkboxen (Rad/Laufen/Schwimmen/Kraft) unter den chronischen Befunden, `fillProfileForm()`/`saveProfile()` lesen/schreiben `load_sports`. Golf/Brick/Sonstiges sind bewusst nicht wählbar — `normalize_sport()` kennt nur diese vier Namen plus den Sonstiges-Fallback.
- **CTL/ATL/TSB bleiben unverändert** — `tss_pro_tag()`/`compute_pmc()` filtern nicht nach Sportart, ein TSS-Wert ist echte physiologische Belastung unabhängig von der Disziplin. Betroffen ist nur der **Text**, den der Periodisierer über die letzten/kommenden Tage sieht (und der `/api/load`-Output für den MCP-Server) — dort steht jetzt „Ruhetag (0 TSS)" statt einer Kraft-Einheit, wenn Kraft nicht in `load_sports` steht.

Tests (`test_offline.py`): ein reiner Kraft-Tag gilt per Default als Ruhetag bei `letzte_einheiten()` **und** `wochenstruktur()`, wird Kraft explizit in `load_sports` aufgenommen, zählt der Tag wieder mit seiner echten TSS-Summe.

### v2.8.3 — Chat darf jetzt auch Einheiten streichen
Live-Test nach v2.8.2: „Die Radeinheit heute bitte streichen, ich habe ein Date" — der Coach hat das (korrekt gemäß der bis dahin festgelegten Regeln) abgelehnt und auf den Abend-/Morgen-Check verwiesen, weil Streichen/Verschieben bewusst außerhalb des ursprünglichen Scopes lag. Auf Nachfrage entschieden: Streichen soll erlaubt sein — und lässt sich technisch günstig nachrüsten, weil „Streichen" im bestehenden Check-Flow (`tp_apply`) ohnehin nur eine **Titel-Umbenennung** ist (`❌ {Titel} (KI)`, TP löscht dabei nichts), also dieselbe Tool-Klasse wie `propose_workout_update` — kein neues MCP-Recht nötig.

- **`agents/chat/chat.py`** — drittes Tool `propose_workout_skip` (`date`, `workout_hint`, `summary` — kein `new_title`, der Server bildet den Titel selbst). `CHAT_TOOLS` hat jetzt drei Einträge.
- **`agents/chat/chat.md`** — GRENZEN-Abschnitt erweitert, das bisherige Negativ-Beispiel „streich die Einheit" (durfte keinen Tool-Call auslösen) ist raus, da jetzt explizit erlaubt.
- **`app.py`** — `_resolve_workout_skip_proposal()` löst wie `_resolve_workout_update_proposal()` über `_match_tp_workouts()` auf, baut den neuen Titel aber serverseitig aus `clean_title()` + `T["tp_skip_renamed"]` — exakt dieselbe Konvention wie die SKIP/STOP-Badges im Check, damit gestrichene Einheiten unabhängig vom Auslöser (Chat oder Check) gleich aussehen. `chat_tp_action_confirm()` behandelt `workout_update` und `workout_skip` im selben Zweig (beides am Ende nur `tp_update_workout` mit `title`).
- **`templates/index.html`** — dritte Kartenvariante in `appendProposalCard()` zeigt Datum/Sportart/Originaltitel + den neuen ❌-Titel zur Kontrolle vor dem Bestätigen.

Mit echtem API-Key gegen die echten Produktionsdaten verifiziert: die ursprünglich fehlgeschlagene Nachricht aus dem Live-Test liefert jetzt korrekt einen `workout_skip`-Vorschlag mit `❌ 4h30 LIT (KI)`.

### v2.8.2 — Chat-Tools liefen live nie, weil `anyOf` auf oberster Ebene stand
Nutzer-Rückmeldung: „ich konnte über den Chat am iPhone keine Änderung in TP vornehmen" — noch am selben Tag wie v2.8.1. Mit dem echten `ANTHROPIC_API_KEY` reproduziert: **jeder** `messages.create(..., tools=CHAT_TOOLS)`-Aufruf schlug mit `400 invalid_request_error` fehl (`input_schema does not support oneOf, allOf, or anyOf at the top level`) — `PROPOSE_WORKOUT_UPDATE_TOOL`s `input_schema` hatte genau das, um „mindestens `new_title` oder `new_description`" zu erzwingen. `coach_chat`s `except Exception` fing das ab und fiel still auf den Monolith zurück, der die Fähigkeit gar nicht kennt — die Karte konnte dadurch nie erscheinen, mit `/api/version` sah die Pipeline trotzdem gesund aus (der Fehler passiert erst beim tatsächlichen Tool-Use-Call, nicht beim Import).

- **`agents/chat/chat.py`** — `anyOf` aus `PROPOSE_WORKOUT_UPDATE_TOOL.input_schema` entfernt. Die Regel „mindestens eines von beiden" steht jetzt nur noch in der Tool-Beschreibung und wird — wie ohnehin schon dokumentiert, das Anthropic-Schema wird serverseitig nie erzwungen — von `app._resolve_workout_update_proposal()` durchgesetzt, die das schon vorher prüfte.
- Live mit echtem Key gegen die Produktions-TP-Daten verifiziert (nicht nur gegen Attrappen wie beim ursprünglichen Test): eindeutiger Treffer liefert jetzt `_pipeline: "agents"` mit korrektem `proposal` (echte `workout_id` aus dem TP-Cache), eine normale Frage ohne Änderungswunsch liefert weiterhin reinen Text ohne Tool-Aufruf.

**Lehre für künftige Tool-Schemas:** Anthropics `input_schema` ist kein beliebiges JSON-Schema — `oneOf`/`allOf`/`anyOf` sind nur innerhalb von `properties`-Feldern erlaubt, nicht auf der Objekt-Wurzel. Ein lokaler Test mit `ANTHROPIC_API_KEY=dummy` (wie in `test_wiring.py`) kann das nicht fangen, da er nie wirklich bei Anthropic ankommt — nur ein Lauf mit echtem Key deckt sowas auf.

### v2.8.1 — Coach-Chat kann TP-Änderungen vorschlagen (Propose/Confirm)
Bisher konnte der Chat nichts in TrainingPeaks ändern — `agents/chat/chat.md` sagte das dem Modell sogar explizit. Nutzerwunsch: der Chat soll TP-Änderungen vornehmen können. Weil das echte Schreibzugriffe auf einen produktiv genutzten Trainingskalender sind, vorab geklärt: **Vorschlag statt Sofort-Ausführung** (der Chat schreibt nie direkt, erst ein Klick bestätigt), Scope nur **bestehende Einheit anpassen (Titel/Beschreibung) + Kalendernotiz anlegen** — kein Verschieben, Löschen, keine neuen Einheiten.

Das ist die erste Stelle im Code, die Anthropic Tool-Use/Function-Calling nutzt (bisher nur erzwungenes JSON-Schema via `output_config` oder reiner Freitext).

- **`agents/base.py`** — neue `call_agent_with_tools()` neben `call_agent`/`call_agent_text`: ruft Claude **einmal** mit `tools=`, kein Tool-Result-Loop (solange nichts ausgeführt wurde, gibt es kein Ergebnis zum Zurückspielen). Gibt `{"text", "tool_call"}` zurück statt eines rohen Strings.
- **`agents/chat/chat.py`** — zwei Tool-Schemas (`propose_workout_update`, `propose_calendar_note`, zusammengefasst in `CHAT_TOOLS`). Feldnamen bewusst identisch zu den `call_tp_mcp`-Argumenten (`title`, `description`, `date`, `text`) — keine Umbenennung zwischen Tool-Input und MCP-Call. Claude bekommt nie eine `workout_id` gezeigt und soll auch nie eine raten — `date` + `workout_hint` (wörtlich aus dem Plan-Kontext kopiert) reichen, der Server löst serverseitig auf. `run()` liefert jetzt ein `dict` statt `str`.
- **`agents/chat/chat.md`** — die blockierende Zeile „Du änderst hier nichts in TrainingPeaks" raus, ersetzt durch: wann welches Tool erlaubt ist, dass nur Titel/Beschreibung änderbar sind, und dass bei Unklarheit **kein** Tool gerufen wird, sondern im Text nachgefragt wird.
- **`app.py`** — `_match_tp_workouts()` (case-insensitive Substring-Match von `workout_hint` gegen `sport`/`title` im `_tp_cache`), `_resolve_workout_update_proposal()`/`_resolve_calendar_note_proposal()`/`_resolve_chat_tool_call()` (validieren die vom Anthropic-Tool-Schema **nicht** serverseitig erzwungenen Pflichtfelder selbst — `input` ist ungeprüftes Modell-Output). Bei 0 oder >1 Treffern: keine pending action, sondern eine Python-generierte Rückfrage. Neuer Store `_pending_tp_actions` (TTL 1800s, exakt das `_check_jobs`-Muster: TTL-Sweep-on-Insert, `uuid.hex[:10]`-Ids). Zwei neue Endpoints: `POST /api/chat/tp-action/{pending_id}/confirm` (pop-before-execute — ein zweites Bestätigen kann strukturell nicht doppelt anwenden, 404 bei fehlendem/abgelaufenem Eintrag) und `.../cancel` (idempotent). `coach_chat()` reicht einen Tool-Call an `_resolve_chat_tool_call()` durch und ergänzt die Antwort um ein `proposal`-Feld — der Monolith-Fallback bleibt unverändert (bekommt strukturell kein `tools=`, kann also nie einen Tool-Call erzeugen).
- **`templates/index.html`** — `appendProposalCard()` rendert eine Karte im Chat-Verlauf mit dem **tatsächlich gematchten** Titel/Sportart (der eigentliche Sicherheits-Backstop, nicht die Matching-Logik) + Bestätigen/Verwerfen. `confirmChatProposal()`/`dismissChatProposal()` rufen die neuen Endpoints, gleiches visuelles Muster wie `applyToTP()` (Spinner im Button, grüne/rote Ergebniszeilen).
- **`translations.py`** — zwölf neue de/en-Schlüsselpaare für Karten-Texte, Buttons und die drei Rückfrage-/Fehlertexte.

Tests (`test_wiring.py`): `CHAT_TOOLS` hat exakt zwei Einträge ohne `workout_id`-Feld im Schema, ein eindeutiger Treffer legt die richtige `workout_id` server-seitig an (nicht von Claude geraten), zwei bzw. null Treffer erzeugen keine pending action, Bestätigen ruft `tp_update_workout` mit denselben Parametern wie `tp_apply`, ein zweites Bestätigen liefert 404 (pop-before-execute), `coach_chat` gibt bei einem Tool-Call ein `proposal`-Feld zurück, die alte Sperre ist aus dem Prompt raus.

### v2.8.0 — Desktop-Layout: Sidebar + Morgen/Abend/Fueling als Dashboard
Die App war komplett iPhone-fixiert (`body{max-width:430px}`, keine einzige `@media`-Query). Ab 1024px Fensterbreite jetzt ein echtes Desktop-Layout, ein Template mit CSS-Breakpoints statt einer zweiten Route/Vorlage — passt zur Single-File-Frontend-Linie des Projekts.

- **Sidebar statt oberer Tab-Leiste** (`#desktop-layout`-Wrapper um `.tabs`/`#form-section`, neuer `@media (min-width:1024px)`-Block): dieselben 7 `.tab-btn`, nur restyled (Spalte links, 220px), keine JS-Änderung an `initTabs()`s Grundlogik nötig. `.tab-panel`/`.result-wrap` auf 680px Lesebreite gedeckelt — greift automatisch auch für Erholung/Analyse/Chat/Profil als Einzelansichten (Chat-Bubbles mit `max-width:88%` landen dadurch bei ~600px, ohne JS-Änderung).
- **Morgen/Abend/Fueling als permanentes 3-Spalten-Grid** auf Desktop (`#form-section.dashboard-mode`, CSS-Grid), gesteuert über ein zusätzliches `classList.toggle` in `initTabs()`. Erholung/Analyse/Chat/Profil bleiben Einzelansichten (`display:none` im Grid) — als fokussierte Task-Ansichten (Chat-Verlauf, Workout-Upload) bringt Nebeneinander-Anzeige wenig, bei den beiden Checks + Ernährung dagegen ist der tägliche Blick auf alle drei gleichzeitig der eigentliche Nutzen.
- **Der eigentliche Umbau: Morgen und Abend hatten sich einen einzigen globalen Ergebnis-State geteilt** (`currentResult`, `currentResultType`, `currentFormData`, `tpWorkouts`, `userOverrides`, ein gemeinsames `#result-section`, nicht-namespaced DOM-Ids wie `sport-card-${idx}`). Auf Desktop gleichzeitig sichtbar hätte das bedeutet: der zuletzt abgeschlossene Check überschreibt den anderen, "In TP anwenden" hätte im schlimmsten Fall die falschen Daten geschrieben. Ersetzt durch ein `checkState = {morgen:{...}, abend:{...}}`-Objekt; `showResult`/`buildResult`/`toggleOverride`/`backToForm`/`applyToTP`/`loadTPWorkouts` bekommen alle einen expliziten `type`-Parameter statt auf globale Variablen zu lesen. Zwei eigene Ergebnis-Container (`#result-section-abend`/`-morgen`, je im eigenen `.tab-panel`) statt des einen globalen — auf Mobil bleibt das Verhalten dadurch automatisch identisch (nur ein Panel je aktiv), auf Desktop können beide Checks jetzt unabhängig voneinander laufen, Ergebnis zeigen und einzeln in TP angewendet werden.
- **Eigene Lade-/Fehleranzeige pro Check** (`setCheckLoading`/`setCheckLoadingText`/`showCheckError`, neue `.check-status`/`.check-error`-Elemente je Formular) statt des einen globalen `.loading-overlay`/`#error-banner` — sonst hätten zwei gleichzeitig laufende Checks sich denselben Spinnertext/dieselbe Fehlermeldung streitig gemacht. `runCheck()` bekommt dafür einen optionalen dritten Parameter (`onStage`-Callback), der reine Polling-Body (v2.7.17) bleibt unverändert. Fehler bleiben wie beim alten Banner dauerhaft stehen (kein 8s-Timer) und sind per Antippen schließbar. Der globale Banner/Overlay bleibt für echte seitenweite Ereignisse (Profil-Ladefehler beim Start, Baseline-CSV-Upload) bestehen.

Tests: `test_wiring.py`s Check auf den alten `showError(err.message || String(err), true)`-Aufruf (v2.7.17) ist auf die neue `showCheckError()`-Stelle umgeschrieben — geprüft wird weiterhin dieselbe Eigenschaft (kein Auto-Hide-Timer, Klick-Dismiss), nur an der neuen Stelle.

## Offene Punkte

### Public Release (GitHub, Self-hosted Single-User) — noch nicht begonnen
1. Personal Data raus: `athlete.json` → Template, `setup_complete`-Flag, About-Tab dynamisch
2. **Auth: Google OAuth 2.0** (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS`) — PIN war zu schwach, aktuell gibt es **keinen** Schutz
2b. TP-Cookie-Extractor-Script (`rookiepy`) für Enduser
3. Onboarding-Wizard bei `setup_complete: false`
4. README + „Deploy on Railway"-Button

### MyFitnessPal MCP — explizit auf „später"
MFP MCP auf Railway (`MFP_USERNAME`/`MFP_PASSWORD`), Kalorienbilanz im Abend-Check gegen Trainingsverbrauch.

### Periodische Recherche — aktuell nur manuell auslösbar
Der Recherche-Agent (v2.9.0, siehe Changelog) läuft nur auf Klick im Profil-Tab (oder `curl` gegen `POST /api/research/run`) — es gibt in diesem Repo keinerlei Scheduling-Infrastruktur (kein APScheduler, kein Railway-Cron, nur der einmalige Startup-Prefetch für TP). Für echte Periodizität ("einmal pro Woche automatisch ein Thema recherchieren") bräuchte es einen externen Trigger (separater Railway-Cron-Service, GitHub-Actions-Schedule o.ä.), der den bestehenden Endpoint anstößt — der Agent selbst müsste sich dafür nicht ändern.

### Sicherheit — der MCP-Token schützt nicht die App
Der MCP-Service hat seit v2.7.6 einen Bearer-Token. **Die App selbst hat weiterhin keinen.** Wer die App-URL kennt, kann `POST /api/coach/chat` direkt aufrufen und damit denselben Anthropic-Key verbrennen und dieselben Daten lesen — der MCP-Token ist also nicht die schwächste Stelle, sondern die App. Das bleibt der Google-OAuth-Punkt unten. Der Token liegt außerdem im Klartext in `~/.claude.json` bzw. der Claude-Desktop-Config.

### Technische Altlasten
Die drei hier zuletzt geführten Punkte sind in v2.7.18 abgeräumt. **`pain_thresholds` in `athlete.json` bleibt**, entgegen der früheren Notiz hier: es ist nur im Backend-Prompt ungenutzt, `buildModReason()` im Frontend rechnet damit den MOD-Grund für TrainingPeaks aus.
