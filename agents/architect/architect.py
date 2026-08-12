"""Workout-Architekt — generischer Fallback für Kraft/Sonstiges.

Läuft nur für MOD-Einheiten. GO-Einheiten übernehmen die Original-Beschreibung
unverändert (deterministisch im Orchestrator), SKIP-Einheiten brauchen keine.

Lauf/Rad/Schwimmen haben eigene Disziplin-Agenten (agents/architect_run,
agents/architect_bike, agents/architect_swim), die der Orchestrator per
_ARCHITECT_BY_SPORT direkt anspricht — dieses Modul bekommt sie nie zu
Gesicht. Es bleibt für Sportarten ohne Spezialisten (Kraft/Sonstiges)
bestehen. SCHEMA und build_input sind Aliase auf agents/base.py, das
dieselben Bausteine an alle vier Module liefert — hier lokal neu zu
definieren würde sie vervierfachen.
"""
import logging
from pathlib import Path

from ..base import ARCHITECT_SCHEMA, HAIKU, build_architect_input, call_agent, load_prompt

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "architect.md"

SCHEMA = ARCHITECT_SCHEMA
build_input = build_architect_input


def run(*, athlete: dict, workout: dict, auftrag: dict, wetter_zeile: str = "",
        sport: str = "", model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("architect", path=_PROMPT_PATH),
        schema=SCHEMA,
        user=build_input(athlete=athlete, workout=workout, auftrag=auftrag,
                         wetter_zeile=wetter_zeile),
        model=model,
        max_tokens=4000,
        label=f"architect[{sport or workout.get('sport', '?')}]",
    )
