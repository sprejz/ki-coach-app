# KI Coach App — Schritt 1

**Version:** 1.1.3  
**Stand:** 2026-06-20  
**Autor:** Hendrik  
**Änderungen:**
- 1.0.0 — Initiale Version Schritt 1
- 1.0.1 — Entscheidungslogik: Regelkette → Coach-Gesamtbewertung
- 1.0.2 — Athleten-Profil + Baseline dynamisch (athlete.json, baseline.json)
- 1.0.3 — Wettkämpfe dynamisch in athlete.json als Liste
- 1.0.4 — Name dynamisch aus athlete.json
- 1.0.5 — Trainingsort + Koordinaten dynamisch aus athlete.json
- 1.0.6 — Countdown dynamisch zum nächsten A-Rennen
- 1.0.7 — TP_MCP_URL + System-Prompt A-Rennen dynamisch
- 1.0.8 — Ernährungsregeln dynamisch aus athlete.json nutrition Block
- 1.0.9 — Fragebogen-Felder dynamisch aus athlete.json checklist Block
- 1.1.0 — Entscheidungslogik + Coaching-Regeln dynamisch aus athlete.json coaching_rules Block
- 1.1.1 — coaching_rules + checklist zurück hardcoded (kein Laufzeit-Bedarf)
- 1.1.2 — Datenstrategie dokumentiert: Railway ENV nur für Secrets, athlete.json per App-Formular
- 1.1.3 — Coach Skill (felixrieseberg/claude-coach) als optionale Schritt-2-Integration dokumentiert

---

## Ziel
iPhone-optimierte Progressive Web App (PWA) für den täglichen Triathlon-Coaching-Workflow aus athlete.json (A-Rennen und Zielzeit werden dynamisch aus athlete.json geladen).

## Architektur
- **Backend:** Python FastAPI
- **Frontend:** Single HTML-Datei, iPhone-optimiert (320–390px Breite)
- **Hosting:** Railway (Docker)
- **APIs:** Claude API (claude-sonnet-4-6) für Auswertung, Open-Meteo für Wetter, TrainingPeaks MCP über Railway

## Umgebungsvariablen (Railway — nur Secrets und Infrastruktur)
- `ANTHROPIC_API_KEY` — Claude API Key (Sicherheit)
- `TP_MCP_URL` — TrainingPeaks MCP URL (wird als Umgebungsvariable gesetzt, nicht hardcoded)
- `PORT` — Railway setzt automatisch

## Datenstrategie — wo was gespeichert wird

| Was | Wo | Wie ändern |
|---|---|---|
| API Keys, URLs | Railway ENV | Railway Dashboard |
| Name, Ort, FTP, Zonen, Rennen, Ernährung | `athlete.json` | App-Einstellungsseite (Formular) |
| AutoSleep-Baseline | `baseline.json` | CSV-Upload → `/baseline/calculate` |
| Coaching-Logik, Fragebogen, Design | hardcoded im Code | neues Deployment |

**Wichtig:** Railway ENV-Vars erfordern immer einen Redeploy — daher nur für Secrets geeignet, nicht für Athleten-Daten.

---

## Zwei Workflows

### 1. check-abend (Abend-Check)
Wird abends durchgeführt — plant den nächsten Tag.

**Ablauf:**
1. Wetter für morgen abrufen (Open-Meteo API, Koordinaten aus athlete.json: location.lat/lon)
2. Fragebogen (Felder dynamisch aus athlete.json — checklist.abend)
3. Claude API wertet aus → gibt Empfehlung + angepassten Plan zurück
4. Ausgabe als Dark Card (Style-A, siehe Design)
5. Optional: Bei Schwimmeinheit → nach Wassertemperatur fragen → in Note eintragen

### 2. check-morgen (Morgen-Override)
Wird morgens vor dem Training durchgeführt.

**Ablauf:**
1. AutoSleep CSV Upload (optional)
2. Fragebogen (Felder dynamisch aus athlete.json — checklist.morgen)
3. Claude API wertet aus → Go/No-Go Entscheidung
4. Ausgabe als Dark Card

---

## Entscheidungslogik (hardcoded im Code — ändert sich nur per Deployment)

