import asyncio
import os
import json
import re
import csv
import io
import logging
import statistics
import uuid
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import anthropic

from translations import TRANSLATIONS

APP_VERSION = "2.6.90"
APP_LANG = os.environ.get("APP_LANG", "de")
T = TRANSLATIONS.get(APP_LANG, TRANSLATIONS["de"])
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI()

@app.on_event("startup")
async def _prefetch_tp():
    """Prefetcht TP Workouts für die nächsten 7 Tage in einem einzigen MCP-Call."""
    if not os.environ.get("TP_MCP_URL"):
        return
    athlete = load_athlete()
    asyncio.create_task(_tp_refresh_range(athlete, days=7))
BASE_DIR = Path(__file__).parent

# ── shared HTTP clients (connection pooling) ──────────────────────────────────
_tp_http = httpx.Client(
    timeout=httpx.Timeout(15.0),
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)
_tp_http_long = httpx.Client(
    timeout=httpx.Timeout(360.0),   # 6 Min für Workout-Analyse
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)

# In-memory Job-Store für Workout-Analysen
_analysis_jobs: dict = {}  # job_id -> {"status":"pending"|"done"|"error", "result":{}, "error":"..."}

# ── TP Workout Cache + Background Refresh ────────────────────────────────────
import time as _time
_tp_cache: dict = {}             # date_str -> {"data": {...}, "ts": float}
_tp_refresh_busy: set = set()    # date_strs currently being fetched
_TP_CACHE_TTL   = 3600           # 1h — serve from cache
_TP_CACHE_STALE = 1800           # 30min — trigger background refresh
_history_wx_cache: dict = {}     # range_key -> {"ts": float, "wx": {date: weather_dict}}
_HISTORY_WX_TTL = 21600          # 6h — history weather einmal pro Tag genug

def _tp_cache_get(date_str: str) -> Optional[dict]:
    entry = _tp_cache.get(date_str)
    if entry and _time.time() - entry["ts"] < _TP_CACHE_TTL:
        return entry["data"]
    return None

def _tp_cache_set(date_str: str, data: dict):
    _tp_cache[date_str] = {"data": data, "ts": _time.time()}

def _extract_json(raw: str):
    """Extrahiert JSON aus einem String — auch wenn Modell Text darum herum schreibt."""
    raw = raw.strip()
    # Markdown-Fence entfernen
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    # Direkt parsen (strikt)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Ersten vollständigen JSON-Block per Decoder extrahieren (robust gegen "Extra data")
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(raw)
        return obj
    except json.JSONDecodeError:
        pass
    # Fallback: erstes {...} oder [...] per Regex
    m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
    if m:
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(m.group(1))
            return obj
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Kein JSON gefunden: {raw[:200]}")


async def _enrich_workouts(workouts: list) -> list:
    """Fetcht Beschreibung + subtype_id pro Workout direkt vom TP MCP (ohne Claude)."""
    async def _detail(w: dict) -> dict:
        wid = w.get("id") or w.get("workoutId")
        if not wid:
            return w
        try:
            d = await call_tp_mcp("tp_get_workout", {"workout_id": str(wid)})
            if isinstance(d, dict):
                desc = (d.get("description") or d.get("coachComments") or
                        d.get("workoutDescription") or "")
                if desc:
                    w["description"] = desc
                subtype = (d.get("workoutTypeValueId") or d.get("subTypeValueId") or
                           d.get("workoutSubTypeId") or d.get("subtypeId"))
                if subtype is not None:
                    w["subtype_id"] = subtype
        except Exception as e:
            logger.warning("_enrich_workouts: tp_get_workout failed for %s: %s", wid, e)
        return w
    return list(await asyncio.gather(*[_detail(w) for w in workouts]))


def _map_tp_workout(w: dict) -> dict:
    """Mapped TP-native Felder auf unser internes Format."""
    wid   = str(w.get("workoutId") or w.get("id") or "")
    title = w.get("title") or w.get("name") or ""
    day   = (w.get("workoutDay") or w.get("date") or "")[:10]
    dur_s = w.get("totalTimePlanned") or w.get("totalTime") or 0
    dur_m = round(dur_s / 60) if dur_s else None
    tss   = w.get("tssPlanned") or w.get("tssActual") or w.get("tss") or None
    st    = w.get("startTimePlanned") or w.get("startTime") or ""
    stid  = w.get("workoutTypeValueId") or w.get("sportTypeId")
    sport = (w.get("sport") or w.get("sportType") or
             _HISTORY_SPORT_MAP.get(stid, "") or str(stid or ""))
    return {"id": wid, "sport": sport, "title": title,
            "duration_min": dur_m, "tss": tss,
            "start_time": st, "subtype_id": stid, "_day": day}


async def _tp_fetch_direct(start: str, end: str, wtype: str = "planned") -> dict:
    """Holt Workouts per direktem MCP-Call und gruppiert sie nach Datum."""
    raw = await call_tp_mcp("tp_get_workouts", {
        "start_date": start, "end_date": end, "type": wtype
    })
    items = raw if isinstance(raw, list) else raw.get("workouts", raw.get("items", []))
    by_date: dict = {}
    for w in (items or []):
        mapped = _map_tp_workout(w)
        day = mapped.pop("_day", "")
        if mapped["id"] and day:
            by_date.setdefault(day, []).append(mapped)
    return by_date


async def _tp_refresh(athlete: dict, day_offset: int = 0, date_str: str = None):
    """Holt TP Workouts im Hintergrund und füllt den Cache."""
    target = date_str if date_str else (date.today() + timedelta(days=day_offset)).isoformat()
    if target in _tp_refresh_busy:
        return
    _tp_refresh_busy.add(target)
    try:
        by_date = await _tp_fetch_direct(target, target)
        workouts = await _enrich_workouts(by_date.get(target, []))
        _tp_cache_set(target, {"available": True, "workouts": workouts, "date": target})
        logger.info("_tp_refresh ok: %d workouts for %s", len(workouts), target)
    except Exception as e:
        logger.error("_tp_refresh error for %s: %s", target, e)
    finally:
        _tp_refresh_busy.discard(target)

async def _tp_refresh_range(athlete: dict, days: int = 7):
    """Holt TP Workouts für einen Datumsbereich direkt per MCP."""
    start = date.today()
    end   = start + timedelta(days=days - 1)
    range_key = f"range_{start.isoformat()}_{end.isoformat()}"
    if range_key in _tp_refresh_busy:
        return
    _tp_refresh_busy.add(range_key)
    date_keys = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    for dk in date_keys:
        _tp_refresh_busy.add(dk)
    try:
        by_date = await _tp_fetch_direct(start.isoformat(), end.isoformat())
        # Alle Workouts in einem Batch parallel enrichen
        flat = [(day, w) for day, wl in by_date.items() for w in wl]
        if flat:
            enriched = await _enrich_workouts([w for _, w in flat])
            by_date = {}
            for (day, _), w in zip(flat, enriched):
                by_date.setdefault(day, []).append(w)
        for day, workouts in by_date.items():
            _tp_cache_set(day, {"available": True, "workouts": workouts, "date": day})
        # Tage ohne Workouts auch als leer cachen
        for dk in date_keys:
            if not _tp_cache_get(dk):
                _tp_cache_set(dk, {"available": True, "workouts": [], "date": dk})
        logger.info("_tp_refresh_range ok: %d Tage mit Workouts für %s–%s",
                    len(by_date), start, end)
    except Exception as e:
        logger.error("_tp_refresh_range error: %s", e)
        # Fallback: heute + morgen einzeln nachladen
        for off in range(2):
            asyncio.create_task(_tp_refresh(athlete, off))
    finally:
        _tp_refresh_busy.discard(range_key)
        for dk in date_keys:
            _tp_refresh_busy.discard(dk)


