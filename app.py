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

APP_VERSION = "2.5.1"
APP_LANG = os.environ.get("APP_LANG", "de")
T = TRANSLATIONS.get(APP_LANG, TRANSLATIONS["de"])
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI()
BASE_DIR = Path(__file__).parent

# ── shared HTTP clients (connection pooling) ──────────────────────────────────
_tp_http = httpx.Client(
    timeout=httpx.Timeout(15.0),
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)
ATHLETE_FILE = BASE_DIR / "athlete.json"
BASELINE_FILE = BASE_DIR / "baseline.json"
SLEEP_HISTORY_FILE = BASE_DIR / "sleep_history.json"
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


def load_sleep_history() -> list:
    if SLEEP_HISTORY_FILE.exists():
        with open(SLEEP_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def append_sleep_history(entry: dict):
    history = load_sleep_history()
    history = [h for h in history if h.get("date") != entry.get("date")]
    history.append(entry)
    history = sorted(history, key=lambda h: h.get("date", ""))[-14:]
    with open(SLEEP_HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)


def next_a_race(athlete: dict) -> Optional[dict]:
    today = date.today()
    candidates = [
        r for r in athlete.get("races", [])
        if r.get("priority") == "A" and date.fromisoformat(r["date"]) >= today
    ]
    return min(candidates, key=lambda r: r["date"]) if candidates else None


# ── weather ───────────────────────────────────────────────────────────────────

WMO = {
    0: "Sonnig", 1: "Meist klar", 2: "Teils bewölkt", 3: "Bedeckt",
    45: "Nebel", 48: "Nebel",
    51: "Leichter Niesel", 53: "Nieselregen", 55: "Starker Niesel",
    61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    71: "Leichter Schnee", 73: "Schnee", 75: "Starker Schnee",
    80: "Leichte Schauer", 81: "Schauer", 82: "Starke Schauer",
    95: "Gewitter", 96: "Gewitter + Hagel", 99: "Schweres Gewitter",
}


WTTR_TO_WMO = {
    113: 0,  116: 2,  119: 3,  122: 3,
    143: 45, 176: 51, 185: 71, 200: 95,
    227: 73, 230: 75, 248: 45, 260: 45,
    263: 51, 266: 51, 281: 55, 284: 55,
    293: 61, 296: 61, 299: 63, 302: 65,
    305: 65, 308: 65, 311: 55, 314: 55,
    317: 71, 320: 73, 323: 71, 326: 71,
    329: 73, 332: 73, 335: 75, 338: 75,
    350: 71, 353: 80, 356: 81, 359: 82,
    362: 71, 365: 73, 368: 71, 371: 73,
    386: 95, 389: 95, 392: 96, 395: 99,
}


async def fetch_weather(athlete: dict, day: int = 1) -> dict:
    lat = athlete["location"]["lat"]
    lon = athlete["location"]["lon"]
    url = f"https://wttr.in/{lat},{lon}?format=j1"
    logger.info("fetch_weather: day=%s lat=%s lon=%s", day, lat, lon)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        headers={"Accept": "application/json", "User-Agent": "ki-coach-app/1.0"},
    ) as client:
        r = await client.get(url)
    r.raise_for_status()
    raw = r.json()
    weather_days = raw.get("weather", [])
    if not weather_days or day >= len(weather_days):
        raise ValueError(f"Keine Wetterdaten für Tag {day}")
    day_data = weather_days[day]
    hourly_list = day_data.get("hourly", [])
    midday = hourly_list[4] if len(hourly_list) > 4 else (hourly_list[-1] if hourly_list else {})
    wttr_code = int(midday.get("weatherCode", "113") or "113")
    code = WTTR_TO_WMO.get(wttr_code, 0)
    temp_max = float(day_data.get("maxtempC", "0") or "0")
    temp_min = float(day_data.get("mintempC", "0") or "0")
    rain_prob = max((int(h.get("chanceofrain", "0") or "0") for h in hourly_list), default=0)
    datum = day_data.get("date", "")
    hourly = []
    for h in hourly_list:
        hour = int(h.get("time", "0") or "0") // 100
        if 6 <= hour <= 20:
            hourly.append({
                "hour": hour,
                "rain": int(h.get("chanceofrain", "0") or "0"),
                "temp": float(h.get("tempC", "0") or "0"),
            })
    result = {
        "datum": datum,
        "code": code,
        "description": WMO.get(code, f"Code {code}"),
        "temp_max": temp_max,
        "temp_min": temp_min,
        "rain_prob": rain_prob,
        "is_thunderstorm": code in [95, 96, 99],
        "is_rain": code in [51, 53, 55, 61, 63, 65, 80, 81, 82] or rain_prob > 60,
        "is_hot": temp_max > 25,
        "hourly": hourly,
    }
    logger.info("fetch_weather ok: datum=%s temp=%s-%s code=%s hourly=%d",
                datum, temp_min, temp_max, code, len(hourly))
    return result


