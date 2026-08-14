"""Periodisierer — ordnet den heutigen Tag in den Saisonverlauf ein.

Läuft unabhängig von Mediziner und Wetter und damit parallel zu ihnen. Liefert
dem Chefcoach den Rahmen, den er sonst nicht hat: Phase, Rolle des Tages,
Spielraum. Die Kennzahlen selbst kommen deterministisch aus training_load.py.
"""
import logging
from typing import Optional

from ..base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

PHASEN = ["grundlage", "aufbau", "spitze", "taper", "wettkampfwoche", "erholung"]
ROLLEN = ["schluesseleinheit", "unterstuetzung", "erholung", "ruhetag", "wettkampf"]

SCHEMA = {
    "type": "object",
    "properties": {
        "phase": {"type": "string", "enum": PHASEN},
        "wochenintention": {
            "type": "string",
            "description": "Ein Satz: worum geht es in dieser Woche.",
        },
        "heute_rolle": {"type": "string", "enum": ROLLEN},
        "heute_begruendung": {
            "type": "string",
            "description": "Warum diese Rolle — Bezug zur Wochenstruktur.",
        },
        "belastungsurteil": {
            "type": "string",
            "enum": ["zu_wenig", "im_rahmen", "grenzwertig", "ueberlastet"],
        },
        "spielraum": {
            "type": "string",
            "enum": ["ausbauen", "halten", "zuruecknehmen"],
            "description": "Wie viel Luft der Chefcoach heute hat.",
        },
        "hinweis": {
            "type": "string",
            "description": "Was der Chefcoach über den Block wissen muss, mit Zahlen.",
        },
        "warnung": {
            "type": "string",
            "description": "Nur bei strukturellem Problem, mit der auslösenden Zahl. Sonst leer.",
        },
    },
    "required": ["phase", "wochenintention", "heute_rolle", "heute_begruendung",
                 "belastungsurteil", "spielraum", "hinweis", "warnung"],
    "additionalProperties": False,
}


def build_input(*, load: dict, woche: list, a_race: Optional[dict],
                naechste_rennen: Optional[list] = None, tage_bis_a: Optional[int] = None) -> str:
    lines = ["## Belastungskennzahlen (Stand heute, vor der heutigen Einheit)"]
    lines.append(f"- CTL (Fitness, 42d): {load.get('ctl', '?')}")
    lines.append(f"- ATL (Ermüdung, 7d): {load.get('atl', '?')}")
    lines.append(f"- TSB (Frische): {load.get('tsb', '?')}")
    lines.append(f"- Ramp Rate (CTL-Zuwachs letzte 7 Tage): {load.get('ramp_7d', '?')}")
    lines.append(f"- CTL vor 28 Tagen: {load.get('ctl_vor_28d', '?')}")
    lines.append(f"- TSS letzte 7 Tage: {load.get('tss_7d', '?')}")
    lines.append(f"- TSS letzte 28 Tage: {load.get('tss_28d', '?')}")
    lines.append(f"- Tage mit Trainingsdaten im Zeitraum: {load.get('tage_mit_daten', 0)}")

    verlauf = load.get("verlauf") or []
    if verlauf:
        lines.append("\n## Letzte 14 Tage")
        lines.append("Datum | TSS | CTL | ATL | TSB")
        for v in verlauf:
            lines.append(f"{v['datum']} | {v['tss']:.0f} | {v['ctl']} | {v['atl']} | {v['tsb']}")

    # Titel statt bloßer TSS-Zahlen: ein Wettkampf, ein Test und ein zäher
    # Grundlagentag können dieselbe Tagessumme haben und bedeuten für die
    # Erholung etwas völlig anderes.
    absolviert = load.get("letzte_einheiten") or []
    if any(t.get("einheiten") for t in absolviert):
        lines.append("\n## Tatsächlich absolviert (letzte Tage)")
        for t in absolviert:
            if not t["einheiten"]:
                lines.append(f"- {t['datum']}: Ruhetag (0 TSS)")
                continue
            teile = ", ".join(
                f"{e['sport']} „{e['titel']}“"
                + (f" {e['dauer_min']}min" if e.get("dauer_min") else "")
                + (f" {e['distanz_km']:.1f}km" if e.get("distanz_km") else "")
                + (f" {e['tss']}TSS" if e.get("tss") else "")
                for e in t["einheiten"]
            )
            lines.append(f"- {t['datum']}: {teile} (Σ {t['tss_summe']} TSS)")

    lines.append("\n## Kommende 7 Tage (Plan aus TrainingPeaks)")
    for tag in woche or []:
        marke = " ← HEUTE" if tag.get("ist_heute") else ""
        if tag["einheiten"]:
            teile = ", ".join(
                f"{e['sport']} {e['titel']}"
                + (f" {e['dauer_min']}min" if e.get("dauer_min") else "")
                + (f" {e['tss']}TSS" if e.get("tss") else "")
                for e in tag["einheiten"]
            )
            lines.append(f"- {tag['wochentag']} {tag['datum']}: {teile} (Σ {tag['tss_summe']:.0f} TSS){marke}")
        else:
            lines.append(f"- {tag['wochentag']} {tag['datum']}: nichts geplant{marke}")

    lines.append("\n## Rennkalender")
    letztes = load.get("letztes_rennen")
    if letztes:
        lines.append(
            f"- **Letztes Rennen: {letztes.get('name')} ({letztes.get('priority')}) "
            f"am {letztes.get('date')}, vor {letztes.get('tage_her')} Tagen** — "
            "Erholungsbedarf danach berücksichtigen."
        )
    if a_race:
        lines.append(
            f"- A-Rennen: {a_race.get('name')} am {a_race.get('date')}"
            + (f", noch {tage_bis_a} Tage" if tage_bis_a is not None else "")
            + (f", Zielzeit {a_race['goal_total']} h" if a_race.get("goal_total") else "")
        )
    else:
        lines.append("- Kein A-Rennen eingetragen.")
    for r in naechste_rennen or []:
        if a_race and r.get("name") == a_race.get("name"):
            continue
        lines.append(f"- {r.get('priority', '?')}-Rennen: {r.get('name')} am {r.get('date')}")

    lines.append("\nOrdne den heutigen Tag in den Saisonverlauf ein.")
    return "\n".join(lines)


def run(*, load: dict, woche: list, a_race=None, naechste_rennen=None,
        tage_bis_a=None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("periodizer"),
        schema=SCHEMA,
        user=build_input(load=load, woche=woche, a_race=a_race,
                         naechste_rennen=naechste_rennen, tage_bis_a=tage_bis_a),
        model=model,
        max_tokens=2000,
        label="periodizer",
    )
