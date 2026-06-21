import asyncio
import os
import json
import csv
import io
import logging
import statistics
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import anthropic

from translations import TRANSLATIONS

APP_VERSION = "2.4.3"
APP_LANG = os.environ.get("APP_LANG", "de")
T = TRANSLATIONS.get(APP_LANG, TRANSLATIONS["de"])
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI()
BASE_DIR = Path(__file__).parent

# ── shared HTTP clients (connection pooling) ──────────────────────────────────
_weather_http = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0),
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)
_tp_http = httpx.Client(
    timeout=httpx.Timeout(15.0),
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)
ATHLETE_FILE = BASE_DIR / "athlete.json"
BASELINE_FILE = BASE_DIR / "baseline.json"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.middleware("http")
async def no_cache_api(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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


def parse_weather(raw: dict, day: int = 1) -> dict:
    daily = raw.get("daily", {})
    available = len(daily.get("time", []))
    idx = min(day, available - 1) if available > 0 else 0
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


def parse_hourly(raw: dict, day: int = 1) -> list:
    target = (date.today() + timedelta(days=day)).isoformat()
    hourly = raw.get("hourly", {})
    times = hourly.get("time", [])
    rain_probs = hourly.get("precipitation_probability", [])
    temps = hourly.get("temperature_2m", [])
    result = []
    for i, t in enumerate(times):
        if not t.startswith(target):
            continue
        hour = int(t[11:13])
        if 6 <= hour <= 20:
            result.append({
                "hour": hour,
                "rain": rain_probs[i] if i < len(rain_probs) else 0,
                "temp": round(temps[i], 1) if i < len(temps) and temps[i] is not None else None,
            })
    return result


async def fetch_weather(athlete: dict, day: int = 1) -> dict:
    lat = athlete["location"]["lat"]
    lon = athlete["location"]["lon"]
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
        f"&hourly=precipitation_probability,temperature_2m"
        f"&timezone=Europe/Berlin&forecast_days=2"
    )
    logger.info("fetch_weather: day=%s lat=%s lon=%s", day, lat, lon)
    r = await _weather_http.get(url)
    r.raise_for_status()
    raw = r.json()
    daily_dates = raw.get("daily", {}).get("time", [])
    logger.info("fetch_weather ok: daily_dates=%s", daily_dates)
    result = parse_weather(raw, day=day)
    result["hourly"] = parse_hourly(raw, day=day)
    logger.info("fetch_weather parsed: datum=%s temp=%s-%s hourly=%d",
                result.get("datum"), result.get("temp_min"), result.get("temp_max"), len(result.get("hourly", [])))
    return result


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
        b_text = T["prompt_system_baseline"].format(
            nights=baseline.get("nights", "?"),
            updated=baseline.get("updated", "?"),
            hrv_med=baseline.get("SchlafHRV", {}).get("median", "?"),
            hrv_flag=baseline.get("SchlafHRV", {}).get("flag_low", 29),
            wach_med=baseline.get("WachBPM", {}).get("median", "?"),
            wach_flag=baseline.get("WachBPM", {}).get("flag_high", 60),
            schlaf_med=baseline.get("SchlafBPM", {}).get("median", "?"),
            schlaf_flag=baseline.get("SchlafBPM", {}).get("flag_high", 69),
        )

    return T["prompt_system"].format(
        name=athlete.get("name", "dem Athleten"),
        a_info=a_info,
        weight=athlete.get("weight_kg", "?"),
        ftp=athlete.get("ftp_watt", "?"),
        run_thr=athlete.get("run_threshold_pace", "?"),
        css=athlete.get("css_per_100m", "?"),
        b_text=b_text,
        carbs=n.get("carbs_per_hour_g", 90),
        salt=n.get("salt_per_hour", 1),
        heat_thr=heat_thr,
        fluid_heat=n.get("fluid_heat_per_hour_ml", 750),
        salt_heat=n.get("salt_heat_per_hour", 2),
    )


# ── Claude call ───────────────────────────────────────────────────────────────