# ── AutoSleep CSV ─────────────────────────────────────────────────────────────

def parse_autosleep_csv(content: bytes) -> dict:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError(T["err_csv_empty"])
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

def nutrition_for_duration(duration_min: Optional[int], nutrition: dict) -> str:
    if not duration_min:
        return ""
    for rule in nutrition.get("rules", []):
        lo = rule.get("duration_min_min", 0)
        hi = rule.get("duration_max_min")
        if duration_min >= lo and (hi is None or duration_min < hi):
            parts = []
            if rule.get("before"):  parts.append(f"Vorher: {rule['before']}")
            if rule.get("during"):  parts.append(f"Während: {rule['during']}")
            if rule.get("after"):   parts.append(f"Nachher: {rule['after']}")
            return " | ".join(parts)
    return ""


def build_pain_rules(_pt: dict) -> str:
    return ""


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
        swim_min=athlete.get("swim_outdoor_min_celsius", 15),
        pain_rules=build_pain_rules(athlete.get("pain_thresholds", {})),
    )


# ── Claude call ───────────────────────────────────────────────────────────────

def call_claude(system: str, user_msg: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, T["err_api_key_missing"])
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
        raise HTTPException(500, T["err_api_key_missing"])
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


async def call_tp_mcp(tool_name: str, arguments: dict):
    url = os.environ["TP_MCP_URL"]
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=headers)
        logger.info("tp_mcp status: %d raw: %r", response.status_code, response.text[:500])
        text = response.text.strip()
        if not text:
            raise ValueError("Empty response from TP MCP")
        # SSE Format: mehrere Zeilen mit "data: {...}"
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    result = json.loads(data)
                    if "result" in result:
                        content = result["result"].get("content", [])
                        if content:
                            return json.loads(content[0]["text"])
        # Plain JSON
        return json.loads(text)


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
        raise HTTPException(404, T["err_no_baseline"])
    return b


@app.get("/api/sleep/history")
async def get_sleep_history():
    return load_sleep_history()


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


def clean_title(title: str) -> str:
    return title.replace(" (KI)", "").replace(" (AI)", "").replace("❌ ", "").replace("↩️ ", "").strip()


