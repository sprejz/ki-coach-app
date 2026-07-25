"""Orchestrator für den Coach-Ablauf.

Der Kontrollfluss liegt hier, nicht bei den Agents — die Agents reden nicht
miteinander, sie liefern typisierte Urteile an den Orchestrator zurück.

    Mediziner ┐
              ├─(parallel)─→ Chefcoach ─→ Ergebnis
    Wetter    ┘

Deterministische Logik (Schlaf-Flags, Baseline, Ernährungstabelle, Wetterschwellen)
bleibt bewusst in Code — sie ist exakt, kostenlos und auditierbar.
"""
import asyncio
import logging
from typing import Optional

from agents import head_coach, medic, weather
from agents.base import HAIKU

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
    """Führt den kompletten Check aus und liefert das Chefcoach-Ergebnis.

    Das Ergebnis entspricht dem Vertrag, den das Frontend bereits liest — der
    Aufrufer hängt nur noch `weather` und ggf. `sleep_flags` an.
    """
    tp_workouts = tp_workouts or []

    sportarten = list(dict.fromkeys(
        normalize_sport(w.get("sport", "")) for w in tp_workouts
    )) or [normalize_sport(s) for s in koerper.get("geplante_einheiten", [])]
    sportarten = [s for s in dict.fromkeys(sportarten) if s]
    titel = [w.get("title", "") for w in tp_workouts if w.get("title")]

    # Stufe 1: die beiden Spezialisten sind unabhängig voneinander → parallel.
    # asyncio.to_thread, weil das anthropic-SDK hier synchron aufgerufen wird.
    medic_task = asyncio.to_thread(
        medic.run, koerper=koerper, sportarten=sportarten,
        sleep=sleep, baseline=baseline, model=model,
    )
    weather_task = asyncio.to_thread(
        weather.run, weather=weather_data, sportarten=sportarten, titel=titel,
        swim_min_c=athlete.get("swim_outdoor_min_celsius", 15),
        wasser_temp=wasser_temp, tag=tag, model=model,
    )
    medic_result, weather_result = await asyncio.gather(medic_task, weather_task)
    logger.info(
        "orchestrator: medic=%s wetter=%s sportarten=%s",
        medic_result.get("gesamturteil"), weather_result.get("gesamtlage"), sportarten,
    )

    # Stufe 2: der Chefcoach synthetisiert und entscheidet.
    result = await asyncio.to_thread(
        head_coach.run,
        athlete=athlete, a_race=a_race, medic=medic_result, wetter=weather_result,
        tp_workouts=tp_workouts, tag=tag, model=model,
    )

    # Urteile mitgeben — für Debugging und als Grundlage der späteren Anzeige.
    result["_agents"] = {"medic": medic_result, "wetter": weather_result}
    return result