def call_claude(system: str, user_msg: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY nicht gesetzt")
    c = anthropic.Anthropic(api_key=key)
    msg = c.messages.create(
        model="claude-haiku-4-5-20251001",
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


def call_claude_tp_mcp(user_content: str) -> str:
    tp_url = os.environ.get("TP_MCP_URL", "")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY nicht gesetzt")
    c = anthropic.Anthropic(api_key=key, http_client=_tp_http)
    try:
        msg = c.beta.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            betas=["mcp-client-2025-11-20"],
            mcp_servers=[{"type": "url", "url": tp_url, "name": "trainingpeaks"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "trainingpeaks"}],
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIStatusError as e:
        body = getattr(e, "body", None) or {}
        detail = (body.get("error", {}).get("message", "") if isinstance(body, dict) else "") or getattr(e, "message", "")
        logger.error("TP MCP APIStatusError %s: body=%s", e.status_code, body)
        raise HTTPException(502, f"TrainingPeaks MCP {e.status_code}: {detail or str(e)}")
    except anthropic.APIConnectionError as e:
        logger.error("TP MCP connection error: %s", e)
        raise HTTPException(502, f"TrainingPeaks MCP nicht erreichbar: {e}")
    except Exception as e:
        logger.error("TP MCP unexpected error: %s %s", type(e).__name__, e)
        raise HTTPException(502, f"TrainingPeaks MCP Fehler: {e}")

    mcp_errors = []
    for block in msg.content:
        if hasattr(block, "text") and block.text:
            return block.text
        if getattr(block, "is_error", False):
            content = getattr(block, "content", "")
            if isinstance(content, list):
                content = " ".join(getattr(c, "text", str(c)) for c in content)
            mcp_errors.append(str(content)[:300])

    if mcp_errors:
        raise HTTPException(502, f"TrainingPeaks Fehler: {'; '.join(mcp_errors)}")
    return ""


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "T": T,
            "T_json": json.dumps(T, ensure_ascii=False),
            "LANG": APP_LANG,
        },
    )


@app.get("/api/version")
async def api_version():
    return {"version": APP_VERSION}


@app.get("/api/startup")
async def startup_data():
    athlete = load_athlete()

    async def safe_weather(day_offset: int):
        try:
            return await fetch_weather(athlete, day=day_offset)
        except Exception as e:
            logger.error("startup weather day=%d: %s", day_offset, e)
            return None

    w_today, w_tomorrow = await asyncio.gather(
        safe_weather(0),
        safe_weather(1),
    )
    return JSONResponse({
        "weather_today":    w_today,
        "weather_tomorrow": w_tomorrow,
    }, headers=_NO_CACHE)


@app.get("/manifest.json")
async def manifest_json():
    return JSONResponse(
        {
            "name": "KI Coach",
            "short_name": "KI Coach",
            "description": "Triathlon Tagescoaching",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f0f13",
            "theme_color": "#1D9E75",
        },
        media_type="application/manifest+json",
    )


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