Die Entscheidung ist KEINE isolierte Regelkette, sondern eine **Gesamtbewertung** aller Signale.
Claude denkt wie ein erfahrener Coach — Kontext beachten, nicht stur Regeln abarbeiten.

### Harte Grenzen (immer einhalten)
- Knie ≥ 3/10 → kein Laufen (Aqua oder Rad als Ersatz)
- Achillessehne > 2/10 → kein Laufen
- Symptome neu schwer (Fieber/Körperschmerzen) → komplette Ruhe
- Gewitter → kein Outdoor-Rad

### Weiche Signale (Coach-Urteil)
- Gleich leicht / neu leicht: Schwimmen eher SKIP, Rad Z2 meist ok, Lauf reduziert möglich
- Muskelkater lokal → betroffene Sportart entlasten, andere normal
- Müdigkeit ≥ 4 → Intensität raus, nicht automatisch streichen
- HRV einzelner Wert unter Baseline → Trend 3–5 Tage zählt, nicht überreagieren
- Mehrere schwache Signale kombiniert → konservativer entscheiden

### Sportart-spezifisch
- **Schwimmen:** Bei Schnupfen eher SKIP (Chlor), bei Muskelkater Beine ok
- **Rad Z2:** Sehr tolerant — geht fast immer außer Fieber
- **Lauf:** Sensibelste Sportart — Knie, Achilles, Müdigkeit stärker gewichten

### Wetter (Koordinaten aus athlete.json)
- Regen/Gewitter → Rad auf Zwift, Dauer auf 75–80% kürzen
- Hitze > swim_outdoor_min aus athlete.json → Pace/Watt anpassen, mehr Saltstick/Wasser
- Kälte < swim_outdoor_min_celsius aus athlete.json → Hallenbad

### Fragebogen-Felder (hardcoded)
**Abend:** Knie (0–10) · Achillessehne L (0–10) · Achillessehne R (0–10) · Müdigkeit (1–5) · Muskelkater (Auswahl) · Symptome (Auswahl)

**Morgen:** Waden (0–10) · Knie (0–10) · Achillessehne L (0–10) · Achillessehne R (0–10) · Symptome (Auswahl)

**Symptom-Optionen:** keine / besser / gleich leicht (Schnupfen/Kopfdruck) / schlechter / neu leicht / neu mittel (Halsschmerzen/Husten) / neu schwer (Fieber/Körperschmerzen)

### Indoor (Zwift)
- Immer auf 75–80% der Outdoor-Dauer kürzen (kein Fahrtwind, konstante Belastung)
- Titel: "Zwift (KI)" + Notiz "wegen Wetter indoor"

---

## AutoSleep CSV Auswertung

### Baseline — dynamisch aus baseline.json
Die Baseline wird NICHT hardcoded gespeichert, sondern in einer Datei `baseline.json` im App-Verzeichnis.

**baseline.json Format:**
```json
{
  "SchlafBPM":    {"median": 64.5, "flag_high": 69},
  "WachBPM":      {"median": 55.0, "flag_high": 60},
  "SchlafHRV":    {"median": 35.0, "flag_low": 29},
  "Atmung":       {"median": 15.8, "flag_high": 17.5},
  "Effizienz":    {"median": 92.0, "flag_low": 82},
  "nights":       153,
  "updated":      "2026-06-15"
}
```

**Baseline berechnen:** Ein separater Endpoint `POST /baseline/calculate` nimmt mehrere AutoSleep CSVs entgegen, berechnet den Median pro Marker und schreibt `baseline.json`. Wird nur auf Anforderung ausgeführt (nicht täglich).

**Täglicher Check:** Nur die aktuelle CSV wird mit der gespeicherten Baseline verglichen.

**Flag-Schwellen** (fest, nicht aus CSV):
- SchlafBPM ≥ baseline + 4.5 oder ≥ 69
- WachBPM ≥ 60
- SchlafHRV ≤ 29 (Hauptmarker!)
- Atmung ≥ 17.5
- Effizienz < 82%

