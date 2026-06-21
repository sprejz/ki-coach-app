import os
import json
import csv
import io
import statistics
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import anthropic

app = FastAPI()
BASE_DIR = Path(__file__).parent
ATHLETE_FILE = BASE_DIR / "athlete.json"
BASELINE_FILE = BASE_DIR / "baseline.json"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── data helpers ──────────────────────────────────────────────────────────────

def load_athlete() -> dict:
    with open(ATHLETE_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_baseline() -> Optional[dict]:
    if BASELINE_FILE.exists():
        with open(BASELINE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def next_a_race(athlete: dict) -> Optional[dict]:
    today = date.today()
    candidates = [
        r for r in athlete.get("races", [])
        if r.get("priority") == "A" and date.fromisoformat(r["date"]) >= today
    ]
    return min(candidates, key=lambda r: r["date"]) if candidates else None


# ── weather ───────────────────────────────────────────────────────────────────

WMO = {
    0: "Klarer Himmel", 1: "Überwiegend klar", 2: "Teils bewölkt", 3: "Bedeckt",
    45: "Nebel", 48: "Nebel",
    51: "Leichter Nieselregen", 53: "Nieselregen", 55: "Starker Nieselregen",
    61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    71: "Leichter Schnee", 73: "Schnee", 75: "Starker Schnee",
    80: "Leichte Schauer", 81: "Schauer", 82: "Starke Schauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Starkhagel",
}


def parse_weather(raw: dict) -> dict:
    daily = raw.get("daily", {})
    idx = 1 if len(daily.get("time", [])) > 1 else 0
    code = (daily.get("weathercode") or [0])[idx] if idx < len(daily.get("weathercode") or []) else 0
    temp_max = (daily.get("temperature_2m_max") or [None])[idx]
    temp_min = (daily.get("temperature_2m_min") or [None])[idx]
    rain_prob = (daily.get("precipitation_probability_max") or [0])[idx] or 0
    datum = (daily.get("time") or ["?"])[idx]
    return {
        "datum": datum,
        "code": code,
        "description": WMO.get(code, f"Code {code}"),
        "temp_max": temp_max,
        "temp_min": temp_min,
        "rain_prob": rain_prob,
        "is_thunderstorm": code in [95, 96, 99],
        "is_rain": code in [51, 53, 55, 61, 63, 65, 80, 81, 82] or rain_prob > 60,
        "is_hot": temp_max is not None and temp_max > 25,
    }


async def fetch_weather(athlete: dict) -> dict:
    lat = athlete["location"]["lat"]
    lon = athlete["location"]["lon"]
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
        f"&timezone=Europe/Berlin&forecast_days=2"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        return parse_weather(r.json())


# ── AutoSleep CSV ─────────────────────────────────────────────────────────────

def parse_autosleep_csv(content: bytes) -> dict:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV ist leer")
    row = rows[-1]

    def sf(val: Optional[str]) -> Optional[float]:
        try:
            return float(str(val).replace(",", ".").strip()) if val and str(val).strip() else None
        except (ValueError, TypeError):
            return None

    def parse_dur(val: Optional[str]) -> Optional[float]:
        try:
            parts = str(val).split(":")
            if len(parts) == 3:
                return round(int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600, 2)
        except Exception:
            pass
        return None

    return {
        "schlaf_stunden": parse_dur(row.get("Schlafend")),
        "hrv": sf(row.get("SchlafHRV")),
        "wach_bpm": sf(row.get("WachBPM")),
        "schlaf_bpm": sf(row.get("SchlafBPM")),
        "atmung": sf(row.get("AtmungDurchschnitt")),
        "effizienz": sf(row.get("Effizienz")),
    }


def flag_sleep(data: dict, baseline: Optional[dict]) -> dict:
    if baseline is None:
        return {"flags": [], "score": "ok", "data": data}
    flags = []
    hrv = data.get("hrv")
    wach = data.get("wach_bpm")
    schlaf_bpm = data.get("schlaf_bpm")
    atmung = data.get("atmung")
    eff = data.get("effizienz")

    if hrv is not None and hrv <= baseline.get("SchlafHRV", {}).get("flag_low", 29):
        flags.append(f"HRV niedrig ({hrv:.0f}ms ≤ {baseline['SchlafHRV']['flag_low']}ms)")
    if wach is not None and wach >= baseline.get("WachBPM", {}).get("flag_high", 60):
        flags.append(f"WachBPM erhöht ({wach:.0f} ≥ {baseline['WachBPM']['flag_high']})")
    if schlaf_bpm is not None:
        sb = baseline.get("SchlafBPM", {})
        thr = max(sb.get("flag_high", 69), (sb.get("median") or 64.5) + 4.5)
        if schlaf_bpm >= thr:
            flags.append(f"SchlafBPM erhöht ({schlaf_bpm:.0f} ≥ {thr:.0f})")
    if atmung is not None and atmung >= baseline.get("Atmung", {}).get("flag_high", 17.5):
        flags.append(f"Atmung erhöht ({atmung:.1f} ≥ {baseline['Atmung']['flag_high']})")
    if eff is not None and eff < baseline.get("Effizienz", {}).get("flag_low", 82):
        flags.append(f"Effizienz niedrig ({eff:.0f}% < {baseline['Effizienz']['flag_low']}%)")

    return {"flags": flags, "score": "warn" if flags else "ok", "data": data}


# ── Claude system prompt ──────────────────────────────────────────────────────

def build_system_prompt(athlete: dict, baseline: Optional[dict]) -> str:
    a = next_a_race(athlete)
    a_info = f"{a['name']}, {a['date']}, Zielzeit {a.get('goal_total', '?')}h" if a else "kein A-Rennen eingetragen"
    n = athlete.get("nutrition", {})
    heat_thr = n.get("heat_threshold_celsius", 25)
    swim_min = athlete.get("swim_outdoor_min_celsius", 15)

    b_text = ""
    if baseline:
        b_text = (
            f"\nBaseline ({baseline.get('nights', '?')} Nächte, Stand {baseline.get('updated', '?')}):"
            f"\n  SchlafHRV: Median {baseline.get('SchlafHRV', {}).get('median', '?')}ms, Flag ≤{baseline.get('SchlafHRV', {}).get('flag_low', 29)}ms"
            f"\n  WachBPM:   Median {baseline.get('WachBPM', {}).get('median', '?')}, Flag ≥{baseline.get('WachBPM', {}).get('flag_high', 60)}"
            f"\n  SchlafBPM: Median {baseline.get('SchlafBPM', {}).get('median', '?')}, Flag ≥{baseline.get('SchlafBPM', {}).get('flag_high', 69)}"
        )

    return f"""Du bist der KI Coach von {athlete.get('name', 'dem Athleten')}, einem Langdistanz-Triathleten.
A-Rennen: {a_info}
Athletenprofil: {athlete.get('weight_kg', '?')}kg · FTP {athlete.get('ftp_watt', '?')}W · Lauf-Schwelle {athlete.get('run_threshold_pace', '?')}/km · CSS {athlete.get('css_per_100m', '?')}/100m
{b_text}
Ernährung: {n.get('mix', '')} · {n.get('carbs_per_hour_g', 90)}g Carbs/h ab 90 min · {n.get('salt_per_hour', 1)} Saltstick/h · bei Hitze (>{heat_thr}°C): {n.get('fluid_heat_per_hour_ml', 750)}ml/h + {n.get('salt_heat_per_hour', 2)} Saltstick/h
Schwimmen outdoor ab {swim_min}°C Wassertemp, sonst Hallenbad empfehlen.

ENTSCHEIDUNGSLOGIK (Gesamtbewertung wie ein erfahrener Coach — keine sture Regelkette):

HARTE GRENZEN:
- Knie ≥ 3/10 → kein Laufen (Aqua oder Rad als Ersatz)
- Achillessehne > 2/10 → kein Laufen
- Symptome "neu schwer" (Fieber/Körperschmerzen) → komplette Ruhe
- Gewitter → kein Outdoor-Rad

WEICHE SIGNALE (Coach-Urteil):
- gleich leicht / neu leicht: Schwimmen eher SKIP (Chlor), Rad Z2 meist ok, Lauf reduziert möglich
- Muskelkater lokal → betroffene Sportart entlasten, andere normal
- Müdigkeit ≥ 4 → Intensität raus, nicht automatisch streichen
- HRV Einzelwert unter Baseline → Trend 3-5 Tage zählt, nicht überreagieren
- mehrere schwache Signale kombiniert → konservativer entscheiden

SPORTART:
- Schwimmen: sensitiv bei Schnupfen (Chlor), bei Muskelkater Beine ok
- Rad Z2: sehr tolerant — geht fast immer außer Fieber
- Lauf: sensibelste Sportart — Knie, Achilles, Müdigkeit stärker gewichten

WETTER:
- Regen/Gewitter → Rad auf Zwift (75–80% Dauer), Titel "Zwift (KI)", Notiz "wegen Wetter indoor"
- Hitze >{heat_thr}°C → Pace/Watt anpassen, mehr Saltstick + Wasser
- Kälte < {swim_min}°C → Hallenbad

WICHTIG: Schlafdauer NIEMALS als Entscheidungsfaktor — kurze Nächte sind für diesen Athleten normal. Primär: SchlafHRV-Trend + WachBPM.

Antworte NUR als gültiges JSON ohne Markdown-Umrandung:
{{
  "status": "green",
  "status_text": "Alles grün",
  "sportarten": [
    {{"sport": "Schwimmen", "badge": "GO", "details": "konkrete Empfehlung", "ernaehrung": "kurzer Hinweis"}}
  ],
  "autosleep_summary": null,
  "wetter_hinweis": "Wetter-Empfehlung in 1 Satz",
  "prep": "Coach-Kommentar in 1–2 Sätzen"
}}"""


# ── Claude call ───────────────────────────────────────────────────────────────

def call_claude(system: str, user_msg: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY nicht gesetzt")
    c = anthropic.Anthropic(api_key=key)
    msg = c.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner)
    return json.loads(raw)


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/athlete")
async def get_athlete():
    return load_athlete()


@app.post("/api/athlete/update")
async def update_athlete(request: Request):
    data = await request.json()
    with open(ATHLETE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True}


@app.get("/api/baseline")
async def get_baseline():
    b = load_baseline()
    if not b:
        raise HTTPException(404, "Keine Baseline — bitte zuerst CSVs hochladen")
    return b


@app.post("/api/baseline/calculate")
async def calc_baseline(files: List[UploadFile] = File(...)):
    buckets: dict = {k: [] for k in ["SchlafBPM", "WachBPM", "SchlafHRV", "Atmung", "Effizienz"]}
    for f in files:
        content = await f.read()
        try:
            d = parse_autosleep_csv(content)
            if d.get("schlaf_bpm"):  buckets["SchlafBPM"].append(d["schlaf_bpm"])
            if d.get("wach_bpm"):    buckets["WachBPM"].append(d["wach_bpm"])
            if d.get("hrv"):         buckets["SchlafHRV"].append(d["hrv"])
            if d.get("atmung"):      buckets["Atmung"].append(d["atmung"])
            if d.get("effizienz"):   buckets["Effizienz"].append(d["effizienz"])
        except Exception:
            continue

    def med(lst: list) -> Optional[float]:
        return round(statistics.median(lst), 1) if lst else None

    baseline = {
        "SchlafBPM": {"median": med(buckets["SchlafBPM"]), "flag_high": round((med(buckets["SchlafBPM"]) or 64.5) + 4.5, 1)},
        "WachBPM":   {"median": med(buckets["WachBPM"]),   "flag_high": 60},
        "SchlafHRV": {"median": med(buckets["SchlafHRV"]), "flag_low":  29},
        "Atmung":    {"median": med(buckets["Atmung"]),    "flag_high": 17.5},
        "Effizienz": {"median": med(buckets["Effizienz"]), "flag_low":  82},
        "nights":    len(buckets["SchlafHRV"]),
        "updated":   date.today().isoformat(),
    }
    with open(BASELINE_FILE, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    return baseline


@app.post("/api/check-abend")
async def check_abend(request: Request):
    data = await request.json()
    athlete = load_athlete()
    baseline = load_baseline()

    try:
        weather = await fetch_weather(athlete)
    except Exception as e:
        weather = {
            "description": "Wetterdaten nicht verfügbar",
            "temp_max": None, "temp_min": None,
            "rain_prob": 0, "is_thunderstorm": False,
            "is_rain": False, "is_hot": False,
            "error": str(e),
        }

    system = build_system_prompt(athlete, baseline)
    einheiten = data.get("geplante_einheiten", [])
    muskelkater = data.get("muskelkater") or ["keine"]
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")

    user_msg = f"""Abend-Check — Plan für morgen ({tomorrow}):

Fragebogen:
- Knie: {data.get('knie', 0)}/10
- Achillessehne L: {data.get('achilles_l', 0)}/10
- Achillessehne R: {data.get('achilles_r', 0)}/10
- Müdigkeit: {data.get('muedigkeit', 1)}/5
- Muskelkater: {', '.join(muskelkater)}
- Symptome: {data.get('symptome', 'keine')}

Wetter morgen in {athlete['location']['name']}:
- {weather.get('description', 'unbekannt')}, {weather.get('temp_min', '?')}–{weather.get('temp_max', '?')}°C
- Regenrisiko: {weather.get('rain_prob', 0)}%
- Gewitter: {'JA' if weather.get('is_thunderstorm') else 'nein'}
- Hitzealarm (>{athlete.get('nutrition', {}).get('heat_threshold_celsius', 25)}°C): {'JA' if weather.get('is_hot') else 'nein'}
{f"- Wassertemperatur Freibad: {data['wasser_temp']}°C" if data.get('wasser_temp') else ''}

Geplante Einheiten morgen: {', '.join(einheiten) if einheiten else 'noch nicht festgelegt — bitte empfehlen'}"""

    try:
        result = call_claude(system, user_msg)
        result["weather"] = weather
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Ungültiges JSON von Claude: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/check-morgen")
async def check_morgen(
    knie: str = Form("0"),
    achilles_l: str = Form("0"),
    achilles_r: str = Form("0"),
    waden: str = Form("0"),
    symptome: str = Form("keine"),
    geplante_einheiten: str = Form(""),
    csv_file: Optional[UploadFile] = File(None),
):
    athlete = load_athlete()
    baseline = load_baseline()
    system = build_system_prompt(athlete, baseline)

    sleep_text = ""
    sleep_result = None
    if csv_file and csv_file.filename:
        try:
            content = await csv_file.read()
            sd = parse_autosleep_csv(content)
            sleep_result = flag_sleep(sd, baseline)
            d = sd
            flag_str = ", ".join(sleep_result["flags"]) if sleep_result["flags"] else "alle Marker ok"
            sleep_text = f"""
AutoSleep (letzte Nacht):
- SchlafHRV: {d.get('hrv', '?')}ms  WachBPM: {d.get('wach_bpm', '?')}  SchlafBPM: {d.get('schlaf_bpm', '?')}
- Atmung: {d.get('atmung', '?')}  Effizienz: {d.get('effizienz', '?')}%
- Flags: {flag_str}"""
        except Exception as e:
            sleep_text = f"\nAutoSleep Fehler: {e}"

    einheiten_list = [x.strip() for x in geplante_einheiten.split(",") if x.strip()]
    today_str = date.today().strftime("%d.%m.%Y")

    user_msg = f"""Morgen-Check — Go/No-Go für heute ({today_str}):

Fragebogen:
- Waden: {waden}/10
- Knie: {knie}/10
- Achillessehne L: {achilles_l}/10
- Achillessehne R: {achilles_r}/10
- Symptome: {symptome}
{sleep_text}

Geplante Einheiten heute: {', '.join(einheiten_list) if einheiten_list else 'noch nicht festgelegt'}"""

    try:
        result = call_claude(system, user_msg)
        if sleep_result:
            result["sleep_flags"] = sleep_result
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Ungültiges JSON von Claude: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))
