"""Gemeinsame Infrastruktur für alle Coach-Agents.

Jeder Agent ist ein Modul mit einem statischen Prompt (prompts/<lang>/<name>.md),
einem JSON-Schema und einer run()-Funktion. Das Schema wird über output_config
hart erzwungen — deshalb braucht hier niemand mehr JSON aus Prosa zu extrahieren.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
PROMPT_DIR = BASE_DIR / "prompts"

# Modell-Tiering: bewusst erstmal überall Haiku. Chefcoach und Architekt können
# später einzeln hochgezogen werden, ohne dass sich hier etwas anderes ändert.
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-5"
OPUS = "claude-opus-5"

_prompt_cache: dict = {}

# Token-Verbrauch pro Aufruf, für Kostenmessung in Tests. Preise in $/1M Token.
USAGE: list = []
PREISE = {
    HAIKU: (1.0, 5.0),
    SONNET: (3.0, 15.0),
    OPUS: (5.0, 25.0),
}


def kosten(eintraege: Optional[list] = None) -> float:
    """Summiert die Kosten der erfassten Aufrufe in Dollar."""
    total = 0.0
    for e in eintraege if eintraege is not None else USAGE:
        p_in, p_out = PREISE.get(e["model"], (0.0, 0.0))
        total += e["in"] * p_in / 1_000_000 + e["out"] * p_out / 1_000_000
    return total


class AgentError(RuntimeError):
    """Ein Agent konnte kein verwertbares Ergebnis liefern."""


def load_prompt(name: str, lang: Optional[str] = None, path: Optional[Path] = None) -> str:
    """Lädt einen Prompt.

    Ohne `path`: prompts/<lang>/<name>.md, mit Fallback auf Deutsch (Standardfall).
    Mit `path`: liest direkt von dort — für Agenten, die ihren Prompt im eigenen
    Ordner statt zentral unter prompts/ halten (z.B. die Architekt-Disziplin-Agenten).
    """
    if path is not None:
        cache_key = str(path)
        if cache_key in _prompt_cache:
            return _prompt_cache[cache_key]
        if not path.exists():
            raise AgentError(f"Prompt nicht gefunden: {path}")
        text = path.read_text(encoding="utf-8").strip()
        _prompt_cache[cache_key] = text
        return text

    lang = lang or os.environ.get("APP_LANG", "de")
    cache_key = f"{lang}/{name}"
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]
    p = PROMPT_DIR / lang / f"{name}.md"
    if not p.exists():
        p = PROMPT_DIR / "de" / f"{name}.md"
    if not p.exists():
        raise AgentError(f"Prompt nicht gefunden: {name} ({lang})")
    text = p.read_text(encoding="utf-8").strip()
    _prompt_cache[cache_key] = text
    return text


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AgentError("ANTHROPIC_API_KEY ist nicht gesetzt")
    return anthropic.Anthropic(api_key=key)


def call_agent(
    *,
    prompt: str,
    schema: dict,
    user: str,
    model: str = HAIKU,
    max_tokens: int = 4000,
    label: str = "agent",
) -> dict:
    """Ruft einen Agent mit erzwungenem JSON-Schema auf.

    Das Modell kann kein ungültiges JSON und keine Prosa drumherum produzieren —
    output_config bindet die Antwort an das Schema.
    """
    client = _client()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=prompt,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIStatusError as e:
        logger.error("%s: API %s — %s", label, e.status_code, e.message)
        raise AgentError(f"{label}: API-Fehler {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        logger.error("%s: Verbindungsfehler — %s", label, e)
        raise AgentError(f"{label}: API nicht erreichbar") from e

    if resp.stop_reason == "refusal":
        logger.error("%s: Anfrage abgelehnt", label)
        raise AgentError(f"{label}: Anfrage wurde abgelehnt")
    if resp.stop_reason == "max_tokens":
        # Bei erzwungenem Schema heißt das: abgeschnittenes JSON. Nicht parsebar.
        logger.error("%s: max_tokens (%d) erreicht, JSON unvollständig", label, max_tokens)
        raise AgentError(f"{label}: Antwort zu lang (max_tokens={max_tokens})")

    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise AgentError(f"{label}: leere Antwort")

    USAGE.append({
        "label": label, "model": model,
        "in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
    })
    logger.info(
        "%s ok: model=%s in=%d out=%d",
        label, model, resp.usage.input_tokens, resp.usage.output_tokens,
    )
    return json.loads(text)


def call_agent_text(
    *,
    prompt: str,
    messages: list,
    model: str = HAIKU,
    max_tokens: int = 1500,
    label: str = "agent",
) -> str:
    """Freitext-Variante für den Chat — kein Schema, mehrere Turns.

    Der Chat ist der einzige Agent ohne Schema: seine Antwort geht direkt an
    den Athleten, nicht an ein weiterverarbeitendes System.
    """
    client = _client()
    try:
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=prompt, messages=messages,
        )
    except anthropic.APIStatusError as e:
        logger.error("%s: API %s — %s", label, e.status_code, e.message)
        raise AgentError(f"{label}: API-Fehler {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        logger.error("%s: Verbindungsfehler — %s", label, e)
        raise AgentError(f"{label}: API nicht erreichbar") from e

    if resp.stop_reason == "refusal":
        raise AgentError(f"{label}: Anfrage wurde abgelehnt")

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise AgentError(f"{label}: leere Antwort")

    USAGE.append({
        "label": label, "model": model,
        "in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
    })
    logger.info("%s ok: model=%s in=%d out=%d%s", label, model,
                resp.usage.input_tokens, resp.usage.output_tokens,
                " (abgeschnitten)" if resp.stop_reason == "max_tokens" else "")
    return text


# Architekt-Schema + Eingabebau leben hier statt in agents/architect, weil sie
# ab v2.7.12 von vier Modulen genutzt werden (generischer Fallback für
# Kraft/Sonstiges + je ein Disziplin-Agent für Lauf/Rad/Schwimm) — ohne diese
# gemeinsame Stelle müssten alle vier dasselbe ~80-Zeilen-Schema pflegen.

# Identisch zur Struktur, die tp_create_workout erwartet. Bewusst nicht rekursiv:
# ein Wiederholungsblock enthält nur Einzelschritte.
_ARCHITECT_STEP = {
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

_ARCHITECT_REPETITION = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "repetition"},
        "reps": {"type": "integer"},
        "steps": {"type": "array", "items": _ARCHITECT_STEP},
    },
    "required": ["type", "reps", "steps"],
    "additionalProperties": False,
}

ARCHITECT_SCHEMA = {
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
                        "steps": {"type": "array", "items": {"anyOf": [_ARCHITECT_STEP, _ARCHITECT_REPETITION]}},
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


def build_architect_input(*, athlete: dict, workout: dict, auftrag: dict, wetter_zeile: str = "") -> str:
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


# Analyst-Schema + Eingabebau leben hier statt in einem eigenen Modul, weil sie
# von den drei Disziplin-Agenten (agents/analyst_run/_bike/_swim) gemeinsam
# genutzt werden — analog zum Architekt-Schema oben. Es gibt bewusst KEINEN
# generischen Kraft/Sonstiges-Fallback wie beim Architekten: der Analyse-Tab
# zeigt im Frontend ohnehin nur Lauf-/Rad-/Schwimmeinheiten zur Auswahl
# (SPORT_OK-Filter in templates/index.html), ein generischer Analyst wäre
# dort nie erreichbar gewesen — bis v2.7.28 lief er trotzdem mit, als totes
# Fallback-Gewicht.

ANALYST_SCHEMA = {
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

_ANALYST_FIT_LABELS = [
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
_ANALYST_TP_METRIC_LABELS = [
    ("duration_actual", "Dauer Ist (min)", 60), ("duration_planned", "Dauer Plan (min)", 60),
    ("distance_actual_km", "Distanz Ist (km)", 1), ("distance_planned_km", "Distanz Plan (km)", 1),
    ("tss_actual", "TSS Ist", 1), ("tss_planned", "TSS Plan", 1),
    ("avg_hr", "Ø HF Ist (bpm)", 1),
    ("avg_power", "Ø Leistung Ist (W)", 1), ("normalized_power", "NP Ist (W)", 1),
    ("avg_cadence", "Ø Kadenz Ist", 1),
    ("calories", "Kalorien Ist", 1),
]
# duration_* kommt in Stunden (Bruchzahl) — Faktor 60 rechnet in Minuten um.

_ANALYST_TP_TOP_LABELS = [
    ("rpe", "RPE (1–10)"), ("feeling", "Gefühl (1–10)"), ("description", "Beschreibung"),
]

# Nur Felder, die zweifelsfrei eine ausgeführte Einheit voraussetzen (Ist-Werte
# vom Gerät) — duration_actual/tss_actual sind laut Live-Beispiel auch bei
# reinen Planwerten befüllt, also kein verlässliches Signal.
_ANALYST_IST_SCHLUESSEL_METRICS = ["avg_hr", "avg_power", "avg_cadence"]


def analyst_datenlage(fit: Optional[dict], tp: Optional[dict]) -> str:
    if fit:
        return "fit"
    if tp and any((tp.get("metrics") or {}).get(k) for k in _ANALYST_IST_SCHLUESSEL_METRICS):
        return "tp_ist"
    return "nur_plan"


def _analyst_sek_zu_pace(sekunden: float) -> str:
    return f"{int(sekunden // 60)}:{int(sekunden % 60):02d}"


def _analyst_dauer_text(sekunden) -> str:
    if not sekunden:
        return "?"
    sekunden = int(sekunden)
    if sekunden % 60 == 0:
        return f"{sekunden // 60} min"
    return f"{sekunden}s"


def _analyst_ziel_wert(lo, hi, metric: str, sport: str, athlete: dict) -> str:
    """Rechnet einen Prozent-der-Schwelle-Zielbereich in eine konkrete Zahl um
    (Watt bzw. Pace) — höherer Prozentwert heißt schneller/stärker, wie im
    übrigen Code (translations.py-Zonentabelle, build_architect_input) schon
    gehandhabt."""
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
            return f"{_analyst_sek_zu_pace(werte[0])}–{_analyst_sek_zu_pace(werte[-1])}{einheit}"
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    return ""


def _analyst_render_struktur(struktur: dict, sport: str, athlete: dict) -> str:
    """Baut aus tp_get_workout's structured_workout eine lesbare Zielvorgabe
    pro Schritt — der Analyst kann damit Ist-Pace/-Watt pro Wiederholung gegen
    das ECHTE Ziel prüfen, statt nur gegen den (oft nur verkürzenden) Titel."""
    metric = struktur.get("primaryIntensityMetric", "")
    zeilen = []

    def schritt_zeile(schritt: dict, einzug: str) -> str:
        name = schritt.get("name", "Schritt")
        laenge = schritt.get("length", {}) or {}
        dauer = _analyst_dauer_text(laenge.get("value")) if laenge.get("unit") == "second" else ""
        ziele = schritt.get("targets") or []
        ziel_text = (_analyst_ziel_wert(ziele[0].get("minValue"), ziele[0].get("maxValue"), metric, sport, athlete)
                    if ziele else "")
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


def build_analyst_input(*, athlete: dict, sport: str, titel: str, datum: str,
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
        for key, label, unit in _ANALYST_FIT_LABELS:
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
        lage = analyst_datenlage(fit, tp)
        kopf = ("## TrainingPeaks — Ist-Daten" if lage != "nur_plan"
                else "## TrainingPeaks — NUR Plan-Daten, keine Ist-Werte")
        lines.append(f"\n{kopf}")
        for key, label in _ANALYST_TP_TOP_LABELS:
            v = tp.get(key)
            if v not in (None, ""):
                lines.append(f"- {label}: {v}")
        metrics = tp.get("metrics") or {}
        for key, label, faktor in _ANALYST_TP_METRIC_LABELS:
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
            lines.append(_analyst_render_struktur(struktur, sport, athlete))

    if analyst_datenlage(fit, tp) == "nur_plan":
        lines.append("\nEs liegen keine Messwerte vor. Bewerte die Einheit trotzdem anhand "
                     "von Vorgabe, Beschreibung, Wetter und Kontext — und sage klar, dass "
                     "die Einschätzung auf Plandaten beruht.")

    lines.append("\nBewerte diese Einheit.")
    return "\n".join(lines)
