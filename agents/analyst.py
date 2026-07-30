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

# Feldnamen von tp_get_workout (MCP-Server) — snake_case, größtenteils unter
# "metrics" verschachtelt. Bewusst NICHT die TP-eigenen camelCase-API-Namen
# (totalTime, tssActual, …): das MCP normalisiert die Antwort um, ein Abgleich
# gegen echte Live-Daten hat das aufgedeckt (vorher landeten nur "description"
# und keine einzige Zahl beim Analysten).
_TP_METRIC_LABELS = [
    ("duration_actual", "Dauer Ist (min)", 60), ("duration_planned", "Dauer Plan (min)", 60),
    ("distance_actual_km", "Distanz Ist (km)", 1), ("distance_planned_km", "Distanz Plan (km)", 1),
    ("tss_actual", "TSS Ist", 1), ("tss_planned", "TSS Plan", 1),
    ("avg_hr", "Ø HF Ist (bpm)", 1),
    ("avg_power", "Ø Leistung Ist (W)", 1), ("normalized_power", "NP Ist (W)", 1),
    ("avg_cadence", "Ø Kadenz Ist", 1),
    ("calories", "Kalorien Ist", 1),
]
# duration_* kommt in Stunden (Bruchzahl) — Faktor 60 rechnet in Minuten um.

_TP_TOP_LABELS = [
    ("rpe", "RPE (1–10)"), ("feeling", "Gefühl (1–10)"), ("description", "Beschreibung"),
]

# Nur Felder, die zweifelsfrei eine ausgeführte Einheit voraussetzen (Ist-Werte
# vom Gerät) — duration_actual/tss_actual sind laut Live-Beispiel auch bei
# reinen Planwerten befüllt, also kein verlässliches Signal.
_IST_SCHLUESSEL_METRICS = ["avg_hr", "avg_power", "avg_cadence"]


def datenlage(fit: Optional[dict], tp: Optional[dict]) -> str:
    if fit:
        return "fit"
    if tp and any((tp.get("metrics") or {}).get(k) for k in _IST_SCHLUESSEL_METRICS):
        return "tp_ist"
    return "nur_plan"


def _sek_zu_pace(sekunden: float) -> str:
    return f"{int(sekunden // 60)}:{int(sekunden % 60):02d}"


def _dauer_text(sekunden) -> str:
    if not sekunden:
        return "?"
    sekunden = int(sekunden)
    if sekunden % 60 == 0:
        return f"{sekunden // 60} min"
    return f"{sekunden}s"


def _ziel_wert(lo, hi, metric: str, sport: str, athlete: dict) -> str:
    """Rechnet einen Prozent-der-Schwelle-Zielbereich in eine konkrete Zahl um
    (Watt bzw. Pace) — höherer Prozentwert heißt schneller/stärker, wie im
    übrigen Code (translations.py-Zonentabelle, architect.py) schon gehandhabt."""
    if lo is None or hi is None:
        return ""
    try:
        if metric == "percentOfFtp":
            ftp = float(athlete.get("ftp_watt") or 0)
            if not ftp:
                return ""
            return f"{round(ftp * lo / 100)}–{round(ftp * hi / 100)} W"
        if metric == "percentOfThresholdPace":
            ist_schwimmen = "schwimm" in (sport or "").lower() or "swim" in (sport or "").lower()
            basis = athlete.get("css_per_100m") if ist_schwimmen else athlete.get("run_threshold_pace")
            einheit = "/100m" if ist_schwimmen else "/km"
            if not basis or ":" not in str(basis):
                return ""
            m, s = str(basis).split(":")
            schwelle_sek = int(m) * 60 + int(s)
            werte = sorted(schwelle_sek / (p / 100) for p in (lo, hi) if p)
            if not werte:
                return ""
            return f"{_sek_zu_pace(werte[0])}–{_sek_zu_pace(werte[-1])}{einheit}"
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    return ""


def _render_struktur(struktur: dict, sport: str, athlete: dict) -> str:
    """Baut aus tp_get_workout's structured_workout eine lesbare Zielvorgabe
    pro Schritt — der Analyst kann damit Ist-Pace/-Watt pro Wiederholung gegen
    das ECHTE Ziel prüfen, statt nur gegen den (oft nur verkürzenden) Titel."""
    metric = struktur.get("primaryIntensityMetric", "")
    zeilen = []

    def schritt_zeile(schritt: dict, einzug: str) -> str:
        name = schritt.get("name", "Schritt")
        laenge = schritt.get("length", {}) or {}
        dauer = _dauer_text(laenge.get("value")) if laenge.get("unit") == "second" else ""
        ziele = schritt.get("targets") or []
        ziel_text = _ziel_wert(ziele[0].get("minValue"), ziele[0].get("maxValue"), metric, sport, athlete) if ziele else ""
        stueck = f"{einzug}{name}"
        if dauer:
            stueck += f": {dauer}"
        if ziel_text:
            stueck += f" @ {ziel_text}"
        return stueck

    for block in struktur.get("structure") or []:
        if block.get("type") == "repetition":
            reps = (block.get("length") or {}).get("value", "?")
            zeilen.append(f"{reps}× Wiederholung:")
            for schritt in block.get("steps") or []:
                zeilen.append(schritt_zeile(schritt, "  - "))
        else:
            for schritt in block.get("steps") or []:
                zeilen.append(schritt_zeile(schritt, "- "))
    return "\n".join(zeilen)


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
        for key, label in _TP_TOP_LABELS:
            v = tp.get(key)
            if v not in (None, ""):
                lines.append(f"- {label}: {v}")
        metrics = tp.get("metrics") or {}
        for key, label, faktor in _TP_METRIC_LABELS:
            v = metrics.get(key)
            if v is not None:
                wert = round(v * faktor, 1) if faktor != 1 else round(v, 1)
                lines.append(f"- {label}: {wert}")

        struktur = tp.get("structured_workout")
        if struktur and struktur.get("structure"):
            lines.append(
                "\n## Geplante Struktur (TrainingPeaks, echte Ziel-Werte pro Schritt)\n"
                "Vergleiche Ist-Pace/-Watt pro Wiederholung gegen DIESE Ziele, nicht nur "
                "gegen den (oft verkürzenden) Titel:"
            )
            lines.append(_render_struktur(struktur, sport, athlete))

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
