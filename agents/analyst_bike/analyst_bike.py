"""Performance-Analyst — Rad.

Eigener Disziplin-Agent, analog zu agents/architect_bike: derselbe Coach, der
Radeinheiten anpasst (Coach Nils Brandt, siehe translations.py → T["agenten"]),
bewertet sie im Analyse-Tab jetzt auch. Bisher lief für jede Sportart derselbe
generische Performance-Analyst (agents/analyst) — ein Radcoach liest
kardiales Drift und NP/Ø-Leistung anders als ein Lauf- oder Schwimmspezialist.

SCHEMA und build_input bleiben zentral in agents/analyst/analyst.py (der
generische Fallback für Kraft/Sonstiges/Golf nutzt dieselben Objekte) — hier
ist nur der Prompt radspezifisch.
"""
from pathlib import Path

from ..analyst.analyst import SCHEMA, build_input
from ..base import HAIKU, call_agent, load_prompt

SPORT = "Rad"
_PROMPT_PATH = Path(__file__).parent / "analyst_bike.md"


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
