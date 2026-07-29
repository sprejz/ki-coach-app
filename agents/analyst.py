"""Performance-Analyst — bewertet eine absolvierte Einheit.

Ersetzt den freien JSON-Pfad aus _run_analysis_job_fast. Dort führte ein
Parse-Fehler stillschweigend zu {"bewertung": "ok", "urteil": <Rohtext>} — der
Athlet sah ein Urteil, das nie eines war. Mit erzwungenem Schema unmöglich.
"""
import logging
from typing import Optional

from .base import HAIKU, call_agent, load_prompt

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "bewertung": {"type": "string", "enum": ["gut", "ok", "verbesserungsbedarf"]},
        "urteil": {
            "type": "string",
            "description": "3–4 Sätze mit konkreten Zahlen, verglichen mit den Schwellenwerten.",
        },
        "naechster_schritt": {
            "type": "string",
            "description": "Ein umsetzbarer Hinweis für die nächsten 1–2 Tage.",
        },
        "datenlage": {
            "type": "string",
            "enum": ["fit", "tp_ist", "nur_plan"],
            "description": "Worauf die Bewertung beruht.",
        },
        "ernaehrung_einschaetzung": {
            "type": "string",
            "description": "Einschätzung, ob Energie-/Flüssigkeitszufuhr während der Einheit ausreichend "
                           "war — anhand RPE, Splits/HF-Drift und Dauer gegen die Tabellen-Basis. Leer, "
                           "wenn die Datenlage dafür nicht reicht.",
        },
    },
    "required": ["bewertung", "urteil", "naechster_schritt", "datenlage", "ernaehrung_einschaetzung"],
    "additionalProperties": False,
}

_FIT_LABELS = [
    ("dauer_min", "Dauer", " min"), ("distanz_km", "Distanz", " km"),
    ("avg_power_w", "Ø Leistung", " W"), ("max_power_w", "Max Leistung", " W"),
    ("normalized_power_w", "NP", " W"), ("avg_hr", "Ø HF", " bpm"),
    ("max_hr", "Max HF", " bpm"), ("avg_kadenz", "Ø Kadenz", " rpm"),
    ("avg_pace_min_km", "Ø Pace", " /km"), ("tss", "TSS", ""),
    ("total_work_kj", "Gesamtarbeit", " kJ"),
    ("sport", "Sport laut FIT", ""), ("sub_sport", "Sub-Sport", ""),
]

_TP_LABELS = [
    ("totalTime", "Dauer Ist (s)"), ("totalTimePlanned", "Dauer Plan (s)"),
    ("distanceInMeters", "Distanz Ist (m)"), ("distancePlanned", "Distanz Plan (m)"),
    ("tssActual", "TSS Ist"), ("tssPlanned", "TSS Plan"),
    ("averageHeartRateInBeatsPerMinute", "Ø HF Ist"),
    ("maxHeartRateInBeatsPerMinute", "Max HF Ist"),
    ("averageWatts", "Ø Leistung Ist (W)"), ("normalizedPower", "NP Ist (W)"),
    ("averagePaceInMinutesPerKilometer", "Ø Pace Ist (min/km)"),
    ("totalWork", "Gesamtarbeit (kJ)"), ("perceivedExertion", "RPE (1–10)"),
    ("coachComments", "Coach-Notizen"), ("description", "Beschreibung"),
]

_IST_SCHLUESSEL = ["tssActual", "averageHeartRateInBeatsPerMinute",
                   "averagePaceInMinutesPerKilometer", "averageWatts",
                   "distanceInMeters", "totalTime"]


def datenlage(fit: Optional[dict], tp: Optional[dict]) -> str:
    if fit:
        return "fit"
    if tp and any(tp.get(k) for k in _IST_SCHLUESSEL):
        return "tp_ist"
    return "nur_plan"


