"""Performance-Analyst — Schwimmen.

Eigener Disziplin-Agent, analog zu agents/architect_swim: derselbe Coach, der
Schwimmeinheiten anpasst (Coach Pia König, siehe translations.py → T["agenten"]),
bewertet sie im Analyse-Tab. Es gibt (anders als beim Architekten) keinen
generischen Kraft/Sonstiges-Fallback für die Analyse — der Analyse-Tab zeigt
im Frontend ohnehin nur Lauf-/Rad-/Schwimmeinheiten zur Auswahl.

SCHEMA und build_input bleiben zentral in agents/base.py (alle drei
Disziplin-Agenten nutzen dieselben Objekte) — hier ist nur der Prompt
schwimmspezifisch.
"""
from pathlib import Path

from ..base import ANALYST_SCHEMA as SCHEMA
from ..base import HAIKU, build_analyst_input as build_input, call_agent, load_prompt

SPORT = "Schwimmen"
_PROMPT_PATH = Path(__file__).parent / "analyst_swim.md"


def run(*, athlete: dict, a_race=None, sport: str = "", titel: str = "", datum: str = "",
        fit=None, tp=None, wetter=None, load=None, ernaehrung_basis=None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt(SPORT, path=_PROMPT_PATH),
        schema=SCHEMA,
        user=build_input(athlete=athlete, a_race=a_race, sport=sport, titel=titel,
                         datum=datum, fit=fit, tp=tp, wetter=wetter, load=load,
                         ernaehrung_basis=ernaehrung_basis),
        model=model,
        max_tokens=2000,
        label=f"analyst[{SPORT}]",
    )
