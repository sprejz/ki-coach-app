"""Chefcoach — trifft die Trainingsentscheidung aus den Spezialisten-Urteilen.

Das Ausgabeschema spiegelt exakt den Vertrag, den templates/index.html liest
(status, status_text, sportarten[].{sport,badge,details,beschreibung,ernaehrung},
autosleep_summary, wetter_hinweis, prep) plus die Felder, die applyToTP an
/api/tp/apply weitergibt (tp_struktur, distanz_m).
"""
import json
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

# tp_struktur: bewusst nicht rekursiv aufgebaut (Structured Outputs unterstützen
# keine rekursiven Schemas). Ein Wiederholungsblock enthält nur Einzelschritte.
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

_TP_STRUKTUR = {
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
}

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["green", "orange", "red"]},
        "status_text": {"type": "string", "description": "Kurzer Status, z.B. 'Alles grün' oder 'Angepasst'."},
        "sportarten": {
            "type": "array",
            "description": "Ein Eintrag pro geplanter Einheit, in derselben Reihenfolge wie im Input.",
            "items": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string"},
                    "badge": {"type": "string", "enum": ["GO", "MOD", "SKIP"]},
                    "details": {"type": "string", "description": "1–2 Sätze Coach-Hinweis für die App."},
                    "beschreibung": {"type": "string", "description": "Text für das TrainingPeaks-Beschreibungsfeld."},
                    "ernaehrung": {"type": "string"},
                    "tp_struktur": {
                        "anyOf": [_TP_STRUKTUR, {"type": "null"}],
                        "description": "Nur bei MOD mit echten Intervallblöcken, sonst null.",
                    },
                    "distanz_m": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Gesamtdistanz in Metern, nur bei Schwimm-MOD, sonst null.",
                    },
                },
                "required": ["sport", "badge", "details", "beschreibung", "ernaehrung",
                             "tp_struktur", "distanz_m"],
                "additionalProperties": False,
            },
        },
        "autosleep_summary": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Ein Satz zu den Schlafmarkern, oder null wenn keine CSV vorlag.",
        },
        "wetter_hinweis": {"type": "string"},
        "prep": {"type": "string", "description": "Ein Satz Vorbereitung für den Abend vorher."},
    },
    "required": ["status", "status_text", "sportarten", "autosleep_summary",
                 "wetter_hinweis", "prep"],
    "additionalProperties": False,
}


def _athlete_block(athlete: dict, a_race: Optional[dict]) -> str:
    lines = ["## Athlet"]
    lines.append(f"- {athlete.get('name', 'Athlet')}, {athlete.get('weight_kg', '?')} kg")
    lines.append(f"- FTP Rad: {athlete.get('ftp_watt', '?')} W")
    lines.append(f"- Laufschwelle: {athlete.get('run_threshold_pace', '?')} /km")
    lines.append(f"- CSS Schwimmen: {athlete.get('css_per_100m', '?')} /100m")
    if a_race:
        lines.append(
            f"- A-Rennen: {a_race.get('name')} am {a_race.get('date')}, "
            f"Zielzeit {a_race.get('goal_total', '?')} h"
        )
    n = athlete.get("nutrition", {})
    if n.get("rules"):
        lines.append("\n## Ernährungsregeln des Athleten (nach Dauer)")
        for r in n["rules"]:
            lo = r.get("duration_min_min", 0)
            hi = r.get("duration_max_min")
            spanne = f"{lo}–{hi} min" if hi else f"ab {lo} min"
            teile = [f"vorher: {r['before']}" if r.get("before") else "",
                     f"während: {r['during']}" if r.get("during") else "",
                     f"nachher: {r['after']}" if r.get("after") else ""]
            lines.append(f"- {spanne} — " + " | ".join(t for t in teile if t))
        lines.append(
            f"- Gemisch: {n.get('mix', '?')}, {n.get('carbs_per_hour_g', 90)} g Carbs/h, "
            f"{n.get('fluid_per_hour_ml', 600)} ml/h (Hitze: {n.get('fluid_heat_per_hour_ml', 750)} ml/h, "
            f"{n.get('salt_heat_per_hour', 2)} Saltstick/h)"
        )
    return "\n".join(lines)


def build_input(*, athlete: dict, a_race, medic: dict, wetter: dict,
                tp_workouts: list, tag: str) -> str:
    lines = [f"# Entscheidung für {tag}", "", _athlete_block(athlete, a_race)]

    lines.append("\n## Urteil des Sportmediziners")
    lines.append(f"- Gesamtlage: {medic.get('gesamturteil')}")
    if medic.get("leitsymptom"):
        lines.append(f"- Leitsymptom: {medic['leitsymptom']}")
    for s in medic.get("sportarten", []):
        lines.append(f"- {s.get('sport')}: **{s.get('urteil')}** — {s.get('grund')}")
    if medic.get("alternativen"):
        lines.append(f"- Alternativen: {', '.join(medic['alternativen'])}")
    if medic.get("erholung"):
        lines.append(f"- Erholung: {medic['erholung']}")

    lines.append("\n## Urteil des Wetter-Taktikers")
    lines.append(f"- Gesamtlage: {wetter.get('gesamtlage')}")
    lines.append(f"- Hinweis: {wetter.get('hinweis')}")
    for s in wetter.get("sportarten", []):
        zusatz = " ".join(x for x in [s.get("anpassung", ""), s.get("zeitfenster", "")] if x)
        lines.append(f"- {s.get('sport')}: **{s.get('empfehlung')}** — {zusatz or 'keine Anpassung'}")
    if wetter.get("versorgung"):
        lines.append(f"- Versorgung: {wetter['versorgung']}")

    lines.append("\n## Geplante Einheiten aus TrainingPeaks")
    if tp_workouts:
        for i, w in enumerate(tp_workouts, 1):
            lines.append(f"\n### Einheit {i}: {w.get('sport', '?')} — {w.get('title', '')}")
            if w.get("duration_min"):
                lines.append(f"- Geplante Dauer: {w['duration_min']} min")
            if w.get("tss"):
                lines.append(f"- Geplanter TSS: {w['tss']}")
            if w.get("start_time"):
                lines.append(f"- Geplante Startzeit: {w['start_time']}")
            desc = (w.get("description") or "").strip()
            lines.append("- Original-Beschreibung:")
            lines.append(f"```\n{desc}\n```" if desc else "  (leer — du musst eine Struktur bauen)")
    else:
        lines.append("Keine TrainingPeaks-Einheiten bekannt. Entscheide anhand der Sportarten allein.")

    lines.append(
        "\nEntscheide pro Einheit GO, MOD oder SKIP. Gib die Einheiten in derselben "
        "Reihenfolge zurück, in der sie oben stehen."
    )
    return "\n".join(lines)


def run(*, athlete: dict, a_race, medic: dict, wetter: dict, tp_workouts: list,
        tag: str, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("head_coach"),
        schema=SCHEMA,
        user=build_input(athlete=athlete, a_race=a_race, medic=medic, wetter=wetter,
                         tp_workouts=tp_workouts, tag=tag),
        model=model,
        max_tokens=8000,
        label="head_coach",
    )
