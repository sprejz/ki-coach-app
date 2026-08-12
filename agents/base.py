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
