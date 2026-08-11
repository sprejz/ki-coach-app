"""Chefcoach — trifft die Trainingsentscheidung aus den Spezialisten-Urteilen.

Seit Stufe 3 formuliert der Chefcoach die Einheiten nicht mehr aus. Er
entscheidet (GO/MOD/SKIP) und übergibt bei MOD einen strukturierten Auftrag an
den Workout-Architekten. Den Vertrag fürs Frontend baut der Orchestrator
daraus zusammen.
"""
import json
import logging
from typing import Optional

from ..base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

_ANPASSUNG = {
    "type": "object",
    "description": "Was am Workout geändert werden soll. Nur bei MOD gefüllt, sonst überall null/false.",
    "properties": {
        "dauer_min": {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
            "description": "Zieldauer in Minuten, oder null wenn unverändert.",
        },
        "zone": {"type": "string", "description": "Zielzone/Intensität, z.B. 'Z1–Z2'. Leer wenn unverändert."},
        "kein_tempo": {"type": "boolean", "description": "Keine Intervalle, keine Schwellenarbeit."},
        "indoor": {"type": "boolean", "description": "Nach drinnen verlegen."},
        "sportwechsel": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Andere Sportart, z.B. 'Aquajogging'. Null wenn keine.",
        },
        "hinweis": {"type": "string", "description": "Zusatzauflage für den Architekten. Leer wenn keine."},
    },
    "required": ["dauer_min", "zone", "kein_tempo", "indoor", "sportwechsel", "hinweis"],
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
                    "begruendung": {
                        "type": "string",
                        "description": "Warum diese Entscheidung, mit konkretem Wert. Bei GO kurz oder leer.",
                    },
                    "anpassung": _ANPASSUNG,
                },
                "required": ["sport", "badge", "details", "begruendung", "anpassung"],
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
    # Ernährungsregeln bewusst nicht mitgeliefert — die werden nach der
    # fertigen Dauer deterministisch aus athlete.json berechnet.
    return "\n".join(lines)


def build_input(*, athlete: dict, a_race, medic: dict, wetter: dict, allgemein: dict,
                tp_workouts: list, tag: str, block: Optional[dict] = None) -> str:
    lines = [f"# Entscheidung für {tag}", "", _athlete_block(athlete, a_race)]

    lines.append("\n## Urteil des Allgemeinmediziners (bindend, stärker als der Sportmediziner)")
    lines.append(f"- Gesamtlage: {allgemein.get('gesamturteil')}")
    if allgemein.get("leitbefund"):
        lines.append(f"- Leitbefund: {allgemein['leitbefund']}")
    for s in allgemein.get("sportarten", []):
        lines.append(f"- {s.get('sport')}: **{s.get('urteil')}** — {s.get('grund')}")
    if allgemein.get("alternativen"):
        lines.append(f"- Alternativen: {', '.join(allgemein['alternativen'])}")
    if allgemein.get("hinweis_chronisch"):
        lines.append(f"- Chronischer Kontext: {allgemein['hinweis_chronisch']}")

    if block:
        lines.append("\n## Urteil des Periodisierers")
        lines.append(f"- Phase: {block.get('phase')}")
        lines.append(f"- Woche: {block.get('wochenintention')}")
        lines.append(f"- Rolle heute: **{block.get('heute_rolle')}** — {block.get('heute_begruendung')}")
        lines.append(f"- Belastung: {block.get('belastungsurteil')}")
        lines.append(f"- Spielraum: **{block.get('spielraum')}**")
        if block.get("hinweis"):
            lines.append(f"- Hinweis: {block['hinweis']}")
        if block.get("warnung"):
            lines.append(f"- ⚠️ WARNUNG: {block['warnung']}")

    lines.append("\n## Urteil des Sportmediziners")
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


def run(*, athlete: dict, a_race, medic: dict, wetter: dict, allgemein: dict, tp_workouts: list,
        tag: str, block: Optional[dict] = None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("head_coach"),
        schema=SCHEMA,
        user=build_input(athlete=athlete, a_race=a_race, medic=medic, wetter=wetter,
                         allgemein=allgemein, tp_workouts=tp_workouts, tag=tag, block=block),
        model=model,
        max_tokens=8000,
        label="head_coach",
    )
