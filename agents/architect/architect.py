"""Workout-Architekt — generischer Fallback für Kraft/Sonstiges.

Läuft nur für MOD-Einheiten. GO-Einheiten übernehmen die Original-Beschreibung
unverändert (deterministisch im Orchestrator), SKIP-Einheiten brauchen keine.

Lauf/Rad/Schwimmen haben eigene Disziplin-Agenten (agents/architect_run,
agents/architect_bike, agents/architect_swim). Dieses Modul bleibt für
Sportarten ohne Spezialisten (Kraft/Sonstiges) bestehen. SCHEMA und
build_input sind Aliase auf agents/base.py, das dieselben Bausteine an alle
vier Module liefert — hier lokal neu zu definieren würde sie vervierfachen.
"""
import logging

from ..base import ARCHITECT_SCHEMA, HAIKU, build_architect_input, call_agent, load_prompt

logger = logging.getLogger(__name__)

# Sportspezifische Zusatz-Prompts (nur Ergänzung, keine Kosten extra — der
# Architekt lief schon vorher nur bei MOD). Kraft/Sonstiges haben keinen
# Spezialisten und bekommen nur den generischen Kern-Prompt.
_SPORT_PROMPT_SCHLUESSEL = {"Laufen": "run", "Rad": "bike", "Schwimmen": "swim"}

SCHEMA = ARCHITECT_SCHEMA
build_input = build_architect_input


def _prompt_fuer_sport(sport: str) -> str:
    kern = load_prompt("architect")
    schluessel = _SPORT_PROMPT_SCHLUESSEL.get(sport)
    if not schluessel:
        return kern
    zusatz = load_prompt(f"architect_{schluessel}")
    return f"{kern}\n\n{zusatz}"


def run(*, athlete: dict, workout: dict, auftrag: dict, wetter_zeile: str = "",
        sport: str = "", model: str = HAIKU) -> dict:
    return call_agent(
        prompt=_prompt_fuer_sport(sport),
        schema=SCHEMA,
        user=build_input(athlete=athlete, workout=workout, auftrag=auftrag,
                         wetter_zeile=wetter_zeile),
        model=model,
        max_tokens=4000,
        label=f"architect[{sport or workout.get('sport', '?')}]",
    )
