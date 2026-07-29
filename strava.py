"""Strava-Anbindung für den Analyse-Tab.

Ersetzt den manuellen FIT-Datei-Export für den Normalfall: die App holt die
zu Sportart+Datum passende Strava-Aktivität selbst und bringt sie in exakt
dieselbe Dict-Form wie `parse_fit_summary()` (app.py) — der Analyst sieht
keinen Unterschied zwischen hochgeladener FIT-Datei und Strava-Aktivität,
beides sind echte Gerätemesswerte.

Kein eigener MCP-Service (anders als TrainingPeaks) — Stravas REST-API ist
einfach genug für direkte httpx-Calls, dieselbe Bauart wie die Wetter-Anbindung.

Auth: OAuth2 mit Refresh-Token. `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET` und
ein initialer `STRAVA_REFRESH_TOKEN` (einmalig per Browser-Autorisierung
geholt) kommen aus der Umgebung; danach verwaltet dieses Modul seinen eigenen,
aktuellen Stand in `DATA_DIR/strava_token.json` — Strava tauscht das
Refresh-Token bei jedem Refresh potenziell aus, das muss dauerhaft landen,
nicht nur im statischen ENV-Wert. Ohne Client-ID/Secret bleibt die Funktion
`fetch_matching_activity_as_fit` bei `None`, der manuelle FIT-Upload bleibt
dann der einzige Weg — kein Unterschied zum bisherigen Verhalten.
"""
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SPORT_GRUPPEN = {
    "Run": {"Run", "TrailRun", "VirtualRun"},
    "Bike": {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide"},
    "Swim": {"Swim"},
}


def _data_dir() -> Path:
    roh = os.environ.get("DATA_DIR", "").strip()
    return Path(roh) if roh else Path(__file__).parent


def _token_file() -> Path:
    return _data_dir() / "strava_token.json"


def _load_state() -> dict:
    """Liest den zuletzt gespeicherten Token-Stand, sonst den ENV-Seed."""
    pfad = _token_file()
    if pfad.exists():
        try:
            return json.loads(pfad.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("strava: Token-Datei unlesbar, ignoriere: %s", e)
    seed = os.environ.get("STRAVA_REFRESH_TOKEN")
    return {"refresh_token": seed} if seed else {}


def _save_state(state: dict) -> None:
    try:
        _token_file().write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.warning("strava: Token konnte nicht gespeichert werden: %s", e)


async def _get_access_token() -> Optional[str]:
    """Liefert ein gültiges Access-Token, refresht bei Bedarf. None statt Exception,
    wenn Credentials fehlen oder der Refresh fehlschlägt — degradiert wie das
    bestehende TP_MCP_URL-Muster."""
    if not (os.environ.get("STRAVA_CLIENT_ID") and os.environ.get("STRAVA_CLIENT_SECRET")):
        return None
    state = _load_state()
    if not state.get("refresh_token"):
        return None
    if state.get("access_token") and state.get("expires_at", 0) > time.time() + 60:
        return state["access_token"]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://www.strava.com/oauth/token", data={
                "client_id": os.environ["STRAVA_CLIENT_ID"],
                "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": state["refresh_token"],
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("strava: Token-Refresh fehlgeschlagen: %s", e)
        return None

    neuer_stand = {
        "refresh_token": data.get("refresh_token", state["refresh_token"]),
        "access_token": data["access_token"],
        "expires_at": data["expires_at"],
    }
    _save_state(neuer_stand)
    return neuer_stand["access_token"]


def _tages_fenster_epoch(target_date: str) -> tuple:
    """±1 Tag um target_date als UTC-Epoch — Zeitzonen-Puffer für die grobe
    Vorauswahl, die exakte Filterung passiert danach über start_date_local."""
    d = date.fromisoformat(target_date)
    start = datetime.combine(d - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    ende = datetime.combine(d + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
    return int(start.timestamp()), int(ende.timestamp())


async def _get_activities(token: str, target_date: str) -> list:
    after_ts, before_ts = _tages_fenster_epoch(target_date)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://www.strava.com/api/v3/athlete/activities",
            params={"after": after_ts, "before": before_ts, "per_page": 30},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _get_laps(token: str, activity_id) -> list:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://www.strava.com/api/v3/activities/{activity_id}/laps",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


def _parse_local(iso_ohne_zone: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat((iso_ohne_zone or "").replace("Z", ""))
    except ValueError:
        return None


def match_activity(kandidaten: list, sport_hint: str, start_time_hint: str = "") -> Optional[dict]:
    """Wählt aus den Tageskandidaten die passendste Aktivität.

    Erst nach Sportart-Gruppe filtern (falls die Gruppe etwas liefert — sonst
    lieber ungefiltert weitersuchen als fälschlich leer laufen), danach bei
    mehreren Treffern die zeitlich nächste zur geplanten Startzeit, ohne
    Zeithinweis die längste (Haupteinheit vor kurzen Zusatzaktivitäten).
    """
    if not kandidaten:
        return None
    pool = kandidaten
    gruppe = _SPORT_GRUPPEN.get(sport_hint)
    if gruppe:
        gefiltert = [a for a in kandidaten if a.get("sport_type") in gruppe]
        if gefiltert:
            pool = gefiltert

    hint = _parse_local(start_time_hint) if start_time_hint else None
    if hint:
        def naehe(a):
            a_dt = _parse_local(a.get("start_date_local", ""))
            return abs((a_dt - hint).total_seconds()) if a_dt else float("inf")
        return min(pool, key=naehe)
    return max(pool, key=lambda a: a.get("moving_time", 0))


def _pace_str(speed_m_pro_s: float) -> str:
    pace_sec = 1000 / speed_m_pro_s
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"


def _activity_to_fit_shape(activity: dict, laps: Optional[list]) -> dict:
    """Bringt eine Strava-Aktivität + Laps in exakt die Dict-Form von
    parse_fit_summary() (app.py) — gleiche Keys, gleiche Einheiten."""
    summary = {}

    moving = activity.get("moving_time")
    if moving:
        summary["dauer_min"] = round(moving / 60, 1)

    dist = activity.get("distance")
    if dist:
        summary["distanz_km"] = round(dist / 1000, 2)

    for quelle_key, ziel_key in [
        ("average_watts", "avg_power_w"), ("max_watts", "max_power_w"),
        ("weighted_average_watts", "normalized_power_w"),
        ("average_heartrate", "avg_hr"), ("max_heartrate", "max_hr"),
        ("average_cadence", "avg_kadenz"),
    ]:
        v = activity.get(quelle_key)
        if v:
            summary[ziel_key] = round(v)

    if dist and moving:
        speed = dist / moving
        if speed > 0:
            summary["avg_pace_min_km"] = _pace_str(speed)

    kj = activity.get("kilojoules")
    if kj:
        summary["total_work_kj"] = round(kj, 1)

    sport = activity.get("sport_type") or activity.get("type")
    if sport:
        summary["sport"] = str(sport)

    lap_list = []
    for lap in (laps or [])[:25]:
        entry = {}
        t = lap.get("elapsed_time")
        d = lap.get("distance")
        p = lap.get("average_watts")
        h = lap.get("average_heartrate")
        sp = lap.get("average_speed")
        if t:
            entry["t_min"] = round(t / 60, 1)
        if d:
            entry["km"] = round(d / 1000, 2)
        if p:
            entry["avg_w"] = round(p)
        if h:
            entry["avg_hr"] = round(h)
        if sp and sp > 0:
            entry["pace"] = _pace_str(sp)
        if entry:
            lap_list.append(entry)
    if lap_list:
        summary["laps"] = lap_list

    return summary


async def fetch_matching_activity_as_fit(*, target_date: str, sport_hint: str = "",
                                         start_time_hint: str = "") -> Optional[dict]:
    """Holt die zu Datum+Sportart passende Strava-Aktivität, fertig in der
    FIT-Dict-Form. None ohne Credentials, ohne Token oder ohne Treffer —
    der Aufrufer fällt dann auf den bisherigen Ablauf zurück."""
    token = await _get_access_token()
    if not token:
        return None
    aktivitaeten = await _get_activities(token, target_date)
    kandidaten = [a for a in aktivitaeten if (a.get("start_date_local") or "")[:10] == target_date]
    treffer = match_activity(kandidaten, sport_hint, start_time_hint)
    if not treffer:
        return None
    laps = await _get_laps(token, treffer["id"])
    return _activity_to_fit_shape(treffer, laps)