**Wichtig:** Schlafdauer NIEMALS als Entscheidungsfaktor verwenden — kurze Nächte sind für diesen Athleten normal. Primäre Marker: SchlafHRV-Trend (7-Tage) + WachBPM.

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
- Countdown bis zum nächsten A-Rennen (dynamisch aus athlete.json)
- Status-Pill (Alles grün / Angepasst / Gestrichen)
- AutoSleep Übersicht (falls CSV hochgeladen)
- Wetter morgen für {athlete.location.name} (Temp, Regenrisiko, Empfehlung)
- Metriken-Grid: TSS / Müdigkeit / Knie + CTL / ATL / TSB
- Workout-Liste mit GO/MOD/SKIP Badges
- Prep-Zeile (Coach-Hinweis)

---

## Ernährung (dynamisch aus athlete.json — nutrition Block)

Die Ernährungsempfehlungen werden aus `athlete.json` geladen und automatisch in die Empfehlung eingebaut.

**athlete.json nutrition Block:**
```json
"nutrition": {
  "mix": "Maltodextrin 19 + Fruchtzucker 2:1",
  "carbs_per_hour_g": 90,
  "fluid_per_hour_ml": 600,
  "fluid_heat_per_hour_ml": 750,
  "salt_per_hour": 1,
  "salt_heat_per_hour": 2,
  "heat_threshold_celsius": 25,
  "rules": [
    {
      "duration_max_min": 60,
      "before": "Nüchtern oder kleines Frühstück",
      "during": "Wasser reicht",
      "after": "Normale Mahlzeit binnen 1h"
    },
    {
      "duration_min_min": 60,
      "duration_max_min": 90,
      "before": "Leichtes Frühstück 2h vorher",
      "during": "Wasser reicht",
      "after": "Mahlzeit binnen 1h"
    },
    {
      "duration_min_min": 90,
      "duration_max_min": 180,
      "before": "KH-reiches Frühstück 2h vorher",
      "during": "{carbs_per_hour_g}g Carbs/h ({mix}) + {salt_per_hour} Saltstick/h",
      "after": "25g Protein + Carbs binnen 30 min"
    },
    {
      "duration_min_min": 180,
      "before": "Renntag-Protokoll: 100g Carbs (wenig Ballaststoffe) 2h vorher",
      "during": "{carbs_per_hour_g}g Carbs/h + {salt_per_hour}–{salt_heat_per_hour} Saltstick/h",
      "after": "Recovery-Mahlzeit binnen 30 min"
    }
  ]
}
```

---

## Athleten-Profil — dynamisch aus athlete.json

Alle Leistungswerte werden in `athlete.json` gespeichert und können über einen Endpoint `POST /athlete/update` aktualisiert werden (z.B. nach einem Rennen oder FTP-Test).

**athlete.json Format:**
```json
{
  "name": "Hendrik",  // wird überall in der App dynamisch verwendet
  "location": {
    "name": "Ludwigsfelde",
    "lat": 52.30,
    "lon": 13.25
  },
  "weight_kg": 84,
  "ftp_watt": 286,
  "run_threshold_pace": "5:20",
  "css_per_100m": "2:20",
  "threshold_hr_bike": 145,
  "threshold_hr_run": 150,
  "races": [
    {
      "name": "Altmark-Triathlon",
      "date": "2026-07-12",
      "priority": "B",
      "distance": "Olympisch"
    },
    {
      "name": "GEWOBA Bremen",
      "date": "2026-08-09",
      "priority": "B",
      "distance": "70.3"
    },
    {
      "name": "Castle Triathlon Malbork",
      "date": "2026-09-06",
      "priority": "A",
      "distance": "Langdistanz",
      "goal_total": "10:50",
      "goal_swim": "1:20",
      "goal_bike": "5:20",
      "goal_run": "4:01"
    }
  ],
  "zones_bike_hr": {
    "z1_max": 117,
    "z2_min": 117, "z2_max": 130,
    "z3_min": 131, "z3_max": 137,
    "z4_min": 138, "z4_max": 145,
    "z5_min": 146
  },
  "zones_run_pace": {
    "z1_slower_than": "6:30",
    "z2": "6:00-6:30",
    "z3": "5:45-6:00",
    "z4": "5:10-5:30"
  },
  "updated": "2026-06-20"
}
}
```

**Countdown:** Die App berechnet den Countdown automatisch zum nächsten A-Rennen aus `races`. Alle Rennen werden in der App angezeigt.

**Aktualisierung:** Nach jedem Rennen oder FTP-Test per `POST /athlete/update` aktualisieren.