def parse_fit_summary(fit_bytes: bytes) -> dict:
    """Parst eine FIT-Datei und gibt die wichtigsten Metriken als Dict zurück."""
    try:
        import fitdecode
    except ImportError:
        return {}
    try:
        import warnings
        session = {}
        laps = []
        records_power = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with fitdecode.FitReader(io.BytesIO(fit_bytes)) as ff:
                for frame in ff:
                    if not isinstance(frame, fitdecode.FitDataMessage):
                        continue
                    name = frame.name
                    if name == "session":
                        for f in frame.fields:
                            session[f.name] = f.value
                    elif name == "lap":
                        lap = {f.name: f.value for f in frame.fields}
                        laps.append(lap)
                    elif name == "record":
                        pw = frame.get_value("power", fallback=None)
                        if pw is not None:
                            records_power.append(pw)

        summary = {}

        # Dauer
        elapsed = session.get("total_elapsed_time") or session.get("total_timer_time")
        if elapsed:
            summary["dauer_min"] = round(elapsed / 60, 1)

        # Distanz
        dist = session.get("total_distance")
        if dist:
            summary["distanz_km"] = round(dist / 1000, 2)

        # Leistung (Rad)
        avg_pw = session.get("avg_power") or session.get("average_power")
        max_pw = session.get("max_power")
        np_val = session.get("normalized_power")
        if avg_pw:
            summary["avg_power_w"] = round(avg_pw)
        if max_pw:
            summary["max_power_w"] = round(max_pw)
        if np_val:
            summary["normalized_power_w"] = round(np_val)
        elif records_power and len(records_power) > 30:
            window = 30
            rolling = []
            for i in range(window - 1, len(records_power)):
                chunk = records_power[i - window + 1:i + 1]
                rolling.append((sum(chunk) / window) ** 4)
            if rolling:
                summary["normalized_power_w"] = round(statistics.mean(rolling) ** 0.25)

        # Herzrate
        avg_hr = session.get("avg_heart_rate") or session.get("average_heart_rate")
        max_hr = session.get("max_heart_rate")
        if avg_hr:
            summary["avg_hr"] = round(avg_hr)
        if max_hr:
            summary["max_hr"] = round(max_hr)

        # Kadenz (Lauf: avg_running_cadence × 2 = Schritte/min)
        avg_cad = session.get("avg_cadence") or session.get("average_cadence")
        avg_run_cad = session.get("avg_running_cadence")
        if avg_run_cad:
            summary["avg_kadenz"] = round(avg_run_cad * 2)
        elif avg_cad:
            summary["avg_kadenz"] = round(avg_cad)

        # Pace (Lauf) — enhanced_avg_speed zuerst
        avg_speed = (session.get("enhanced_avg_speed") or session.get("avg_speed")
                     or session.get("average_speed"))
        if avg_speed and avg_speed > 0:
            pace_sec = 1000 / avg_speed
            summary["avg_pace_min_km"] = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}"

        # Kalorien
        kcal = session.get("total_calories")
        if kcal:
            summary["kcal"] = round(kcal)

        # TSS / Work
        tss = session.get("training_stress_score") or session.get("total_training_effect")
        total_work = session.get("total_work")
        if tss:
            summary["tss"] = round(tss, 1)
        if total_work:
            summary["total_work_kj"] = round(total_work / 1000, 1)

        # Sport
        sport = session.get("sport")
        sub_sport = session.get("sub_sport")
        if sport:
            summary["sport"] = str(sport)
        if sub_sport and str(sub_sport) not in ("generic", "None"):
            summary["sub_sport"] = str(sub_sport)

        # Start- und Endzeit (UTC ISO-String)
        st = session.get("start_time")
        if st:
            try:
                summary["start_time_utc"] = st.isoformat()
                elapsed_s = session.get("total_elapsed_time") or session.get("total_timer_time")
                if elapsed_s:
                    from datetime import timezone as _tz
                    end_dt = st.replace(tzinfo=_tz.utc) if st.tzinfo is None else st
                    end_dt = end_dt + timedelta(seconds=int(elapsed_s))
                    summary["end_time_utc"] = end_dt.isoformat()
            except Exception:
                pass

        # Lap-Splits (alle, max 25)
        if laps:
            lap_list = []
            for lap in laps[:25]:
                entry = {}
                t = lap.get("total_elapsed_time") or lap.get("total_timer_time")
                d = lap.get("total_distance")
                p = lap.get("avg_power") or lap.get("average_power")
                h = lap.get("avg_heart_rate") or lap.get("average_heart_rate")
                sp = lap.get("enhanced_avg_speed") or lap.get("avg_speed") or lap.get("average_speed")
                if t:
                    entry["t_min"] = round(t / 60, 1)
                if d:
                    entry["km"] = round(d / 1000, 2)
                if p:
                    entry["avg_w"] = round(p)
                if h:
                    entry["avg_hr"] = round(h)
                if sp and sp > 0:
                    ps = 1000 / sp
                    entry["pace"] = f"{int(ps//60)}:{int(ps%60):02d}"
                if entry:
                    lap_list.append(entry)
            if lap_list:
                summary["laps"] = lap_list

        return summary
    except Exception as e:
        logger.warning("FIT parse error: %s", e)
        return {}
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


# ── TP events cache ───────────────────────────────────────────────────────────

_tp_events_cache: dict = {"ts": 0.0, "races": None}
_TP_EVENTS_TTL = 900  # 15 min


def _normalize_tp_events(events: list, existing_races: list) -> list:
    """Map TP events to internal race format, preserving goals from athlete.json by name."""
    goals_by_name = {r.get("name", "").strip().lower(): r for r in existing_races}
    today = date.today().isoformat()
    result = []
    for e in events:
        ev_date = (e.get("eventDate") or "")[:10]
        if not ev_date or ev_date < today:
            continue
        name = (e.get("name") or "").strip()
        tp_priority = e.get("atpPriority")
        existing = goals_by_name.get(name.lower(), {})
        priority = tp_priority if tp_priority in ("A", "B", "C") else existing.get("priority", "B")
        result.append({
            "name":       name,
            "date":       ev_date,
            "priority":   priority,
            "distance":   existing.get("distance", ""),
            "goal_total": existing.get("goal_total"),
            "goal_swim":  existing.get("goal_swim"),
            "goal_bike":  existing.get("goal_bike"),
            "goal_run":   existing.get("goal_run"),
            "tp_event_id": e.get("id"),
        })
    result.sort(key=lambda r: r["date"])
    return result


async def load_athlete_merged() -> dict:
    """load_athlete() + TP events merged in (cached)."""
    athlete = load_athlete()
    tp_races = await _fetch_tp_races(athlete.get("races", []))
    if tp_races is not None:
        athlete["races"] = tp_races
    return athlete


async def _fetch_tp_races(existing_races: list) -> Optional[list]:
    import time as _time
    if not os.environ.get("TP_MCP_URL"):
        return None
    now = _time.monotonic()
    if _tp_events_cache["races"] is not None and now - _tp_events_cache["ts"] < _TP_EVENTS_TTL:
        return _tp_events_cache["races"]
    try:
        today = date.today()
        end   = (today + timedelta(days=89)).isoformat()  # max 90 days per TP limit
        raw   = await call_tp_mcp("tp_get_events", {"start_date": today.isoformat(), "end_date": end})
        events = raw.get("events", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if not events:
            logger.warning("_fetch_tp_races: TP returned 0 events — keeping athlete.json races")
            return None
        races  = _normalize_tp_events(events, existing_races)
        _tp_events_cache.update({"ts": now, "races": races})
        logger.info("_fetch_tp_races: %d events loaded", len(races))
        return races
    except Exception as e:
        logger.warning("_fetch_tp_races failed: %s", e)
        return None


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
        "is_hot": temp_max > 28,
        "is_cold": temp_max < 0,
        "hourly": hourly,
    }
    logger.info("fetch_weather ok: datum=%s temp=%s-%s code=%s hourly=%d",
                datum, temp_min, temp_max, code, len(hourly))
    return result


