"""Sportmediziner — beurteilt ausschließlich Körpersignale."""
import logging
from typing import Optional

from ..base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

URTEILE = ["frei", "reduziert", "kein_tempo", "stop"]

SCHEMA = {
    "type": "object",
    "properties": {
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
        "erholung": {
            "type": "string",
            "description": "Ein Satz zu HRV-Trend und WachBPM. Schlafdauer ausdrücklich nicht bewerten.",
        },
    },
    "required": ["sportarten", "alternativen", "erholung"],
    "additionalProperties": False,
}


def build_input(
    *,
    koerper: dict,
    sportarten: list,
    sleep: Optional[dict] = None,
    baseline: Optional[dict] = None,
) -> str:
    """Baut die User-Message aus Fragebogen, geplanten Sportarten und Schlafdaten."""
    lines = ["## Körperwerte heute"]
    for label, key, unit in [
        ("Waden", "waden", "/10"),
        ("Knie", "knie", "/10"),
        ("Achillessehne links", "achilles_l", "/10"),
        ("Achillessehne rechts", "achilles_r", "/10"),
        ("Müdigkeit", "muedigkeit", "/5"),
    ]:
        lines.append(f"- {label}: {koerper.get(key, 0)}{unit}")
    mk = koerper.get("muskelkater") or ["keine"]
    if isinstance(mk, str):
        mk = [mk]
    lines.append(f"- Muskelkater: {', '.join(mk)}")

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
    lines.append("\nBeurteile die Körpersignale und gib pro geplanter Sportart ein Belastungsurteil.")
    return "\n".join(lines)


def run(*, koerper: dict, sportarten: list, sleep=None, baseline=None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("medic"),
        schema=SCHEMA,
        user=build_input(koerper=koerper, sportarten=sportarten, sleep=sleep, baseline=baseline),
        model=model,
        max_tokens=2000,
        label="medic",
    )
