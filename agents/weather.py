"""Wetter-Taktiker — übersetzt die Wetterlage in Konsequenzen pro Sportart."""
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

EMPFEHLUNGEN = ["outdoor_ok", "zeitfenster", "indoor_wechsel", "gestrichen"]

SCHEMA = {
    "type": "object",
    "properties": {
        "gesamtlage": {
            "type": "string",
            "enum": ["unkritisch", "anpassen", "outdoor_gestrichen"],
        },
        "hinweis": {
            "type": "string",
            "description": "Ein Satz Wetterlage mit konkreten Zahlen, für die App-Anzeige.",
        },
        "sportarten": {
            "type": "array",
            "description": "Ein Eintrag pro geplanter Sportart.",
            "items": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string", "enum": ["Schwimmen", "Rad", "Laufen", "Kraft", "Sonstiges"]},
                    "empfehlung": {"type": "string", "enum": EMPFEHLUNGEN},
                    "anpassung": {
                        "type": "string",
                        "description": "Konkrete Maßnahme mit Zahlen. Leer wenn keine nötig.",
                    },
                    "zeitfenster": {
                        "type": "string",
                        "description": "Empfohlene Uhrzeit, z.B. 'vor 09:00'. Leer wenn egal.",
                    },
                },
                "required": ["sport", "empfehlung", "anpassung", "zeitfenster"],
                "additionalProperties": False,
            },
        },
        "versorgung": {
            "type": "string",
            "description": "Flüssigkeit/Salz nur wenn Hitze relevant ist, sonst leer.",
        },
    },
    "required": ["gesamtlage", "hinweis", "sportarten", "versorgung"],
    "additionalProperties": False,
}


def build_input(*, weather: dict, sportarten: list, titel: Optional[list] = None,
                swim_min_c: int = 15, wasser_temp=None, tag: str = "morgen") -> str:
    lines = [f"## Wetter {tag} in Ludwigsfelde"]
    lines.append(f"- Lage: {weather.get('description', '?')}")
    lines.append(f"- Temperatur: {weather.get('temp_min', '?')} bis {weather.get('temp_max', '?')} °C")
    lines.append(f"- Regenwahrscheinlichkeit (Tagesmaximum): {weather.get('rain_prob', 0)} %")
    if weather.get("is_thunderstorm"):
        lines.append("- GEWITTER gemeldet")
    if weather.get("is_hot"):
        lines.append("- Als Hitzetag markiert (über 28 °C)")
    if weather.get("is_cold"):
        lines.append("- Als Frosttag markiert (unter 0 °C)")

    hourly = weather.get("hourly") or []
    if hourly:
        lines.append("\n## Stundenverlauf 6–20 Uhr")
        lines.append("Uhrzeit | Temp | Regen")
        for h in hourly:
            lines.append(f"{h.get('hour'):>2}:00 | {h.get('temp')} °C | {h.get('rain')} %")

    lines.append(f"\n## Geplante Sportarten\n{', '.join(sportarten) if sportarten else 'keine bekannt'}")
    if titel:
        lines.append("Geplante Workout-Titel (zeigen ob schon Indoor geplant ist):")
        for t in titel:
            lines.append(f"- {t}")

    lines.append(f"\n## Athletenvorgaben\n- Freibad erst ab {swim_min_c} °C Wassertemperatur")
    if wasser_temp:
        lines.append(f"- Gemeldete Wassertemperatur: {wasser_temp} °C")

    lines.append("\nGib pro geplanter Sportart die taktische Wetterempfehlung.")
    return "\n".join(lines)


def run(*, weather: dict, sportarten: list, titel=None, swim_min_c: int = 15,
        wasser_temp=None, tag: str = "morgen", model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("weather"),
        schema=SCHEMA,
        user=build_input(weather=weather, sportarten=sportarten, titel=titel,
                         swim_min_c=swim_min_c, wasser_temp=wasser_temp, tag=tag),
        model=model,
        max_tokens=2000,
        label="weather",
    )
