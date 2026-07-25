"""Orchestrator für den Coach-Ablauf.

Der Kontrollfluss liegt hier, nicht bei den Agents — die Agents reden nicht
miteinander, sie liefern typisierte Urteile an den Orchestrator zurück.

    Mediziner ┐
              ├─(parallel)─→ Chefcoach ─→ Architekt (nur MOD, parallel) ─→ Vertrag
    Wetter    ┘

Deterministisch, ohne Modell:
  - GO-Einheiten übernehmen die Original-Beschreibung unverändert
  - SKIP-Einheiten brauchen keine Beschreibung
  - Ernährung kommt aus der Tabelle in athlete.json, nach fertiger Dauer
  - Schlaf-Flags, Baseline, Wetterschwellen, tp_apply liegen ohnehin in Code
"""
import asyncio
import logging
from typing import Optional

from agents import architect, head_coach, medic, weather
from agents.base import HAIKU
from nutrition import nutrition_for_duration

logger = logging.getLogger(__name__)

# Sportarten-Normalisierung: TP liefert englische Bezeichner, die Agent-Schemas
# arbeiten mit den deutschen Enum-Werten.
_SPORT_MAP = {
    "swim": "Schwimmen", "schwimm": "Schwimmen", "pool": "Schwimmen",
    "bike": "Rad", "rad": "Rad", "cycl": "Rad", "zwift": "Rad",
    "run": "Laufen", "lauf": "Laufen",
    "strength": "Kraft", "kraft": "Kraft",
}


def normalize_sport(sport: str) -> str:
    s = (sport or "").lower()
    for needle, name in _SPORT_MAP.items():
        if needle in s:
            return name
    return "Sonstiges"


def _wetter_zeile(w: dict) -> str:
    return (f"{w.get('description', '?')}, "
            f"{w.get('temp_min', '?')}–{w.get('temp_max', '?')} °C, "
            f"Regen {w.get('rain_prob', 0)} %")


async def _baue_einheit(*, entscheidung: dict, workout: Optional[dict], athlete: dict,
                        wetter_zeile: str, model: str) -> dict:
    """Baut einen Eintrag im Frontend-Vertrag aus Entscheidung + Original-Workout."""
    badge = entscheidung.get("badge", "GO")
    sport = entscheidung.get("sport", "")
    workout = workout or {}
    orig_desc = (workout.get("description") or "").strip()
    dauer = workout.get("duration_min")
    beschreibung, tp_struktur, distanz_m = orig_desc, None, None

    if badge == "MOD":
        # Nur hier läuft der Architekt.
        gebaut = await asyncio.to_thread(
            architect.run, athlete=athlete, workout=workout,
            auftrag={"begruendung": entscheidung.get("begruendung", ""),
                     "anpassung": entscheidung.get("anpassung", {})},
            wetter_zeile=wetter_zeile, model=model,
        )
        beschreibung = gebaut["beschreibung"]
        tp_struktur = gebaut.get("tp_struktur")
        distanz_m = gebaut.get("distanz_m")
        dauer = max(20, int(gebaut.get("dauer_min") or dauer or 20))
    elif badge == "SKIP":
        beschreibung = ""

    return {
        "sport": sport,
        "badge": badge,
        "details": entscheidung.get("details", ""),
        "beschreibung": beschreibung,
        # Ernährung deterministisch aus der fertigen Dauer — kein Modell.
        "ernaehrung": "" if badge == "SKIP" else nutrition_for_duration(
            dauer, athlete.get("nutrition", {})
        ),
        "tp_struktur": tp_struktur,
        "distanz_m": distanz_m,
        "_begruendung": entscheidung.get("begruendung", ""),
    }


async def run_check(
    *,
    athlete: dict,
    a_race: Optional[dict],
    baseline: Optional[dict],
    koerper: dict,
    weather_data: dict,
    tp_workouts: Optional[list] = None,
    sleep: Optional[dict] = None,
    wasser_temp=None,
    tag: str = "morgen",
    model: str = HAIKU,
) -> dict:
    """Führt den kompletten Check aus und liefert den Frontend-Vertrag.

    Der Aufrufer hängt nur noch `weather` und ggf. `sleep_flags` an.
    """
    tp_workouts = tp_workouts or []

    sportarten = list(dict.fromkeys(
        normalize_sport(w.get("sport", "")) for w in tp_workouts
    )) or [normalize_sport(s) for s in koerper.get("geplante_einheiten", [])]
    sportarten = [s for s in dict.fromkeys(sportarten) if s]
    titel = [w.get("title", "") for w in tp_workouts if w.get("title")]

    # Stufe 1: die beiden Spezialisten sind unabhängig voneinander → parallel.
    # asyncio.to_thread, weil das anthropic-SDK hier synchron aufgerufen wird.
    medic_result, weather_result = await asyncio.gather(
        asyncio.to_thread(
            medic.run, koerper=koerper, sportarten=sportarten,
            sleep=sleep, baseline=baseline, model=model,
        ),
        asyncio.to_thread(
            weather.run, weather=weather_data, sportarten=sportarten, titel=titel,
            swim_min_c=athlete.get("swim_outdoor_min_celsius", 15),
            wasser_temp=wasser_temp, tag=tag, model=model,
        ),
    )
    logger.info(
        "orchestrator: medic=%s wetter=%s sportarten=%s",
        medic_result.get("gesamturteil"), weather_result.get("gesamtlage"), sportarten,
    )

    # Stufe 2: der Chefcoach entscheidet — ohne auszuformulieren.
    entscheidung = await asyncio.to_thread(
        head_coach.run,
        athlete=athlete, a_race=a_race, medic=medic_result, wetter=weather_result,
        tp_workouts=tp_workouts, tag=tag, model=model,
    )

    # Stufe 3: der Architekt formuliert die MOD-Einheiten aus — parallel.
    wetter_zeile = _wetter_zeile(weather_data)
    einheiten = entscheidung.get("sportarten", [])
    ergebnisse = await asyncio.gather(*[
        _baue_einheit(
            entscheidung=e,
            workout=tp_workouts[i] if i < len(tp_workouts) else None,
            athlete=athlete, wetter_zeile=wetter_zeile, model=model,
        )
        for i, e in enumerate(einheiten)
    ])

    n_mod = sum(1 for e in einheiten if e.get("badge") == "MOD")
    logger.info("orchestrator: %d Einheiten, davon %d über den Architekten",
                len(ergebnisse), n_mod)

    return {
        "status": entscheidung.get("status", "green"),
        "status_text": entscheidung.get("status_text", ""),
        "sportarten": list(ergebnisse),
        "autosleep_summary": entscheidung.get("autosleep_summary"),
        "wetter_hinweis": entscheidung.get("wetter_hinweis", ""),
        "prep": entscheidung.get("prep", ""),
        "_agents": {"medic": medic_result, "wetter": weather_result},
    }