@app.post("/api/tp/apply")
async def tp_apply(request: Request):
    if not os.environ.get("TP_MCP_URL"):
        raise HTTPException(400, T["err_tp_url_missing"])
    body        = await request.json()
    operations  = body.get("operations", [])
    day         = body.get("day", "tomorrow")
    symptome    = body.get("symptome", "")
    knie        = body.get("knie",       0)
    achilles_l  = body.get("achilles_l", 0)
    achilles_r  = body.get("achilles_r", 0)
    muedigkeit  = body.get("muedigkeit", 1)
    day_offset  = 0 if day == "today" else 1
    target_date = (date.today() + timedelta(days=day_offset)).isoformat()
    athlete     = load_athlete()

    logger.info("tp_apply: %d operations for %s symptome=%r", len(operations), target_date, symptome)
    actions = []
    had_skip_stop = False
    for op in operations:
        workout_id = op.get("workout_id")
        badge      = op.get("badge", "GO")
        orig_title = op.get("orig_title", "")

        if badge == "GO" or not workout_id:
            continue

        base_title = clean_title(orig_title)

        if badge in ("SKIP", "STOP"):
            new_title = T["tp_skip_renamed"].format(title=base_title)
            try:
                result = await call_tp_mcp("tp_update_workout", {"workout_id": workout_id, "title": new_title})
                actions.append({"workout_id": workout_id, "badge": badge, "status": "ok",
                                "detail": new_title, "mcp_response": result})
                had_skip_stop = True
            except Exception as e:
                logger.error("tp_apply SKIP: tp_update_workout failed for %s: %s", workout_id, e)
                actions.append({"workout_id": workout_id, "badge": badge, "status": "error", "detail": str(e)})

        elif badge == "MOD":
            # Step 1: mark original as archived
            renamed_title = T["tp_mod_renamed"].format(title=base_title)
            rename_ok = False
            try:
                await call_tp_mcp("tp_update_workout", {"workout_id": workout_id, "title": renamed_title})
                rename_ok = True
                logger.info("tp_apply MOD: renamed %s → %s", workout_id, renamed_title)
            except Exception as e:
                logger.error("tp_apply MOD: rename failed for %s: %s", workout_id, e)
                actions.append({"workout_id": workout_id, "badge": badge, "status": "error",
                                "detail": f"Umbenennung fehlgeschlagen: {e}"})

            if not rename_ok:
                continue

            # Step 2: create new adjusted workout
            new_title  = T["tp_mod_new_title"].format(title=base_title)
            sport      = op.get("sport", "")
            coach_rec  = op.get("description", "")
            reason     = op.get("reason", "")
            orig_dur   = op.get("duration_min")
            orig_tss   = op.get("tss")

            # Duration: parse from coach_rec first ("30min"), else 75% of original, min 20
            import re as _re
            new_duration: int = 20
            new_tss: Optional[int] = None
            rec_match = _re.search(r'\b(\d+)\s*min\b', coach_rec or "", _re.IGNORECASE)
            if rec_match:
                new_duration = max(20, int(rec_match.group(1)))
            elif orig_dur:
                try:
                    new_duration = max(20, round(float(orig_dur) * 0.75))
                except (TypeError, ValueError):
                    pass
            if orig_tss and orig_dur:
                try:
                    new_tss = max(1, round(float(orig_tss) * (new_duration / float(orig_dur))))
                except (TypeError, ValueError):
                    pass

            # Structured description — no old workout notes
            desc_parts: list = []
            if reason:
                desc_parts.append(f"Angepasst wegen: {reason}")
            if coach_rec:
                desc_parts.append(coach_rec)
            nutr = nutrition_for_duration(new_duration, athlete.get("nutrition", {}))
            if nutr:
                desc_parts.append(f"ERNÄHRUNG: {nutr}")

            create_args: dict = {
                "title":              new_title,
                "sport":              sport,
                "date":               target_date,
                "duration_minutes":   new_duration,
            }
            if desc_parts:
                create_args["description"] = "\n\n".join(desc_parts)
            if new_tss is not None:
                create_args["tss"] = new_tss

            logger.info("tp_apply MOD: tp_create_workout args=%s", create_args)
            try:
                result = await call_tp_mcp("tp_create_workout", create_args)
                detail = new_title
                if new_duration:
                    detail += f" ({new_duration}min"
                    if new_tss:
                        detail += f" / {new_tss} TSS"
                    detail += ")"
                actions.append({"workout_id": workout_id, "badge": badge, "status": "ok",
                                "detail": detail, "mcp_response": result})
            except Exception as e:
                logger.error("tp_apply MOD: tp_create_workout failed for %s: %s", workout_id, e)
                actions.append({"workout_id": workout_id, "badge": badge, "status": "error",
                                "detail": f"Neues Workout nicht erstellt: {e}"})

    # Kalendernotiz bei Krankheit (einmalig, unabhängig von Workout-Anzahl)
    if had_skip_stop and "neu schwer" in symptome:
        note_title = "🤧 Krank – Training gestrichen (KI)"
        note_text  = (
            f"Symptome: {symptome}. Alle Einheiten gestrichen.\n"
            f"Knie: {knie}/10, Achilles L: {achilles_l}/10, "
            f"Achilles R: {achilles_r}/10, Müdigkeit: {muedigkeit}/5."
        )
        logger.info("tp_apply: creating sick-note for %s", target_date)
        try:
            await call_tp_mcp("tp_create_note", {
                "date":  target_date,
                "title": note_title,
                "text":  note_text,
            })
            actions.append({"badge": "NOTE", "status": "ok", "detail": note_title})
        except Exception as e:
            logger.error("tp_apply: tp_create_note failed: %s", e)
            actions.append({"badge": "NOTE", "status": "error", "detail": f"Kalendernotiz fehlgeschlagen: {e}"})

    logger.info("tp_apply done: %d actions", len(actions))
    return {"ok": True, "actions": actions}


