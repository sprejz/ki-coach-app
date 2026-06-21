# KI Coach App — v2.1.0

## Ziel
iPhone-optimierte Progressive Web App (PWA) für den täglichen Triathlon-Coaching-Workflow von Hendrik Sprejz (Castle Triathlon Malbork, 6.9.2026, Zielzeit 10:50h).

## Architektur
- **Backend:** Python FastAPI
- **Frontend:** Single HTML-Datei, iPhone-optimiert (320–390px Breite)
- **Hosting:** Railway (Docker)
- **APIs:** Claude API (claude-sonnet-4-6) für Auswertung, Open-Meteo für Wetter, TrainingPeaks MCP über Railway

## Umgebungsvariablen (Railway)
- `ANTHROPIC_API_KEY` — Claude API Key
- `TP_MCP_URL` — TrainingPeaks MCP URL: `https://trainingpeaks-mcp-production-1a4f.up.railway.app/mcp`
- `PORT` — Railway setzt automatisch

---

## Zwei Workflows

### 1. check-abend (Abend-Check)
Wird abends durchgeführt — plant den nächsten Tag.

**Ablauf:**
1. AutoSleep CSV Upload (optional) → Parsing und Auswertung
2. Wetter für morgen in Ludwigsfelde abrufen (Open-Meteo API, Koordinaten: 52.30°N, 13.25°O)
3. Fragebogen (5 Felder):
   - Knie: 0–10 (Slider oder Buttons)
   - Achillessehne links: 0–10
   - Achillessehne rechts: 0–10
   - Müdigkeit: 1–5
   - Muskelkater: keine / Beine leicht / Beine stark / Oberkörper / überall
   - Krankheitssymptome: keine / besser / gleich leicht (Schnupfen/Kopfdruck) / schlechter / neu leicht / neu mittel / neu schwer
4. Claude API wertet aus → gibt Empfehlung + angepassten Plan zurück
5. Ausgabe als Dark Card (Style-A, siehe Design)
6. Optional: Bei Schwimmeinheit → nach Wassertemperatur fragen → in Note eintragen

### 2. check-morgen (Morgen-Override)
Wird morgens vor dem Training durchgeführt.

**Ablauf:**
1. AutoSleep CSV Upload (optional)
2. Fragebogen (5 Felder):
   - Waden: 0–10
   - Knie: 0–10
   - Achillessehne links: 0–10
   - Achillessehne rechts: 0–10
   - Symptome: keine / besser / gleich leicht / schlechter / neu leicht / neu mittel / neu schwer
3. Claude API wertet aus → Go/No-Go Entscheidung
4. Ausgabe als Dark Card

---

## Entscheidungsregeln (für Claude API Prompt)

### Symptome
- **keine / besser** → planmäßig
- **gleich leicht / neu leicht** → angepasst: Schwimmen SKIP, Rad/Lauf max 45/30 min Z1–Z2
- **schlechter / neu mittel / neu schwer** → Training gestrichen

### Körper
- Knie ≥ 3 → Lauf SKIP, auf Rad/Aqua umstellen
- Achillessehne > 2/10 → Lauf SKIP
- Muskelkater lokal → betroffene Sportart entlasten
- Müdigkeit ≥ 4 + schlechte Metriken → Intensität raus

### Wetter (Ludwigsfelde)
- Regen/Gewitter → Rad auf Zwift (Indoor), Dauer auf 75% kürzen
- Hitze > 25°C → Pace/Watt anpassen, 2 Saltstick/h, 750ml/h Flüssigkeit
- Kälte < 10°C → Freibad auf Hallenbad prüfen

### Indoor (Zwift)
- Immer auf 75–80% der Outdoor-Dauer kürzen
- Titel: "Zwift (KI)"

---

## AutoSleep CSV Auswertung

### Baseline (153 Nächte, 1.1.–15.6.2026)
| Marker | Baseline | Flag |
|---|---|---|
| Schlaf | 8,2h | — (nicht als Entscheidungsfaktor nutzen!) |
| SchlafBPM | 64,5 | ≥ 69 |
| WachBPM | 55 | ≥ 60 |
| SchlafHRV | 35ms | ≤ 29 (Hauptmarker!) |
| Atmung | 15,8/min | ≥ 17,5 |
| Effizienz | 92% | < 82% |

**Wichtig:** Schlafdauer NIEMALS als Entscheidungsfaktor verwenden — kurze Nächte sind bei Hendrik normal. Primäre Marker: SchlafHRV-Trend + WachBPM.

### CSV-Spalten (Deutsch)
- `Schlafend` → Schlafdauer (HH:MM:SS → in Stunden umrechnen)
- `SchlafHRV` → HRV in ms
- `WachBPM` → Ruhepuls wach
- `SchlafBPM` → Herzrate im Schlaf
- `AtmungDurchschnitt` → Atemfrequenz
- `Effizienz` → Schlafeffizienz in %

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

