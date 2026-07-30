"""Workout-Architekt — formuliert eine beschlossene Einheit für TrainingPeaks aus.

Läuft nur für MOD-Einheiten. GO-Einheiten übernehmen die Original-Beschreibung
unverändert (deterministisch im Orchestrator), SKIP-Einheiten brauchen keine.
"""
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

# Sportspezifische Zusatz-Prompts (nur Ergänzung, keine Kosten extra — der
# Architekt lief schon vorher nur bei MOD). Kraft/Sonstiges haben keinen
# Spezialisten und bekommen nur den generischen Kern-Prompt.
_SPORT_PROMPT_SCHLUESSEL = {"Laufen": "run", "Rad": "bike", "Schwimmen": "swim"}


def _prompt_fuer_sport(sport: str) -> str:
    kern = load_prompt("architect")
    schluessel = _SPORT_PROMPT_SCHLUESSEL.get(sport)
    if not schluessel:
        return kern
    zusatz = load_prompt(f"architect_{schluessel}")
    return f"{kern}\n\n{zusatz}"

# Identisch zur Struktur, die tp_create_workout erwartet. Bewusst nicht rekursiv:
# ein Wiederholungsblock enthält nur Einzelschritte.
_STEP = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "duration_seconds": {"type": "integer"},
        "intensity_min": {"type": "integer", "description": "Prozent der Schwelle"},
        "intensity_max": {"type": "integer", "description": "Prozent der Schwelle"},
        "intensityClass": {"type": "string", "enum": ["warmUp", "active", "rest", "coolDown"]},
    },
    "required": ["name", "duration_seconds", "intensity_min", "intensity_max", "intensityClass"],
    "additionalProperties": False,
}

_REPETITION = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "repetition"},
        "reps": {"type": "integer"},
        "steps": {"type": "array", "items": _STEP},
    },
    "required": ["type", "reps", "steps"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "beschreibung": {
            "type": "string",
            "description": "Der vollständige Text für das TrainingPeaks-Beschreibungsfeld.",
        },
        "dauer_min": {
            "type": "integer",
            "description": "Tatsächliche Dauer der ausformulierten Einheit, mindestens 20.",
        },
        "tp_struktur": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "array", "items": {"anyOf": [_STEP, _REPETITION]}},
                        "primaryIntensityMetric": {
                            "type": "string",
                            "enum": ["percentOfFtp", "percentOfThresholdPace"],
                        },
                    },
                    "required": ["steps", "primaryIntensityMetric"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ],
            "description": "Nur bei echten Intervallblöcken, sonst null.",
        },
        "distanz_m": {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
            "description": "Gesamtdistanz in Metern, nur bei Schwimmeinheiten.",
        },
    },
    "required": ["beschreibung", "dauer_min", "tp_struktur", "distanz_m"],
    "additionalProperties": False,
}


def build_input(*, athlete: dict, workout: dict, auftrag: dict, wetter_zeile: str = "") -> str:
    lines = ["## Auftrag des Chefcoachs"]
    lines.append(f"- Grund der Anpassung: {auftrag.get('begruendung', '—')}")
    a = auftrag.get("anpassung", {})
    if a.get("dauer_min"):
        lines.append(f"- Zieldauer: {a['dauer_min']} min")
    if a.get("zone"):
        lines.append(f"- Zielzone/Intensität: {a['zone']}")
    if a.get("kein_tempo"):
        lines.append("- Kein Tempo: keine Intervalle, keine Schwellenarbeit")
    if a.get("indoor"):
        lines.append("- Nach Indoor verlegen (Zwift/Laufband/Hallenbad)")
    if a.get("sportwechsel"):
        lines.append(f"- Sportart wechseln zu: {a['sportwechsel']}")
    if a.get("hinweis"):
        lines.append(f"- Zusatz: {a['hinweis']}")

    lines.append("\n## Ursprüngliche Einheit aus TrainingPeaks")
    lines.append(f"- Sportart: {workout.get('sport', '?')}")
    lines.append(f"- Titel: {workout.get('title', '')}")
    if workout.get("duration_min"):
        lines.append(f"- Geplante Dauer: {workout['duration_min']} min")
    if workout.get("tss"):
        lines.append(f"- Geplanter TSS: {workout['tss']}")
    desc = (workout.get("description") or "").strip()
    if desc:
        lines.append("- Original-Beschreibung (das ist deine Vorlage):")
        lines.append(f"```\n{desc}\n```")
    else:
        lines.append("- Original-Beschreibung: LEER — du baust eine vollständige Struktur.")

    lines.append("\n## Schwellenwerte des Athleten")
    lines.append(f"- FTP Rad: {athlete.get('ftp_watt', '?')} W")
    lines.append(f"- Laufschwelle: {athlete.get('run_threshold_pace', '?')} /km")
    lines.append(f"- CSS Schwimmen: {athlete.get('css_per_100m', '?')} /100m")
    lines.append(f"- Schwellen-HF Rad: {athlete.get('threshold_hr_bike', '?')} bpm")

    if wetter_zeile:
        lines.append(f"\n## Wetter\n{wetter_zeile}")

    lines.append("\nFormuliere diese eine Einheit aus.")
    return "\n".join(lines)


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