@app.get("/api/weather")
async def get_weather(day: str = "tomorrow"):
    athlete = load_athlete()
    day_offset = 0 if day == "today" else 1
    try:
        return await fetch_weather(athlete, day=day_offset)
    except httpx.HTTPStatusError as e:
        logger.error("Open-Meteo HTTP %s: %s", e.response.status_code, e.response.text[:300])
        raise HTTPException(503, f"Open-Meteo Fehler {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error("Open-Meteo Verbindungsfehler: %s %s", type(e).__name__, e)
        raise HTTPException(503, "Open-Meteo nicht erreichbar")
    except Exception as e:
        logger.error("Wetterfehler: %s", e)
        raise HTTPException(500, str(e))


def _tp_call_sync(athlete: dict, day_offset: int) -> dict:
    """Synchronous TP fetch — runs in asyncio.to_thread for parallel startup."""
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        return {"available": False, "workouts": [], "date": None}
    target = (date.today() + timedelta(days=day_offset)).isoformat()
    prompt = T["tp_workouts_prompt"].format(name=athlete.get("name", "the athlete"), date=target)
    try:
        raw = call_claude_tp_mcp(prompt)
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        workouts = json.loads(raw)
        logger.info("_tp_call_sync ok: %d workouts day_offset=%d", len(workouts), day_offset)
        return {"available": True, "workouts": workouts, "date": target}
    except json.JSONDecodeError:
        logger.error("_tp_call_sync JSON error raw=%s", raw[:200])
        return {"available": True, "workouts": [], "date": target}
    except HTTPException as e:
        logger.error("_tp_call_sync HTTPException: %s", e.detail)
        return {"available": False, "workouts": [], "date": target, "error": e.detail}
    except Exception as e:
        logger.error("_tp_call_sync error: %s", e)
        return {"available": False, "workouts": [], "date": target, "error": str(e)[:200]}


_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/api/tp/workouts")
async def tp_workouts(day: str = "tomorrow"):
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        return JSONResponse({"available": False, "workouts": [], "date": None}, headers=_NO_CACHE)
    day_offset = 0 if day == "today" else 1
    target = (date.today() + timedelta(days=day_offset)).isoformat()
    athlete = load_athlete()
    logger.info("tp_workouts: day=%s target=%s", day, target)
    prompt = T["tp_workouts_prompt"].format(name=athlete.get("name", "the athlete"), date=target)
    try:
        raw = call_claude_tp_mcp(prompt)
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        workouts = json.loads(raw)
        logger.info("tp_workouts ok: %d workouts for %s", len(workouts), target)
        return JSONResponse({"available": True, "workouts": workouts, "date": target}, headers=_NO_CACHE)
    except json.JSONDecodeError:
        logger.error("tp_workouts JSON decode error, raw=%s", raw[:300])
        return JSONResponse({"available": True, "workouts": [], "date": target, "raw": raw[:300]}, headers=_NO_CACHE)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/tp/apply")
async def tp_apply(request: Request):
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        raise HTTPException(400, "TP_MCP_URL nicht konfiguriert")
    body = await request.json()
    workouts        = body.get("workouts", [])
    recommendation  = body.get("recommendation", {})
    day             = body.get("day", "tomorrow")
    form_data       = body.get("form_data", {})
    athlete         = load_athlete()
    day_offset      = 0 if day == "today" else 1
    target_date     = (date.today() + timedelta(days=day_offset)).isoformat()

    # Form snapshot
    knie        = form_data.get("knie", "-")
    ach_l       = form_data.get("achilles_l", "-")
    ach_r       = form_data.get("achilles_r", "-")
    muedigkeit  = form_data.get("muedigkeit", "-")
    muskelkater = form_data.get("muskelkater", "-")
    symptome    = form_data.get("symptome", "-")
    wetter_temp = form_data.get("wetter_temp", "-")

    # Achilles: max of L/R
    try:
        max_ach = max(float(ach_l), float(ach_r))
        ach_str = str(int(max_ach) if max_ach == int(max_ach) else max_ach)
    except (ValueError, TypeError):
        ach_str = f"L{ach_l}/R{ach_r}"

    athlete_note = T["tp_note_fmt"].format(
        wetter_temp=wetter_temp,
        muedigkeit=muedigkeit,
        knie=knie,
        achilles=ach_str,
        muskelkater=muskelkater,
        symptome=symptome,
    )

    # Build structured operation list — only for workouts that actually exist in TP
    ops: list = []
    for s in recommendation.get("sportarten", []):
        sport   = s.get("sport", "?")
        badge   = s.get("badge", "GO")
        details = s.get("details", "")

        tp_w = next((w for w in workouts if w.get("sport", "").lower() == sport.lower()), None)
        if tp_w is None:
            continue  # not in TP — skip entirely

        orig_title    = tp_w.get("title", sport)
        orig_duration = tp_w.get("duration_min", 60)
        workout_id    = tp_w.get("id")

        rename_op = {"action": "rename_workout", "sport": sport, "date": target_date,
                     "old_title": orig_title}
        if workout_id:
            rename_op["workout_id"] = workout_id

        if badge == "MOD":
            rename_op["new_title"] = T["tp_mod_renamed"].format(title=orig_title)
            ops.append(rename_op)
            ops.append({"action": "create_workout", "sport": sport, "date": target_date,
                        "title": T["tp_mod_new_title"].format(title=orig_title),
                        "duration_min": round(orig_duration * 0.75),
                        "note": details})

        elif badge == "SKIP":
            rename_op["new_title"] = T["tp_skip_renamed"].format(title=orig_title)
            ops.append(rename_op)
            ops.append({"action": "create_calendar_note", "date": target_date,
                        "text": T["tp_skip_note"].format(sport=sport, details=details)})

        # GO → no change

    if "schwer" in str(symptome).lower() and ("neu" in str(symptome).lower() or "severe" in str(symptome).lower()):
        ops.append({"action": "create_calendar_note", "date": target_date,
                    "text": T["tp_sick_note"]})

    # Private note per existing TP workout
    for w in workouts:
        note_op: dict = {"action": "add_private_note", "date": target_date,
                         "note": athlete_note, "title": w.get("title")}
        if w.get("id"):
            note_op["workout_id"] = w["id"]
        ops.append(note_op)

    logger.info("tp_apply: %d ops for %s", len(ops), target_date)
    prompt = (
        f"{T['tp_apply_prompt_intro'].format(name=athlete.get('name', ''), date=target_date)}\n\n"
        f"Execute each operation in order:\n"
        f"{json.dumps(ops, ensure_ascii=False, indent=2)}\n\n"
        f"{T['tp_apply_prompt_sem']}"
    )
    try:
        raw = call_claude_tp_mcp(prompt)
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            actions = json.loads(raw)
        except json.JSONDecodeError:
            actions = [{"action": "apply", "status": "ok", "detail": raw[:500]}]
        return {"ok": True, "actions": actions}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


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
            "hourly": [],
            "error": str(e),
        }

    system = build_system_prompt(athlete, baseline)
    einheiten = data.get("geplante_einheiten", [])
    muskelkater = data.get("muskelkater") or ["keine"]
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")

    # Optional TP workouts context (pre-loaded by user in form)
    tp_ctx = ""
    tp_workouts_data = data.get("tp_workouts")
    if tp_workouts_data:
        tp_ctx = "\n" + T["prompt_tp_ctx"].format(data=json.dumps(tp_workouts_data, ensure_ascii=False))

    heat_thr = athlete.get("nutrition", {}).get("heat_threshold_celsius", 25)
    wasser_line = ""
    if data.get("wasser_temp"):
        wasser_line = f", Wassertemp {data['wasser_temp']}°C"

    weather_flags = []
    if weather.get("is_thunderstorm"):
        weather_flags.append("Gewitter")
    elif weather.get("is_rain"):
        weather_flags.append("Regen")
    if weather.get("is_hot"):
        weather_flags.append(f"Hitze >{heat_thr}°C")
    weather_summary = (
        f"{weather.get('description', '?')}, "
        f"{weather.get('temp_min', '?')}–{weather.get('temp_max', '?')}°C, "
        f"Regen {weather.get('rain_prob', 0)}%"
        + (f" [{', '.join(weather_flags)}]" if weather_flags else "")
        + wasser_line
    )

    header = T["prompt_abend_header"].format(date=tomorrow)
    units_str = ", ".join(einheiten) if einheiten else T["prompt_abend_units_empty"]

    user_msg = (
        f"{header}\n\nFragebogen:\n"
        f"- Knie: {data.get('knie', 0)}/10\n"
        f"- Achillessehne L: {data.get('achilles_l', 0)}/10\n"
        f"- Achillessehne R: {data.get('achilles_r', 0)}/10\n"
        f"- Müdigkeit: {data.get('muedigkeit', 1)}/5\n"
        f"- Muskelkater: {', '.join(muskelkater)}\n"
        f"- Symptome: {data.get('symptome', 'keine')}\n\n"
        f"Wetter morgen: {weather_summary}{tp_ctx}\n\n"
        f"{T['prompt_abend_units'].format(units=units_str)}"
    )

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
            sleep_text = "\n" + T["prompt_autosleep_err"].format(err=str(e))

    einheiten_list = [x.strip() for x in geplante_einheiten.split(",") if x.strip()]
    today_str = date.today().strftime("%d.%m.%Y")
    header = T["prompt_morgen_header"].format(date=today_str)
    units_str = ", ".join(einheiten_list) if einheiten_list else T["prompt_morgen_units_empty"]

    user_msg = (
        f"{header}\n\nFragebogen:\n"
        f"- Waden: {waden}/10\n"
        f"- Knie: {knie}/10\n"
        f"- Achillessehne L: {achilles_l}/10\n"
        f"- Achillessehne R: {achilles_r}/10\n"
        f"- Symptome: {symptome}"
        f"{sleep_text}\n\n"
        f"{T['prompt_morgen_units'].format(units=units_str)}"
    )

    try:
        result = call_claude(system, user_msg)
        if sleep_result:
            result["sleep_flags"] = sleep_result
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Ungültiges JSON von Claude: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))