def build_input(*, athlete: dict, sport: str, titel: str, datum: str,
                a_race: Optional[dict] = None, fit: Optional[dict] = None,
                tp: Optional[dict] = None, wetter: Optional[dict] = None,
                load: Optional[dict] = None, ernaehrung_basis: Optional[str] = None) -> str:
    lines = ["## Athlet"]
    lines.append(f"- FTP Rad: {athlete.get('ftp_watt', '?')} W")
    lines.append(f"- Laufschwelle: {athlete.get('run_threshold_pace', '?')} /km")
    lines.append(f"- CSS Schwimmen: {athlete.get('css_per_100m', '?')} /100m")
    lines.append(f"- Gewicht: {athlete.get('weight_kg', '?')} kg")
    if a_race:
        lines.append(f"- A-Rennen: {a_race.get('name')} am {a_race.get('date')}, "
                     f"Zielzeit {a_race.get('goal_total', '?')} h")

    lines.append(f"\n## Einheit\n- Sport: {sport or 'unbekannt'}\n- Titel: {titel or sport}\n- Datum: {datum}")
    if ernaehrung_basis:
        lines.append(f"\n## Ernährungsempfehlung für diese Dauer (Tabelle, bereits feststehend)\n{ernaehrung_basis}")

    if wetter and wetter.get("description"):
        if "avg_temp" in wetter:
            lines.append(
                f"\n## Wetter während der Einheit ({wetter.get('start_local', '?')}–"
                f"{wetter.get('end_local', '?')})\n"
                f"- {wetter['description']}, Ø {wetter.get('avg_temp')} °C "
                f"({wetter.get('temp_min')}–{wetter.get('temp_max')} °C), "
                f"Niederschlag {wetter.get('precip_mm', 0)} mm"
            )
        else:
            lines.append(f"\n## Wetter am {datum}\n- {wetter['description']}, "
                         f"{wetter.get('temp_min', '?')}–{wetter.get('temp_max', '?')} °C, "
                         f"Regen {wetter.get('rain_prob', 0)} %")

    if load:
        lines.append("\n## Belastungslage an diesem Tag")
        lines.append(f"- CTL {load.get('ctl', '?')} · ATL {load.get('atl', '?')} · "
                     f"TSB {load.get('tsb', '?')} · Ramp {load.get('ramp_7d', '?')}")
        lines.append("Beziehe das in die Bewertung ein — schwächere Werte bei tiefem TSB sind erwartbar.")

    if fit:
        lines.append("\n## FIT-DATEI — echte Messwerte, primäre Quelle")
        for key, label, unit in _FIT_LABELS:
            v = fit.get(key)
            if v is not None:
                lines.append(f"- {label}: {v}{unit}")
        if fit.get("laps"):
            lines.append("- Splits:")
            for lap in fit["laps"]:
                teile = []
                if "t_min" in lap:  teile.append(f"{lap['t_min']} min")
                if "km" in lap:     teile.append(f"{lap['km']} km")
                if "avg_w" in lap:  teile.append(f"{lap['avg_w']} W")
                if "avg_hr" in lap: teile.append(f"{lap['avg_hr']} bpm")
                if "pace" in lap:   teile.append(f"{lap['pace']}/km")
                lines.append("  • " + " | ".join(teile))

    if tp:
        lage = datenlage(fit, tp)
        kopf = ("## TrainingPeaks — Ist-Daten" if lage != "nur_plan"
                else "## TrainingPeaks — NUR Plan-Daten, keine Ist-Werte")
        lines.append(f"\n{kopf}")
        for key, label in _TP_LABELS:
            v = tp.get(key)
            if v not in (None, ""):
                lines.append(f"- {label}: {v}")

    if datenlage(fit, tp) == "nur_plan":
        lines.append("\nEs liegen keine Messwerte vor. Bewerte die Einheit trotzdem anhand "
                     "von Vorgabe, Beschreibung, Wetter und Kontext — und sage klar, dass "
                     "die Einschätzung auf Plandaten beruht.")

    lines.append("\nBewerte diese Einheit.")
    return "\n".join(lines)


def run(*, athlete: dict, a_race=None, sport: str = "", titel: str = "", datum: str = "",
        fit=None, tp=None, wetter=None, load=None, ernaehrung_basis=None, model: str = HAIKU) -> dict:
    return call_agent(
        prompt=load_prompt("analyst"),
        schema=SCHEMA,
        user=build_input(athlete=athlete, a_race=a_race, sport=sport, titel=titel,
                         datum=datum, fit=fit, tp=tp, wetter=wetter, load=load,
                         ernaehrung_basis=ernaehrung_basis),
        model=model,
        max_tokens=2000,
        label="analyst",
    )