async def fetch_weather_for_date(athlete: dict, target_date: str) -> dict:
    """Wetter für ein spezifisches Datum (heute oder Vergangenheit, max. 7 Tage)."""
    today = date.today().isoformat()
    if target_date >= today:
        return await fetch_weather(athlete, day=0)
    lat = athlete["location"]["lat"]
    lon = athlete["location"]["lon"]
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        f"&past_days=7&forecast_days=1&timezone=Europe%2FBerlin"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if target_date not in dates:
        raise ValueError(f"Keine Wetterdaten für {target_date}")
    i = dates.index(target_date)
    temp_max_v = float((daily.get("temperature_2m_max") or [0])[i] or 0)
    temp_min_v = float((daily.get("temperature_2m_min") or [0])[i] or 0)
    rain_prob  = int((daily.get("precipitation_probability_max") or [0])[i] or 0)
    wcode      = int((daily.get("weather_code") or [0])[i] or 0)
    logger.info("fetch_weather_for_date ok: date=%s temp=%s-%s code=%s", target_date, temp_min_v, temp_max_v, wcode)
    return {
        "datum":         target_date,
        "code":          wcode,
        "description":   WMO.get(wcode, f"Code {wcode}"),
        "temp_max":      temp_max_v,
        "temp_min":      temp_min_v,
        "rain_prob":     rain_prob,
        "is_thunderstorm": wcode in [95, 96, 99],
        "is_rain":       wcode in [51, 53, 55, 61, 63, 65, 80, 81, 82] or rain_prob > 60,
        "is_hot":        temp_max_v > 28,
        "is_cold":       temp_max_v < 0,
        "hourly":        [],
    }


async def fetch_weather_for_workout(athlete: dict, start_utc: str, end_utc: str) -> dict:
    """Stündliche Archiv-Wetterdaten für ein konkretes Workout-Zeitfenster (UTC ISO-Strings)."""
    from datetime import datetime as _dt, timezone as _tz
    lat = athlete["location"]["lat"]
    lon = athlete["location"]["lon"]

    start_dt = _dt.fromisoformat(start_utc.replace("Z", "+00:00"))
    end_dt   = _dt.fromisoformat(end_utc.replace("Z", "+00:00"))
    # In Berliner Lokalzeit umrechnen für die Anzeige
    berlin_offset = timedelta(hours=2)  # CEST; gut genug für Sommer
    start_local = start_dt + berlin_offset
    end_local   = end_dt   + berlin_offset

    start_date = start_dt.date().isoformat()
    end_date   = end_dt.date().isoformat()

    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&hourly=temperature_2m,precipitation,weather_code"
        f"&timezone=Europe%2FBerlin"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
    r.raise_for_status()
    data = r.json()

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    temps  = hourly.get("temperature_2m", [])
    precips = hourly.get("precipitation", [])
    codes  = hourly.get("weather_code", [])

    # Stunden filtern die im Workout-Fenster liegen
    matching_temps, matching_precip, matching_codes = [], [], []
    for i, t_str in enumerate(times):
        t_dt = _dt.fromisoformat(t_str)
        if t_dt.tzinfo is None:
            t_dt = t_dt.replace(tzinfo=_tz.utc)
        # Vergleich in Lokalzeit: t_str ist bereits in Europe/Berlin
        if start_local.replace(tzinfo=None) <= t_dt.replace(tzinfo=None) <= end_local.replace(tzinfo=None):
            if i < len(temps) and temps[i] is not None:
                matching_temps.append(float(temps[i]))
            if i < len(precips) and precips[i] is not None:
                matching_precip.append(float(precips[i]))
            if i < len(codes) and codes[i] is not None:
                matching_codes.append(int(codes[i]))

    if not matching_temps:
        raise ValueError(f"Keine stündlichen Archivdaten für {start_date}")

    avg_temp  = round(sum(matching_temps) / len(matching_temps), 1)
    temp_min  = round(min(matching_temps), 1)
    temp_max  = round(max(matching_temps), 1)
    total_precip = round(sum(matching_precip), 1) if matching_precip else 0
    # häufigster Wettercode im Fenster
    dominant_code = max(set(matching_codes), key=matching_codes.count) if matching_codes else 0

    start_str = start_local.strftime("%H:%M")
    end_str   = end_local.strftime("%H:%M")

    logger.info("fetch_weather_for_workout ok: %s–%s avg=%.1f°C precip=%.1fmm code=%s",
                start_str, end_str, avg_temp, total_precip, dominant_code)
    return {
        "datum":       start_date,
        "start_local": start_str,
        "end_local":   end_str,
        "code":        dominant_code,
        "description": WMO.get(dominant_code, f"Code {dominant_code}"),
        "avg_temp":    avg_temp,
        "temp_min":    temp_min,
        "temp_max":    temp_max,
        "precip_mm":   total_precip,
        "is_hot":      avg_temp > 28,
        "is_cold":     avg_temp < 0,
    }


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
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()
    return _extract_json(raw)


def call_claude_tp_mcp(user_content: str) -> str:
    tp_url = os.environ.get("TP_MCP_URL", "")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(500, T["err_api_key_missing"])
    c = anthropic.Anthropic(api_key=key, http_client=_tp_http_long)
    try:
        msg = c.beta.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            betas=["mcp-client-2025-11-20"],
            mcp_servers=[{"type": "url", "url": tp_url, "name": "trainingpeaks"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "trainingpeaks"}],
            system="Antworte ausschließlich mit gültigem JSON. Kein Erklärungstext, keine Markdown-Blöcke, kein Text vor oder nach dem JSON.",
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
    last_text = None
    for block in msg.content:
        if hasattr(block, "text") and block.text:
            last_text = block.text  # letzten Text-Block merken (nach Tool-Calls)
        if getattr(block, "is_error", False):
            content = getattr(block, "content", "")
            if isinstance(content, list):
                content = " ".join(getattr(c, "text", str(c)) for c in content)
            mcp_errors.append(str(content)[:300])

    if last_text:
        return last_text
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
    resp = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "T": T,
            "T_json": json.dumps(T, ensure_ascii=False),
            "LANG": APP_LANG,
            "version": APP_VERSION,
        },
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


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
    return await load_athlete_merged()


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


@app.post("/api/sleep/history/sync")
async def sync_sleep_history(request: Request):
    """Nimmt Client-seitige localStorage-Einträge und merged sie in die Server-History."""
    entries = await request.json()
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="Expected JSON array")
    history = load_sleep_history()
    existing_dates = {h.get("date") for h in history}
    added = 0
    for entry in entries:
        if isinstance(entry, dict) and entry.get("date") and entry["date"] not in existing_dates:
            history.append(entry)
            existing_dates.add(entry["date"])
            added += 1
    if added:
        history = sorted(history, key=lambda h: h.get("date", ""))[-14:]
        with open(SLEEP_HISTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False)
    return {"added": added, "total": len(history)}


