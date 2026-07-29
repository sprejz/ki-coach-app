"""Ernährungsberater — ergänzt die deterministische Tabelle um Kontext, den sie
nicht kennt (Hitze/Kälte, chronische Befunde, Renntag).

Erfindet NIEMALS Gramm-/ml-/Stundenzahlen — die Basis kommt unverändert aus
nutrition.py::nutrition_for_duration(). Läuft NICHT bei jedem Check, siehe
Gating in orchestrator._baue_einheit.
"""
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {
            "type": "boolean",
            "description": "true nur, wenn es einen echten Zusatzhinweis gibt. false = nichts zu ergänzen.",
        },
        "hinweis": {
            "type": "string",
            "description": "EIN Satz Zusatzhinweis, qualitativ, OHNE neue Gramm-/ml-/Stundenzahlen. "
                           "Leer wenn relevant=false.",
        },
    },
    "required": ["relevant", "hinweis"],
    "additionalProperties": False,
}


def build_input(*, basis: str, sport: str, dauer_min: Optional[int], badge: str,
                is_hot: bool = False, is_cold: bool = False, temp_max=None,
                chronische_befunde: Optional[str] = None,
                ist_renntag: bool = False, rennname: Optional[str] = None) -> str:
    lines = ["## Ernährungsbasis aus der Tabelle (athlete.json) — feststehend, nicht neu berechnen"]
    lines.append(basis or "(keine Regel für diese Dauer)")
    lines.append(f"\n## Einheit\n- Sportart: {sport or '?'}\n- Dauer: {dauer_min or '?'} min\n- Status: {badge}")

    lines.append("\n## Kontext, den die Tabelle nicht kennt")
    if is_hot:
        lines.append(f"- HITZE: heutiges Temperaturmaximum {temp_max if temp_max is not None else '?'} °C")
    elif is_cold:
        lines.append(f"- KÄLTE: heutiges Temperaturmaximum {temp_max if temp_max is not None else '?'} °C")
    else:
        lines.append("- Temperatur unauffällig")
    lines.append(f"- Chronische Befunde: {chronische_befunde or 'keine bekannt'}")
    if ist_renntag:
        lines.append(f"- HEUTE IST RENNTAG: {rennname or 'A-Rennen'}")

    lines.append(
        "\nPrüfe, ob es einen qualitativen Zusatzhinweis gibt, den die Tabelle oben nicht "
        "abdeckt. Erfinde KEINE neuen Mengen, Zeiten oder Verhältnisse — die stehen bereits "
        "in der Basis. Wenn nichts Sinnvolles zu ergänzen ist, setze relevant=false."
    )
    return "\n".join(lines)


def run(*, basis: str, sport: str = "", dauer_min: Optional[int] = None, badge: str = "GO",
        is_hot: bool = False, is_cold: bool = False, temp_max=None,
        chronische_befunde: Optional[str] = None, ist_renntag: bool = False,
        rennname: Optional[str] = None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("fueling"),
        schema=SCHEMA,
        user=build_input(basis=basis, sport=sport, dauer_min=dauer_min, badge=badge,
                         is_hot=is_hot, is_cold=is_cold, temp_max=temp_max,
                         chronische_befunde=chronische_befunde,
                         ist_renntag=ist_renntag, rennname=rennname),
        model=model,
        max_tokens=600,
        label=f"fueling[{sport or '?'}]",
    )