@app.post("/api/check-abend")
async def check_abend(request: Request):
    data = await request.json()
    athlete = load_athlete()
    baseline = load_baseline()

    weather = None
    if data.get("weather_data"):
        try:
            weather = json.loads(data["weather_data"]) if isinstance(data["weather_data"], str) else data["weather_data"]
        except Exception:
            pass
    if not weather:
        try:
            weather = await fetch_weather(athlete)
        except Exception as e:
            logger.warning("check-abend: Wetter nicht verfügbar: %s", e)
            weather = {
                "description": T["err_weather_na"],
                "temp_max": None, "temp_min": None,
                "rain_prob": 0, "is_thunderstorm": False,
                "is_rain": False, "is_hot": False,
                "hourly": [],
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
        f"- Waden: {data.get('waden', 0)}/10\n"
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
        raise HTTPException(500, T["err_claude_json"].format(e=e))
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
    weather_data: str = Form(""),
    csv_file: Optional[UploadFile] = File(None),
):
    athlete = load_athlete()
    baseline = load_baseline()
    system = build_system_prompt(athlete, baseline)

    weather = None
    if weather_data:
        try:
            weather = json.loads(weather_data)
        except Exception:
            pass
    if not weather:
        try:
            weather = await fetch_weather(athlete, day=0)
        except Exception as e:
            logger.warning("check-morgen: Wetter nicht verfügbar: %s", e)

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
            try:
                append_sleep_history({
                    "date": date.today().isoformat(),
                    "schlafHRV": sd.get("hrv"),
                    "wachBPM": sd.get("wach_bpm"),
                    "schlafBPM": sd.get("schlaf_bpm"),
                    "atmung": sd.get("atmung"),
                    "effizienz": sd.get("effizienz"),
                    "schlafDauer": sd.get("schlaf_stunden"),
                })
            except Exception as hist_err:
                logger.warning("sleep_history save failed: %s", hist_err)
        except Exception as e:
            sleep_text = "\n" + T["prompt_autosleep_err"].format(err=str(e))

    heat_thr = athlete.get("nutrition", {}).get("heat_threshold_celsius", 25)
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
    )

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
        f"Wetter heute: {weather_summary}\n\n"
        f"{T['prompt_morgen_units'].format(units=units_str)}"
    )

    try:
        result = call_claude(system, user_msg)
        if weather:
            result["weather"] = weather
        if sleep_result:
            result["sleep_flags"] = sleep_result
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(500, T["err_claude_json"].format(e=e))
    except Exception as e:
        raise HTTPException(500, str(e))