### Status-Badges
- `GO` → grün (#1D9E75)
- `MOD` / `Angepasst` → orange (#EF9F27)
- `SKIP` → rot (#E24B4A)

### Dark Card Inhalt
- Countdown bis Malbork (6.9.2026)
- Status-Pill (Alles grün / Angepasst / Gestrichen)
- AutoSleep Übersicht (falls CSV hochgeladen)
- Wetter morgen (Temp, Regenrisiko, Empfehlung)
- Metriken-Grid: TSS / Müdigkeit / Knie + CTL / ATL / TSB
- Workout-Liste mit GO/MOD/SKIP Badges
- Prep-Zeile (Coach-Hinweis)

---

## Ernährung (automatisch in Empfehlung einbauen)

| Dauer | Empfehlung |
|---|---|
| < 60 min | Nüchtern oder kleines Frühstück, danach normale Mahlzeit |
| 60–90 min | Leichtes Frühstück 2h vorher, Wasser reicht |
| 90 min – 3h | KH-Frühstück 2h vorher, 90g Carbs/h + 1 Saltstick/h während, 25g Protein nachher |
| > 3h | Renntag-Protokoll: 100g Carbs 2h vorher, 90g/h + 1–2 Saltstick/h, Recovery-Mahlzeit |

**Eigenes Gemisch:** Maltodextrin 19 + Fruchtzucker 2:1, 90g Carbs/h, 600–750ml/h Wasser.

---

## Athleten-Profil
- **Name:** Hendrik Sprejz
- **Gewicht:** 84 kg
- **FTP:** 286W (Rad)
- **Laufschwelle:** 5:20/km
- **CSS Schwimmen:** 2:20/100m
- **A-Rennen:** Castle Triathlon Malbork, 6.9.2026
- **Zielzeit:** 10:50h (Swim 1:20h / Bike 5:20h / Run 4:01h)

## HR-Zonen Rad (Schwellen-HF ~145)
- Z1: < 117
- Z2: 117–130
- Z3: 131–137
- Z4: 138–145
- Z5: 146+

## HR-Zonen Lauf (~5 bpm höher)
- Z1: > 6:30/km
- Z2: 6:00–6:30/km
- Z3: 5:45–6:00/km
- Z4: 5:10–5:30/km

---

## Changelog

### v2.0.0 — Schritt 2
- **Stündliche Regenprognose:** Open-Meteo `hourly=precipitation_probability,temperature_2m`, gefiltert auf 6–20 Uhr morgen. Regenspitzen (≥30%) gehen als Kontext in Claude-Prompt. Result-Card: Balkendiagramm pro Stunde (grün/orange/rot).
- **TrainingPeaks MCP Integration:** Claude MCP Connector (`betas=["mcp-client-2025-11-20"]`). `GET /api/tp/workouts` → morgen's Workouts; `POST /api/tp/apply` → SKIP/MOD/GO in TP anwenden (Titel, Notizen, Zwift-Umbenennung). TP_MCP_URL als Railway ENV; gibt `{"available":false}` wenn nicht gesetzt. Abend-Check: "Workouts für morgen laden" Button auto-selektiert Sportarten und schickt TP-Kontext an Claude.
- **PWA Manifest:** `GET /manifest.json` (standalone, dark theme), `<link rel="manifest">`, `<meta name="theme-color">` in HTML.
- **anthropic** auf `>=0.40.0` angehoben (MCP connector beta support).

### v2.1.0 — Profil & Baseline UI
- **Profil-Tab (3. Tab "Profil"):** FTP, Gewicht, Laufschwelle, CSS, Outdoor-Schwimmtemperatur direkt in der App bearbeitbar. Speichern → `POST /api/athlete/update` → Header-Countdown aktualisiert sich. Rennen-Liste (A/B, Datum, Zielzeit) wird angezeigt.
- **Baseline-Manager (im Profil-Tab):** Aktuelle Baseline-Werte (HRV, WachBPM, SchlafBPM, Atmung, Effizienz) mit Median + Flag-Schwellen angezeigt. Mehrere AutoSleep CSVs hochladen → `POST /api/baseline/calculate` → Baseline wird sofort aktualisiert und neu angezeigt.

---

## Dateistruktur
```
ki-coach-app/
├── CLAUDE.md          ← diese Datei (v2.1.0)
├── app.py             ← FastAPI Backend
├── templates/
│   └── index.html     ← Frontend (iPhone-optimiert, 3 Tabs)
├── athlete.json       ← Athletenprofil (editierbar über Profil-Tab)
├── baseline.json      ← Schlaf-Baseline (berechenbar über Profil-Tab)
├── Dockerfile
└── railway.toml
```