@app.post("/api/coach/chat")
async def coach_chat(request: Request):
    """Freies Chat mit dem Coach — nutzt Athletenprofil als Kontext."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(500, T["err_api_key_missing"])
    body = await request.json()
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(400, "Nachricht fehlt")
    history = body.get("history", [])

    athlete = load_athlete()
    baseline = load_baseline()
    system = build_system_prompt(athlete, baseline)
    system += "\nDu bist im direkten Chat. Antworte auf Deutsch, direkt und konkret. Kein JSON — normaler Text."

    # TP-Workouts: heute, morgen + im Text erwähnte Wochentage (bis 30 Tage voraus)
    today_d   = date.today()
    today_str = today_d.isoformat()
    _DE_DAYS = {
        "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
        "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
    }
    _msg_lower = message.lower()
    dates_to_check: list = []  # list of (label, date_str, day_offset_or_none)
    for off in range(30):
        d = today_d + timedelta(days=off)
        ds = d.isoformat()
        if off == 0:
            label = "heute"
        elif off == 1:
            label = "morgen"
        elif off == 2 and "übermorgen" in _msg_lower:
            label = "übermorgen"
        else:
            # Wochentag-Match: nur hinzufügen wenn im Text genannt
            de_name = ["montag","dienstag","mittwoch","donnerstag","freitag","samstag","sonntag"][d.weekday()]
            mentioned = de_name in _msg_lower or (de_name == "samstag" and "sonnabend" in _msg_lower)
            if not mentioned and off >= 2:
                continue
            label = de_name.capitalize()
        dates_to_check.append((label, ds, off))

    tp_lines = []
    tp_loading_labels = []
    for label, ds, off in dates_to_check:
        cached = _tp_cache_get(ds)
        if cached and cached.get("workouts"):
            for w in cached["workouts"]:
                parts = [w.get("sport", "?"), w.get("title", "")]
                if w.get("duration_min"): parts.append(f"{w['duration_min']} min")
                if w.get("tss"):          parts.append(f"{w['tss']} TSS")
                tp_lines.append(f"  - {label} ({ds}): {' | '.join(p for p in parts if p)}")
        elif os.environ.get("TP_MCP_URL"):
            tp_loading_labels.append(label)
            if ds not in _tp_refresh_busy and f"range_{today_str}" not in str(_tp_refresh_busy):
                asyncio.create_task(_tp_refresh(athlete, date_str=ds))

    if tp_lines:
        system += (
            "\n\nAktueller TrainingPeaks-Plan (automatisch geladen — du HAST diese Daten, nutze sie direkt):\n"
            + "\n".join(tp_lines)
        )
    if tp_loading_labels:
        system += (
            f"\n\nFür folgende Tage werden TP-Daten noch geladen: {', '.join(tp_loading_labels)}. "
            "Weise den Nutzer darauf hin, dass diese in ~1 Minute verfügbar sind und er nochmal fragen kann."
        )
    if not tp_lines and not tp_loading_labels and os.environ.get("TP_MCP_URL"):
        system += "\n\nTrainingPeaks: keine Workouts für die angefragten Tage geplant."

    # Wetterdaten heute + morgen anhängen
    try:
        wx_today    = await fetch_weather(athlete, day=0)
        wx_tomorrow = await fetch_weather(athlete, day=1)
        system += (
            f"\n\nWetter heute ({today_str}): {wx_today.get('description','?')}, "
            f"{wx_today.get('temp_min','?')}–{wx_today.get('temp_max','?')}°C, "
            f"Regen {wx_today.get('rain_prob',0)}%."
            f"\nWetter morgen ({tomorrow_str}): {wx_tomorrow.get('description','?')}, "
            f"{wx_tomorrow.get('temp_min','?')}–{wx_tomorrow.get('temp_max','?')}°C, "
            f"Regen {wx_tomorrow.get('rain_prob',0)}%."
        )
    except Exception:
        system += "\n\nWetterdaten aktuell nicht verfügbar. Antworte ohne Wetterdaten — keine Spekulationen."

    messages = []
    for h in history[-10:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": message})

    c = anthropic.Anthropic(api_key=key)
    msg = c.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        system=system,
        messages=messages,
    )
    reply = msg.content[0].text.strip()
    return JSONResponse({"reply": reply}, headers=_NO_CACHE)


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
    cached = _tp_cache_get(target)
    if cached:
        logger.info("_tp_call_sync cache hit: %s", target)
        return cached
    prompt = T["tp_workouts_prompt"].format(name=athlete.get("name", "the athlete"), date=target)
    try:
        raw = call_claude_tp_mcp(prompt)
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        workouts = json.loads(raw)
        logger.info("_tp_call_sync ok: %d workouts day_offset=%d", len(workouts), day_offset)
        result = {"available": True, "workouts": workouts, "date": target}
        _tp_cache_set(target, result)
        return result
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
    cached = _tp_cache_get(target)
    if cached:
        # Stale-while-revalidate: im Hintergrund neu laden wenn Cache > 30min alt
        entry = _tp_cache.get(target)
        if entry and _time.time() - entry["ts"] > _TP_CACHE_STALE:
            asyncio.create_task(_tp_refresh(athlete, day_offset))
        logger.info("tp_workouts cache hit: %s", target)
        return JSONResponse(cached, headers=_NO_CACHE)
    # Cache Miss → sofort zurückgeben + Hintergrund-Fetch starten
    logger.info("tp_workouts cache miss: %s — background fetch started", target)
    asyncio.create_task(_tp_refresh(athlete, day_offset))
    return JSONResponse({"available": True, "workouts": [], "date": target, "loading": True},
                        headers=_NO_CACHE)


@app.post("/api/tp/refresh")
async def tp_refresh_endpoint(day: str = "tomorrow"):
    """Cache löschen und TP-Workouts sofort neu laden."""
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        return JSONResponse({"available": False, "workouts": [], "date": None}, headers=_NO_CACHE)
    day_offset = 0 if day == "today" else 1
    target = (date.today() + timedelta(days=day_offset)).isoformat()
    athlete = load_athlete()
    # Cache-Eintrag entfernen → erzwingt Neu-Fetch
    _tp_cache.pop(target, None)
    _tp_refresh_busy.discard(target)
    await _tp_refresh(athlete, day_offset)
    cached = _tp_cache_get(target)
    if cached:
        return JSONResponse(cached, headers=_NO_CACHE)
    return JSONResponse({"available": True, "workouts": [], "date": target}, headers=_NO_CACHE)


@app.post("/api/debug/coach-beschreibung")
async def debug_coach_beschreibung(request: Request):
    """Test: schickt einen Mock-Workout durch den Coach und zeigt die generierte Beschreibung."""
    body = await request.json()
    athlete = load_athlete()
    baseline = load_baseline()
    system = build_system_prompt(athlete, baseline)

    workout = body.get("workout", {
        "id": "test-1",
        "sport": "Laufen",
        "title": "Lockerer aerober Lauf",
        "duration_min": 35,
        "tss": 28,
        "description": "Lockerer aerober Lauf. Aktive Erholung nach dem Di-Intervall.\nSTRUKTUR:35 min ganz locker (6:15–6:45/km, HF-Deckel 150 bpm)\nKNIE-REGEL: Schmerz >3/10 → abbrechen.",
    })
    badge = body.get("badge", "MOD")
    conditions = body.get("conditions", "Hitze >25°C (31°C erwartet)")

    tp_ctx = "\nTrainingPeaks geplante Workouts morgen: " + json.dumps([workout], ensure_ascii=False)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    user_msg = (
        f"Abend-Check — Plan für morgen ({tomorrow}):\n\n"
        f"Fragebogen:\n- Waden: 0/10\n- Knie: 0/10\n- Achillessehne L: 0/10\n"
        f"- Achillessehne R: 0/10\n- Müdigkeit: 1/5\n- Muskelkater: keine\n- Symptome: keine\n\n"
        f"Wetter morgen: {conditions}{tp_ctx}\n\n"
        f"Geplante Einheiten morgen: {workout['sport']}"
    )
    result = call_claude(system, user_msg)
    sportarten = result.get("sportarten", [])
    return {
        "workout_input": workout,
        "badge_expected": badge,
        "coach_output": sportarten,
        "beschreibung": sportarten[0].get("beschreibung") if sportarten else None,
        "badge_actual": sportarten[0].get("badge") if sportarten else None,
    }


def clean_title(title: str) -> str:
    for pfx in ("❌ ", "↩️ ", "🔥 ", "❄️ ", "☀️ ", "♨️ "):
        title = title.replace(pfx, "")
    return title.replace(" (KI)", "").replace(" (AI)", "").strip()


def _is_weather_sport(sport: str) -> bool:
    """Nur Lauf, Golf und Rad bekommen Wetter-Symbol."""
    s = (sport or "").lower()
    return any(x in s for x in ("lauf", "run", "golf", "bike", "rad", "cycl"))


def _is_indoor(title: str) -> bool:
    """Zwift, Indoor-Trainer, Laufband etc. sind wetterunabhängig."""
    return any(x in (title or "").lower() for x in ("zwift", "indoor", "laufband", "trainer"))


def _hourly_window_weather(hourly_wx: dict, day: str, start_iso: str, duration_s: int):
    """Stündliches Wetter für ein Workout-Zeitfenster aus vorab geladenen Batch-Daten."""
    if not start_iso or not hourly_wx.get(day):
        return None
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td2
        s = start_iso.rstrip("Z")
        if start_iso.endswith("Z"):
            s += "+00:00"
        dt = _dt.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(_tz(_td2(hours=2)))  # CEST approx
        start_h = dt.hour
        dur_h   = max(1, round((duration_s or 3600) / 3600))
        hours   = list(range(start_h, min(start_h + dur_h + 1, 24)))
        day_data = hourly_wx[day]
        relevant = [day_data[h] for h in hours if h in day_data]
        if not relevant:
            return None
        temps   = [r["temp"]   for r in relevant]
        precips = [r["precip"] for r in relevant]
        codes   = [r["code"]   for r in relevant]
        from collections import Counter as _Ctr
        dominant = _Ctr(codes).most_common(1)[0][0]
        return {
            "start_h":      start_h,
            "end_h":        start_h + dur_h,
            "temp_min":     round(min(temps), 1),
            "temp_max":     round(max(temps), 1),
            "precip_total": round(sum(precips), 1),
            "description":  WMO.get(dominant, f"Code {dominant}"),
        }
    except Exception:
        return None


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

    # Fetch weather once for this apply batch (best-effort)
    weather_for_apply: dict = {}
    try:
        weather_for_apply = await fetch_weather(athlete, day=day_offset)
    except Exception as _e:
        logger.warning("tp_apply: weather fetch failed: %s", _e)

    actions = []
    had_skip_stop = False
    for op in operations:
        workout_id = op.get("workout_id")
        badge      = op.get("badge", "GO")
        orig_title = op.get("orig_title", "")

        if not workout_id:
            continue

        base_title    = clean_title(orig_title)
        op_sport      = op.get("sport", "")
        is_swim       = any(x in (op_sport or "").lower() for x in ("swim", "schwimm"))
        user_override = op.get("user_override", False)

        if user_override:
            orig_desc = op.get("orig_description", "")
            note = "Athlete override – eigenes Gefühl"
            desc = f"{note}\n\n{orig_desc}".strip() if orig_desc else note
            try:
                await call_tp_mcp("tp_update_workout", {"workout_id": workout_id,
                                                        "title": base_title, "description": desc})
                actions.append({"workout_id": workout_id, "badge": "GO", "status": "ok",
                                "detail": f"Override: {base_title}"})
            except Exception as e:
                logger.error("tp_apply OVERRIDE: failed for %s: %s", workout_id, e)
                actions.append({"workout_id": workout_id, "badge": "GO", "status": "error", "detail": str(e)})
            continue

        if badge == "GO":
            # Nur Lauf, Golf, Rad — und nur Outdoor
            if not _is_weather_sport(op_sport) or _is_indoor(orig_title) or not weather_for_apply:
                continue
            is_hot  = weather_for_apply.get("is_hot")
            is_cold = weather_for_apply.get("is_cold")
            _td_desc = weather_for_apply.get("description", "")
            _tr      = weather_for_apply.get("rain_prob", 0)
            _tmin    = weather_for_apply.get("temp_min", "?")
            _tmax    = weather_for_apply.get("temp_max", "?")
            wx_desc  = f"Wetter {_td_desc}, {_tmin}–{_tmax}°C, Regen {_tr}%"
            go_args: dict = {"workout_id": workout_id, "description": wx_desc}
            if is_hot:
                go_args["title"] = f"♨️ {base_title}"
            elif is_cold:
                go_args["title"] = f"❄️ {base_title}"
            try:
                await call_tp_mcp("tp_update_workout", go_args)
                actions.append({"workout_id": workout_id, "badge": "GO", "status": "ok",
                                "detail": go_args.get("title", base_title), "wx": wx_desc})
            except Exception as e:
                logger.warning("tp_apply GO: weather update failed for %s: %s", workout_id, e)
            continue

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
            sport        = op.get("sport", "")
            _weather_icon = ""
            if _is_weather_sport(sport) and not _is_indoor(base_title):
                if weather_for_apply.get("is_hot"):
                    _weather_icon = "♨️ "
                elif weather_for_apply.get("is_cold"):
                    _weather_icon = "❄️ "
            new_title    = _weather_icon + T["tp_mod_new_title"].format(title=base_title)
            coach_rec    = op.get("description", "")
            reason       = op.get("reason", "")
            orig_dur     = op.get("duration_min")
            orig_tss     = op.get("tss")
            orig_desc    = op.get("orig_description", "")
            tp_struktur  = op.get("tp_struktur")   # TP interval structure from Claude
            distanz_m    = op.get("distanz_m")     # total swim distance in meters
            subtype_id   = op.get("subtype_id")    # TP sport subtype (Pool/OpenWater, Indoor/Road…)

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

            # Description: weather + coach adaptation + original for reference
            desc_parts: list = []
            if weather_for_apply:
                _temp_min = weather_for_apply.get("temp_min", "?")
                _temp_max = weather_for_apply.get("temp_max", "?")
                _desc_w   = weather_for_apply.get("description", "")
                _rain     = weather_for_apply.get("rain_prob", 0)
                desc_parts.append(f"Wetter: {_desc_w}, {_temp_min}–{_temp_max}°C, Regen {_rain}%")
            if reason:
                desc_parts.append(f"Angepasst wegen: {reason}")
            if coach_rec:
                desc_parts.append(coach_rec)
            if orig_desc:
                desc_parts.append(f"Original:\n{orig_desc}")
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
            if subtype_id is not None:
                create_args["subtype_id"] = int(subtype_id)
            if tp_struktur:
                create_args["structure"] = tp_struktur
                logger.info("tp_apply MOD: passing tp_struktur with %d steps", len(tp_struktur.get("steps", [])))
            if distanz_m:
                try:
                    create_args["distance_km"] = round(float(distanz_m) / 1000, 3)
                except (TypeError, ValueError):
                    pass

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
    athlete = await load_athlete_merged()
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
    muedigkeit: str = Form("1"),
    muskelkater: str = Form("keine"),
    symptome: str = Form("keine"),
    geplante_einheiten: str = Form(""),
    weather_data: str = Form(""),
    csv_file: Optional[UploadFile] = File(None),
):
    athlete = await load_athlete_merged()
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
        f"- Müdigkeit: {muedigkeit}/5\n"
        f"- Muskelkater: {muskelkater}\n"
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


_HISTORY_SPORT_MAP = {
    1: "Swim", 2: "Bike", 3: "Run", 4: "Brick", 5: "Swim",
    6: "Bike", 7: "Run", 12: "Swim", 13: "Bike", 14: "Run",
}

async def _fetch_history_weather(athlete: dict, dates: list) -> dict:
    """Einmaliger Open-Meteo-Call für alle History-Daten (past_days=7). Cached 6h."""
    range_key = ",".join(sorted(dates))
    cached = _history_wx_cache.get(range_key)
    if cached and (_time.time() - cached["ts"]) < _HISTORY_WX_TTL:
        return cached["wx"]
    lat = athlete.get("location", {}).get("lat", 52.30)
    lon = athlete.get("location", {}).get("lon", 13.25)
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
        f"&past_days=7&forecast_days=1&timezone=Europe%2FBerlin"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
        r.raise_for_status()
        daily = r.json().get("daily", {})
        date_list = daily.get("time", [])
        wx: dict = {}
        for i, d in enumerate(date_list):
            if d not in dates:
                continue
            temp_max = float((daily.get("temperature_2m_max") or [0])[i] or 0)
            temp_min = float((daily.get("temperature_2m_min") or [0])[i] or 0)
            wx[d] = {"is_hot": temp_max > 28, "is_cold": temp_max < 0,
                     "temp_max": temp_max, "temp_min": temp_min}
        _history_wx_cache[range_key] = {"ts": _time.time(), "wx": wx}
        logger.info("_fetch_history_weather: %d/%d dates matched", len(wx), len(dates))
        return wx
    except Exception as e:
        logger.warning("_fetch_history_weather failed: %s", e)
        return {}


@app.get("/api/tp/workouts/history")
async def tp_workouts_history(days: int = 5):
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        return JSONResponse({"available": False, "days": []}, headers=_NO_CACHE)
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()
    try:
        # Direkt per MCP — kein Claude-Umweg, kein Timeout-Risiko
        raw = await call_tp_mcp("tp_get_workouts", {
            "start_date": start, "end_date": end, "type": "completed"
        })
        # raw ist Liste oder dict mit Liste
        items = raw if isinstance(raw, list) else raw.get("workouts", raw.get("items", []))
        # Pro Tag gruppieren
        by_date: dict = {}
        for w in (items or []):
            wid   = str(w.get("workoutId") or w.get("id") or "")
            title = w.get("title") or w.get("name") or ""
            day   = (w.get("workoutDay") or w.get("date") or "")[:10]
            dur_s = w.get("totalTime") or w.get("totalTimePlanned") or 0
            dur_m = round(dur_s / 60) if dur_s else None
            tss   = w.get("tssActual") or w.get("tssPlanned") or w.get("tss") or None
            st    = w.get("startTime") or w.get("startTimePlanned") or ""
            stid  = w.get("workoutTypeValueId") or w.get("sportTypeId")
            sport = (w.get("sport") or w.get("sportType") or
                     _HISTORY_SPORT_MAP.get(stid, "") or str(stid or ""))
            if not wid or not day:
                continue
            by_date.setdefault(day, []).append({
                "id": wid, "sport": sport, "title": title,
                "duration_min": dur_m, "tss": tss,
                "start_time": st, "subtype_id": stid,
            })
        grouped = [{"date": d, "workouts": ws}
                   for d, ws in sorted(by_date.items())]
        # Wetterdaten einmalig für alle vorhandenen Daten abrufen (cached 6h)
        athlete = load_athlete()
        all_dates = [e["date"] for e in grouped]
        wx_by_date = await _fetch_history_weather(athlete, all_dates) if all_dates else {}
        for entry in grouped:
            entry["weather"] = wx_by_date.get(entry["date"])
        logger.info("tp_workouts_history ok: %d days, %d total, %d wx",
                    len(grouped), sum(len(e["workouts"]) for e in grouped), len(wx_by_date))
        return JSONResponse({"available": True, "days": grouped}, headers=_NO_CACHE)
    except Exception as e:
        logger.error("tp_workouts_history error: %s", e)
        return JSONResponse({"available": False, "days": [], "error": str(e)[:200]}, headers=_NO_CACHE)


def _run_analysis_job(job_id: str, tp_url: str, key: str, prompt: str):
    """Läuft in eigenem Thread — kein Timeout durch Railway/Browser."""
    import re as _re
    try:
        c = anthropic.Anthropic(api_key=key, http_client=_tp_http_long)
        msg = c.beta.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            betas=["mcp-client-2025-11-20"],
            mcp_servers=[{"type": "url", "url": tp_url, "name": "trainingpeaks"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "trainingpeaks"}],
            system="Du bist ein erfahrener Triathlon-Coach. Antworte ausschließlich mit gültigem JSON ohne Markdown.",
            messages=[{"role": "user", "content": prompt}],
        )
        # Take the LAST text block — earlier blocks are reasoning/narration, final block is the JSON
        raw = ""
        for block in msg.content:
            if hasattr(block, "text") and block.text:
                raw = block.text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            m = _re.search(r'\{.*\}', raw, _re.DOTALL)
            result = json.loads(m.group()) if m else {"bewertung": "ok", "urteil": raw[:400], "naechster_schritt": ""}
        logger.info("analysis job %s done: bewertung=%s", job_id, result.get("bewertung"))
        _analysis_jobs[job_id] = {"status": "done", "result": result}
    except Exception as e:
        logger.error("analysis job %s error: %s", job_id, e)
        _analysis_jobs[job_id] = {"status": "error", "error": str(e)[:300]}


def _run_analysis_job_fast(job_id: str, key: str, prompt: str):
    """Schneller Pfad wenn FIT-Daten vorhanden — kein MCP nötig."""
    import re as _re
    try:
        c = anthropic.Anthropic(api_key=key)
        msg = c.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system="Du bist ein erfahrener Triathlon-Coach. Antworte ausschließlich mit gültigem JSON ohne Markdown.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            m = _re.search(r'\{.*\}', raw, _re.DOTALL)
            result = json.loads(m.group()) if m else {"bewertung": "ok", "urteil": raw[:400], "naechster_schritt": ""}
        logger.info("analysis job %s done (fast): bewertung=%s", job_id, result.get("bewertung"))
        _analysis_jobs[job_id] = {"status": "done", "result": result}
    except Exception as e:
        logger.error("analysis job %s error (fast): %s", job_id, e)
        _analysis_jobs[job_id] = {"status": "error", "error": str(e)[:300]}


def _build_analysis_prompt(athlete: dict, a_race: dict, workout_id: str, sport: str,
                            title: str, target_date: str, fit_data: dict,
                            weather_data: dict = None, tp_data: dict = None) -> str:
    base = T["coach_analysis_prompt"].format(
        name=athlete.get("name", "Hendrik"),
        ftp=athlete.get("ftp_watt", 286),
        run_threshold=athlete.get("run_threshold_pace", "5:20"),
        css=athlete.get("css_per_100m", "2:20"),
        race_name=a_race.get("name", "Castle Triathlon Malbork"),
        race_date=a_race.get("date", "2026-09-06"),
        race_goal=a_race.get("goal_total", "10:50"),
        weight=athlete.get("weight_kg", 84),
        workout_id=workout_id or "unbekannt",
        sport=sport or "unbekannt",
        title=title or sport,
        date=target_date,
    )
    if weather_data and weather_data.get("description"):
        base += (
            f"\n\nWetter am {target_date}: {weather_data['description']}, "
            f"{weather_data.get('temp_min','?')}–{weather_data.get('temp_max','?')}°C, "
            f"Regen {weather_data.get('rain_prob',0)}%."
        )
    if tp_data:
        lines = ["\n\n--- TRAININGPEAKS IST-DATEN ---"]
        tp_label_map = {
            "totalTime": "Dauer (s)", "totalTimePlanned": "Dauer geplant (s)",
            "distanceInMeters": "Distanz (m)", "tssActual": "TSS (Ist)", "tssPlanned": "TSS (Plan)",
            "averageHeartRateInBeatsPerMinute": "Ø HF", "maxHeartRateInBeatsPerMinute": "Max HF",
            "averageWatts": "Ø Leistung (W)", "normalizedPower": "NP (W)",
            "averagePaceInMinutesPerKilometer": "Ø Pace (min/km)",
            "totalWork": "Gesamtarbeit (kJ)",
            "coachComments": "Coach-Notizen", "description": "Beschreibung",
        }
        for k, label in tp_label_map.items():
            v = tp_data.get(k)
            if v is not None and v != "":
                lines.append(f"- {label}: {v}")
        base += "\n".join(lines)
    if fit_data:
        lines = ["\n\n--- FIT-DATEI (TATSÄCHLICHE IST-DATEN — PRIMÄRE QUELLE) ---",
                 "WICHTIG: Diese Werte sind die realen Messdaten dieser Einheit. Nutze sie als primäre Grundlage. Sage NICHT, dass keine Ist-Daten vorliegen."]
        label_map = {
            "dauer_min": "Dauer", "distanz_km": "Distanz", "avg_power_w": "Ø Leistung",
            "max_power_w": "Max Leistung", "normalized_power_w": "NP",
            "avg_hr": "Ø HF", "max_hr": "Max HF", "avg_kadenz": "Ø Kadenz",
            "avg_pace_min_km": "Ø Pace", "tss": "TSS", "total_work_kj": "Gesamtarbeit",
            "sport": "Sport (FIT)", "sub_sport": "Sub-Sport",
        }
        for k, label in label_map.items():
            v = fit_data.get(k)
            if v is not None:
                unit = {"dauer_min": " min", "distanz_km": " km", "avg_power_w": " W",
                        "max_power_w": " W", "normalized_power_w": " W",
                        "avg_hr": " bpm", "max_hr": " bpm", "avg_kadenz": " rpm",
                        "total_work_kj": " kJ"}.get(k, "")
                lines.append(f"- {label}: {v}{unit}")
        if fit_data.get("laps"):
            lines.append("Splits:")
            for lap in fit_data["laps"]:
                parts = []
                if "t_min" in lap:
                    parts.append(f"{lap['t_min']} min")
                if "km" in lap:
                    parts.append(f"{lap['km']} km")
                if "avg_w" in lap:
                    parts.append(f"{lap['avg_w']} W")
                if "avg_hr" in lap:
                    parts.append(f"{lap['avg_hr']} bpm")
                if "pace" in lap:
                    parts.append(f"{lap['pace']}/km")
                lines.append("  • " + " | ".join(parts))
        lines.append("Nutze diese FIT-Daten als primäre Ist-Daten für die Analyse.")
        base += "\n".join(lines)
    return base


@app.post("/api/workout/analyze")
async def workout_analyze(
    workout_id: str = Form(""),
    sport: str = Form(""),
    title: str = Form(""),
    workout_date: str = Form(""),
    start_time: str = Form(""),
    fit_file: Optional[UploadFile] = File(None),
):
    tp_url = os.environ.get("TP_MCP_URL", "")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(500, T["err_api_key_missing"])
    if not tp_url:
        raise HTTPException(400, T["err_tp_url_missing"])

    # FIT-Datei sofort parsen (sync, schnell) bevor der Thread startet
    fit_data = {}
    if fit_file and fit_file.filename:
        try:
            fit_bytes = await fit_file.read()
            fit_data = parse_fit_summary(fit_bytes)
            logger.info("FIT parsed: %s keys for %s", len(fit_data), fit_file.filename)
        except Exception as e:
            logger.warning("FIT read error: %s", e)

    athlete = load_athlete()
    a_race = next((r for r in athlete.get("races", []) if r.get("type") == "A"), {})
    target_date = workout_date or date.today().isoformat()

    # Wetter als private_notes in TP hinterlegen (best-effort, description bleibt unangetastet)
    weather_on_date: dict = {}
    if workout_id:
        try:
            # Priorität: 1) TP-Startzeit, 2) FIT-Startzeit, 3) Tages-Fallback
            tp_start = start_time.strip() if start_time else ""
            fit_start = fit_data.get("start_time_utc", "")
            fit_end   = fit_data.get("end_time_utc", "")

            if tp_start:
                # Endzeit aus TP-Startzeit + duration_min berechnen
                from datetime import datetime as _dt
                dur_min = fit_data.get("dauer_min")
                st_dt = _dt.fromisoformat(tp_start)
                if dur_min:
                    et_dt = st_dt + timedelta(minutes=float(dur_min))
                    weather_on_date = await fetch_weather_for_workout(
                        athlete, st_dt.isoformat(), et_dt.isoformat()
                    )
                else:
                    # Kein duration — 1h annehmen
                    et_dt = st_dt + timedelta(hours=1)
                    weather_on_date = await fetch_weather_for_workout(
                        athlete, st_dt.isoformat(), et_dt.isoformat()
                    )
            elif fit_start and fit_end:
                weather_on_date = await fetch_weather_for_workout(athlete, fit_start, fit_end)
            else:
                weather_on_date = await fetch_weather_for_date(athlete, target_date)

            if "avg_temp" in weather_on_date:
                _w_note = (
                    f"Wetter {weather_on_date['start_local']}–{weather_on_date['end_local']}: "
                    f"{weather_on_date.get('description','?')}, "
                    f"Ø {weather_on_date.get('avg_temp','?')}°C "
                    f"({weather_on_date.get('temp_min','?')}–{weather_on_date.get('temp_max','?')}°C), "
                    f"Niederschlag {weather_on_date.get('precip_mm',0)}mm"
                )
            else:
                _w_note = (
                    f"Wetter {target_date}: {weather_on_date.get('description','?')}, "
                    f"{weather_on_date.get('temp_min','?')}–{weather_on_date.get('temp_max','?')}°C, "
                    f"Regen {weather_on_date.get('rain_prob',0)}%"
                )
            logger.info("workout_analyze: weather note prepared for %s on %s (not written to TP — field unsupported)", workout_id, target_date)
        except Exception as _we:
            logger.warning("workout_analyze: weather update skipped: %s", _we)

    # TP-Workout direkt vorab holen — kein MCP-Roundtrip durch Claude nötig
    tp_workout_data: dict = {}
    if workout_id and tp_url:
        try:
            tp_workout_data = await call_tp_mcp("tp_get_workout", {"workout_id": workout_id})
            if not isinstance(tp_workout_data, dict):
                tp_workout_data = {}
            logger.info("workout_analyze: tp_get_workout ok for %s", workout_id)
        except Exception as _te:
            logger.warning("workout_analyze: tp_get_workout failed: %s", _te)

    prompt = _build_analysis_prompt(athlete, a_race, workout_id, sport, title, target_date,
                                    fit_data, weather_on_date, tp_workout_data)
    job_id = uuid.uuid4().hex[:10]
    _analysis_jobs[job_id] = {"status": "pending", "has_fit": bool(fit_data)}
    # Immer schneller Pfad — TP-Daten sind bereits im Prompt enthalten
    t = threading.Thread(target=_run_analysis_job_fast, args=(job_id, key, prompt), daemon=True)
    t.start()
    logger.info("analysis job %s started for %s on %s (fit=%s, tp=%s)",
                job_id, title, target_date, bool(fit_data), bool(tp_workout_data))
    return JSONResponse({"job_id": job_id, "has_fit": bool(fit_data), "weather": weather_on_date or None},
                        headers=_NO_CACHE)


@app.get("/api/workout/analyze/{job_id}")
async def workout_analyze_status(job_id: str):
    job = _analysis_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    return JSONResponse(job, headers=_NO_CACHE)


@app.post("/api/debug/fit-parse")
async def debug_fit_parse(fit_file: UploadFile = File(...)):
    """Gibt das parse_fit_summary-Ergebnis zurück — zum Debuggen der FIT-Verarbeitung."""
    try:
        fit_bytes = await fit_file.read()
        result = parse_fit_summary(fit_bytes)
        return JSONResponse({"parsed_keys": list(result.keys()), "data": result}, headers=_NO_CACHE)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500, headers=_NO_CACHE)


@app.post("/api/admin/backfill-weather")
async def backfill_weather(days: int = 30):
    """Schreibt Wetterbeschreibung + ggf. Extrem-Symbol in vergangene TP-Workouts.
    Nur Lauf, Golf, Rad. Beschreibung immer (mit Stunden-Fenster wenn möglich).
    Titel-Symbol nur bei >28°C (♨️) oder <0°C (❄️).
    Aufruf: curl -X POST 'https://<railway-url>/api/admin/backfill-weather?days=30'
    """
    tp_url = os.environ.get("TP_MCP_URL", "")
    if not tp_url:
        raise HTTPException(400, T["err_tp_url_missing"])

    days = max(1, min(days, 365))
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end   = today.isoformat()

    # 1. TP-Workouts holen (completed)
    try:
        raw = await call_tp_mcp("tp_get_workouts", {
            "start_date": start, "end_date": end, "type": "completed"
        })
    except Exception as e:
        raise HTTPException(500, f"TP-Fetch fehlgeschlagen: {e}")

    items = raw if isinstance(raw, list) else raw.get("workouts", raw.get("items", []))
    by_date: dict = {}
    for w in (items or []):
        wid        = str(w.get("workoutId") or w.get("id") or "")
        day        = (w.get("workoutDay") or w.get("date") or "")[:10]
        sport      = (w.get("sport") or w.get("sportType") or "")
        title      = w.get("title") or w.get("name") or ""
        start_time = w.get("startTime") or ""
        duration_s = int(w.get("totalTime") or 0)
        existing_desc = (w.get("description") or w.get("notes") or "").strip()
        if not wid or not day:
            continue
        by_date.setdefault(day, []).append({
            "id": wid, "sport": sport, "title": title,
            "start_time": start_time, "duration_s": duration_s,
            "existing_desc": existing_desc,
        })

    if not by_date:
        return JSONResponse({"updated": 0, "skipped": 0, "errors": 0,
                             "detail": "Keine completed Workouts gefunden"})

    # 2. Wetterdaten in einem Batch-Call holen (täglich + stündlich)
    athlete   = load_athlete()
    all_dates = list(by_date.keys())
    cutoff    = (today - timedelta(days=7)).isoformat()
    recent    = [d for d in all_dates if d > cutoff]
    archive   = [d for d in all_dates if d <= cutoff]
    lat = athlete.get("location", {}).get("lat", 52.30)
    lon = athlete.get("location", {}).get("lon", 13.25)

    daily_wx: dict = {}
    hourly_wx: dict = {}  # date -> {hour -> {temp, precip, code}}

    async def _fetch_daily(url: str, dates: list) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
        r.raise_for_status()
        d_data = r.json().get("daily", {})
        result = {}
        for i, d in enumerate(d_data.get("time", [])):
            if d not in dates:
                continue
            tmax = float((d_data.get("temperature_2m_max") or [0])[i] or 0)
            tmin = float((d_data.get("temperature_2m_min") or [0])[i] or 0)
            rain = int((d_data.get("precipitation_probability_max") or [0])[i] or 0)
            code = int((d_data.get("weather_code") or [0])[i] or 0)
            result[d] = {
                "temp_max": tmax, "temp_min": tmin, "rain_prob": rain,
                "description": WMO.get(code, f"Code {code}"),
                "is_hot": tmax > 28, "is_cold": tmax < 0,
            }
        return result

    async def _fetch_hourly(url: str, dates: list) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url)
        r.raise_for_status()
        h_data  = r.json().get("hourly", {})
        times   = h_data.get("time", [])
        temps   = h_data.get("temperature_2m", [])
        precips = h_data.get("precipitation", [])
        codes   = h_data.get("weather_code", [])
        result: dict = {}
        for i, ts in enumerate(times):
            d = ts[:10]
            if d not in dates:
                continue
            h = int(ts[11:13])
            result.setdefault(d, {})[h] = {
                "temp":   float(temps[i]   or 0) if i < len(temps)   else 0,
                "precip": float(precips[i] or 0) if i < len(precips) else 0,
                "code":   int(codes[i]     or 0) if i < len(codes)   else 0,
            }
        return result

    try:
        if recent:
            base_r = (f"https://api.open-meteo.com/v1/forecast"
                      f"?latitude={lat}&longitude={lon}"
                      f"&past_days=7&forecast_days=1&timezone=Europe%2FBerlin")
            daily_wx.update(await _fetch_daily(
                base_r + "&daily=temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,weather_code", recent))
            hourly_wx.update(await _fetch_hourly(
                base_r + "&hourly=temperature_2m,precipitation,weather_code", recent))
        if archive:
            arc_s   = min(archive)
            arc_e   = max(archive)
            base_a  = (f"https://archive-api.open-meteo.com/v1/archive"
                       f"?latitude={lat}&longitude={lon}"
                       f"&start_date={arc_s}&end_date={arc_e}"
                       f"&timezone=Europe%2FBerlin")
            daily_wx.update(await _fetch_daily(
                base_a + "&daily=temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,weather_code", archive))
            hourly_wx.update(await _fetch_hourly(
                base_a + "&hourly=temperature_2m,precipitation,weather_code", archive))
    except Exception as e:
        raise HTTPException(500, f"Wetter-Fetch fehlgeschlagen: {e}")

    # 3. Pro Workout: Beschreibung + ggf. Titel-Symbol schreiben
    updated = skipped = errors = 0
    results = []
    for day_str, workouts in sorted(by_date.items()):
        d_wx = daily_wx.get(day_str)
        if not d_wx:
            skipped += len(workouts)
            results.append({"date": day_str, "status": "no_weather", "workouts": len(workouts)})
            continue

        for w in workouts:
            base = clean_title(w["title"])
            is_relevant = _is_weather_sport(w["sport"]) and not _is_indoor(w["title"])
            has_symbol  = w["title"] != base  # title had ♨️ or ❄️ prefix

            if not is_relevant:
                # Indoor oder falsche Sportart: Symbol ggf. entfernen (Aufräumen)
                if has_symbol:
                    try:
                        await call_tp_mcp("tp_update_workout",
                                          {"workout_id": w["id"], "title": base})
                        updated += 1
                        results.append({"date": day_str, "sport": w["sport"],
                                         "workout": w["title"], "status": "cleaned",
                                         "title": base})
                    except Exception as e:
                        errors += 1
                else:
                    skipped += 1
                continue

            # Stündliches Wetter für das Einheits-Zeitfenster (bevorzugt)
            h_wx = _hourly_window_weather(hourly_wx, day_str, w["start_time"], w["duration_s"])
            if h_wx:
                wx_note = (f"Wetter {h_wx['start_h']:02d}–{h_wx['end_h']:02d}h: "
                           f"{h_wx['description']}, "
                           f"{h_wx['temp_min']}–{h_wx['temp_max']}°C, "
                           f"{h_wx['precip_total']}mm Regen")
            else:
                wx_note = (f"Wetter: {d_wx['description']}, "
                           f"{d_wx['temp_min']}–{d_wx['temp_max']}°C, "
                           f"Regen {d_wx['rain_prob']}%")

            update_args: dict = {"workout_id": w["id"]}

            # Wetter anhängen: bestehendes behalten, nur Wetter-Zeile aktualisieren
            import re as _re
            existing = w["existing_desc"]
            base_desc = _re.sub(r'\n*Wetter[^\n]*', '', existing).strip()
            update_args["description"] = (base_desc + "\n\n" + wx_note) if base_desc else wx_note

            # Titel-Symbol nur bei Extrem
            if d_wx["is_hot"]:
                update_args["title"] = f"♨️ {base}"
            elif d_wx["is_cold"]:
                update_args["title"] = f"❄️ {base}"
            elif has_symbol:
                update_args["title"] = base


            try:
                await call_tp_mcp("tp_update_workout", update_args)
                updated += 1
                results.append({
                    "date": day_str, "sport": w["sport"], "workout": w["title"],
                    "status": "ok", "note": wx_note,
                    "title": update_args.get("title", "(unverändert)"),
                })
            except Exception as e:
                errors += 1
                results.append({"date": day_str, "workout": w["title"],
                                 "status": "error", "error": str(e)[:100]})

    logger.info("backfill-weather: %d updated, %d skipped, %d errors over %d days",
                updated, skipped, errors, days)
    return JSONResponse({"updated": updated, "skipped": skipped, "errors": errors,
                         "days_searched": days, "results": results})


