"""Allgemeinmediziner — beurteilt Krankheit und Ganzkörper-Befunde, überschreibt alles."""
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

URTEILE = ["frei", "reduziert", "kein_tempo", "stop"]

SCHEMA = {
    "type": "object",
    "properties": {
        "gesamturteil": {
            "type": "string",
            "enum": ["frei", "eingeschraenkt", "pause"],
            "description": "Gesamtlage aus Sicht des Allgemeinmediziners. 'pause' ist bindend für ALLE Sportarten.",
        },
        "leitbefund": {
            "type": "string",
            "description": "Auffälligster Befund mit Wert, z.B. 'Fieber 38.6°C' oder 'Symptome neu schwer'. Leer wenn unauffällig.",
        },
        "sportarten": {
            "type": "array",
            "description": "Ein Eintrag pro relevanter Sportart.",
            "items": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string", "enum": ["Schwimmen", "Rad", "Laufen", "Kraft", "Sonstiges"]},
                    "urteil": {"type": "string", "enum": URTEILE},
                    "grund": {"type": "string", "description": "Medizinische Begründung mit konkretem Wert."},
                },
                "required": ["sport", "urteil", "grund"],
                "additionalProperties": False,
            },
        },
        "alternativen": {
            "type": "array",
            "description": "Ausweich-Sportarten bei Einschränkung, z.B. 'Aquajogging'. Leer wenn nichts eingeschränkt ist.",
            "items": {"type": "string"},
        },
        "hinweis_chronisch": {
            "type": "string",
            "description": "Ein Satz, wie chronische Befunde die heutige Einschätzung beeinflusst haben. "
                           "Leer, wenn keine hinterlegt sind oder ohne Einfluss.",
        },
    },
    "required": ["gesamturteil", "leitbefund", "sportarten", "alternativen", "hinweis_chronisch"],
    "additionalProperties": False,
}


def build_input(
    *,
    koerper: dict,
    sportarten: list,
    chronische_befunde: Optional[str] = None,
    sleep: Optional[dict] = None,
    baseline: Optional[dict] = None,
) -> str:
    """Baut die User-Message aus Krankheits-/Ganzkörpersignalen, Profil-Kontext und Schlafdaten."""
    lines = ["## Krankheits- und Ganzkörper-Signale heute"]
    lines.append(f"- Symptome: {koerper.get('symptome', 'keine')}")

    fieber = koerper.get("fieber")
    lines.append(f"- Fieber: {fieber}°C" if fieber not in (None, "") else "- Fieber: nicht gemessen")

    sys_, dia = koerper.get("blutdruck_sys"), koerper.get("blutdruck_dia")
    if sys_ not in (None, "") and dia not in (None, ""):
        lines.append(f"- Blutdruck: {sys_}/{dia} mmHg")
    else:
        lines.append("- Blutdruck: nicht gemessen")

    medikamente = koerper.get("medikamente")
    lines.append(f"- Medikamente: {medikamente}" if medikamente else "- Medikamente: keine")

    lines.append(
        f"\n## Chronische Befunde (Athletenprofil, gilt dauerhaft)\n{chronische_befunde or 'keine bekannt'}"
    )

    if sleep:
        lines.append("\n## AutoSleep letzte Nacht")
        for label, key, unit in [
            ("SchlafHRV", "hrv", "ms"),
            ("WachBPM", "wach_bpm", ""),
            ("SchlafBPM", "schlaf_bpm", ""),
            ("Atmung", "atmung", "/min"),
            ("Effizienz", "effizienz", "%"),
        ]:
            v = sleep.get(key)
            if v is not None:
                lines.append(f"- {label}: {v}{unit}")
        flags = sleep.get("flags") or []
        lines.append(f"- Auffällige Marker: {', '.join(flags) if flags else 'keine'}")

    if baseline:
        lines.append("\n## Baseline des Athleten (Median / Flag-Grenze)")
        for key, label in [
            ("SchlafHRV", "SchlafHRV"), ("WachBPM", "WachBPM"),
            ("SchlafBPM", "SchlafBPM"), ("Atmung", "Atmung"), ("Effizienz", "Effizienz"),
        ]:
            b = baseline.get(key) or {}
            grenze = b.get("flag_low", b.get("flag_high"))
            lines.append(f"- {label}: Median {b.get('median', '?')} / Flag {grenze}")

    lines.append(f"\n## Geplante Sportarten\n{', '.join(sportarten) if sportarten else 'keine bekannt'}")
    lines.append("\nBeurteile die Krankheits-/Ganzkörperlage und gib pro geplanter Sportart ein Belastungsurteil.")
    return "\n".join(lines)


def run(
    *,
    koerper: dict,
    sportarten: list,
    chronische_befunde: Optional[str] = None,
    sleep=None,
    baseline=None,
    model: str = HAIKU,
) -> dict:
    return call_agent(
        prompt=load_prompt("allgemeinmedic"),
        schema=SCHEMA,
        user=build_input(
            koerper=koerper, sportarten=sportarten,
            chronische_befunde=chronische_befunde, sleep=sleep, baseline=baseline,
        ),
        model=model,
        max_tokens=2000,
        label="allgemeinmedic",
    )
