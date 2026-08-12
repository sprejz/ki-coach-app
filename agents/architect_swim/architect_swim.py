"""Workout-Architekt — Schwimmen.

Eigener Disziplin-Agent, abgespalten aus dem bisherigen Universal-Architekten
(agents/architect), der Lauf/Rad/Schwimmen bisher mit einem gemeinsamen
Kern-Prompt + laufzeit-verkettetem Zusatz bediente. SCHEMA und build_input
bleiben zentral in agents/base.py (der generische Fallback nutzt dieselben) —
hier ist nur der Prompt wirklich schwimmspezifisch, und der liegt jetzt als
eine zusammenhängende Datei neben dem Code statt als Kern+Zusatz verteilt.
"""
from pathlib import Path

from ..base import ARCHITECT_SCHEMA as SCHEMA
from ..base import HAIKU, build_architect_input as build_input, call_agent, load_prompt

SPORT = "Schwimmen"
_PROMPT_PATH = Path(__file__).parent / "architect_swim.md"


def run(*, athlete: dict, workout: dict, auftrag: dict, wetter_zeile: str = "",
        sport: str = "", model: str = HAIKU) -> dict:
    # `sport` wird hier nicht ausgewertet (dieses Modul ist schon schwimm-
    # spezifisch) — der Parameter existiert nur für eine einheitliche
    # Aufrufsignatur mit dem generischen Fallback (agents/architect), den der
    # Orchestrator per Dispatch austauschbar aufruft.
    return call_agent(
        prompt=load_prompt(SPORT, path=_PROMPT_PATH),
        schema=SCHEMA,
        user=build_input(athlete=athlete, workout=workout, auftrag=auftrag,
                         wetter_zeile=wetter_zeile),
        model=model,
        max_tokens=4000,
        label=f"architect[{SPORT}]",
    )