---

## Scope Schritt 1 (jetzt bauen)
- Fragebogen (check-abend + check-morgen)
- Wetter abrufen (Open-Meteo)
- AutoSleep CSV Upload + Auswertung
- Claude API Auswertung → Dark Card Ausgabe
- athlete.json + baseline.json dynamisch laden
- iPhone-optimiertes Design

**NICHT in Schritt 1:**
- Keine TrainingPeaks-Änderungen (kein Workout erstellen/anpassen)
- Kein direkter TP-Datenabruf (TSS, CTL, ATL, TSB)
- Kein PWA Manifest

## Schritt 2 (später)
- TrainingPeaks MCP Integration: Workouts abrufen, anpassen, erstellen, Notes setzen
- TP_MCP_URL: wird als Umgebungsvariable gesetzt, nicht hardcoded
- Stündliche Regenprognose (Wetter-Proxy auf Railway)
- PWA Manifest für iPhone Homescreen Bookmark
- Coach Skill Integration: Der `coach` Skill (felixrieseberg/claude-coach) kann für Trainingsplan-Generierung, Zonenanalyse und tiefere Leistungsauswertung genutzt werden — bei Bedarf in Schritt 2 einbinden

---

## Dateistruktur
```
ki-coach-app/
├── CLAUDE.md          ← diese Datei
├── app.py             ← FastAPI Backend
├── templates/
│   └── index.html     ← Frontend (iPhone-optimiert)
├── Dockerfile
└── railway.toml
```

---

## Dark Card Inhalt (Schritt 1 — ohne TP-Daten)
- Countdown bis zum nächsten A-Rennen (dynamisch aus athlete.json)
- Status-Pill (Alles grün / Angepasst / Gestrichen)
- AutoSleep Übersicht (nur falls CSV hochgeladen): SchlafHRV, WachBPM, Flags
- Wetter morgen für {athlete.location.name} (Temp, Regenrisiko, Empfehlung)
- Metriken-Grid: Müdigkeit / Knie / Achilles (KEIN TSS/CTL/ATL/TSB in Schritt 1)
- Coach-Empfehlung mit GO/MOD/SKIP Badges pro Sportart
- Ernährungshinweis passend zur geplanten Einheitsdauer
- Prep-Zeile (Coach-Hinweis in 1–2 Sätzen)

---

## Claude API System-Prompt (für Auswertung)

```
Du bist der KI Coach von {athlete.name}, einem Langdistanz-Triathleten.
A-Rennen: {athlete.races[priority=A].name}, {athlete.races[priority=A].date}, Zielzeit {athlete.races[priority=A].goal_total}h.

Du bekommst:
- Fragebogen-Werte (Knie, Achilles, Müdigkeit, Muskelkater, Symptome)
- Wetterdaten für morgen (Temperatur, Regenrisiko, stündlich)
- Optional: AutoSleep-Daten (SchlafHRV, WachBPM, Flags)
- Athleten-Profil (aus athlete.json)
- Baseline (aus baseline.json)

Deine Aufgabe:
1. Bewerte den Gesamtzustand wie ein erfahrener Coach — keine sture Regelkette
2. Entscheide für jede geplante Sportart: GO / MOD / SKIP
3. Gib konkrete Empfehlung (Dauer, Intensität, Besonderheiten)
4. Berücksichtige Wetter (Hitze, Regen, Gewitter → Zwift)
5. Ernährungshinweis passend zur Einheitsdauer
6. Prep-Zeile: 1–2 Sätze Coach-Kommentar

Antworte NUR als JSON:
{
  "status": "green" | "orange" | "red",
  "status_text": "Alles grün" | "Angepasst" | "Gestrichen",
  "sportarten": [
    {
      "sport": "Schwimmen" | "Rad" | "Lauf" | "STABI",
      "badge": "GO" | "MOD" | "SKIP",
      "details": "konkrete Empfehlung",
      "ernaehrung": "kurzer Hinweis"
    }
  ],
  "autosleep_summary": "kurze Zusammenfassung falls Daten vorhanden, sonst null",
  "wetter_hinweis": "Wetter-Empfehlung in 1 Satz",
  "prep": "Coach-Kommentar in 1–2 Sätzen"
}
```
