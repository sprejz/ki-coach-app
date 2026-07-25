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


def load_prompt(name: str, lang: Optional[str] = None) -> str:
    """Lädt prompts/<lang>/<name>.md. Fällt auf Deutsch zurück."""
    lang = lang or os.environ.get("APP_LANG", "de")
    key = f"{lang}/{name}"
    if key in _prompt_cache:
        return _prompt_cache[key]
    path = PROMPT_DIR / lang / f"{name}.md"
    if not path.exists():
        path = PROMPT_DIR / "de" / f"{name}.md"
    if not path.exists():
        raise AgentError(f"Prompt nicht gefunden: {name} ({lang})")
    text = path.read_text(encoding="utf-8").strip()
    _prompt_cache[key] = text
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
