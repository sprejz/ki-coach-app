"""Recherche-Agent — liest frei verfügbare Sportwissenschaft, schlägt Funde vor.

Läuft NIE automatisch mit einem Check. Ein Thema kommt von Hendrik (Profil-Tab
oder curl), der Agent sucht per Claudes serverseitigem web_search-Tool und
liefert Funde zurück. Die Funde sind ein VORSCHLAG — erst wenn Hendrik einen
Fund im Profil-Tab akzeptiert (siehe knowledge.py), fließt er als Zusatzkontext
in den Chefcoach-Prompt (agents/head_coach/head_coach.py) ein. Kein Fund wird
je automatisch wirksam.
"""
from pathlib import Path

from ..base import SONNET, call_agent_with_search, load_prompt

_PROMPT_PATH = Path(__file__).parent / "research.md"
_VIDEO_PROMPT_PATH = Path(__file__).parent / "research_video.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "zusammenfassung": {
            "type": "string",
            "description": "1-2 Sätze Überblick über die recherchierte Studienlage.",
        },
        "erkenntnisse": {
            "type": "array",
            "description": "Konkrete, einzeln nutzbare Funde. Leer, wenn nichts Belastbares gefunden wurde.",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string", "description": "Kurzer Titel des Fundes."},
                    "aussage": {
                        "type": "string",
                        "description": "1-3 Sätze Kernerkenntnis, konkret genug für einen Prompt-Zusatz.",
                    },
                    "quelle": {"type": "string", "description": "URL oder Zitation der tatsächlich gefundenen Quelle."},
                    "konfidenz": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                    "betrifft": {
                        "type": "string",
                        "description": "Freier Hinweis, welchen Bereich der Fund betrifft, z.B. 'Ernährung', 'Tapering'.",
                    },
                },
                "required": ["titel", "aussage", "quelle", "konfidenz", "betrifft"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["zusammenfassung", "erkenntnisse"],
    "additionalProperties": False,
}


def run(*, thema: str, model: str = SONNET) -> dict:
    return call_agent_with_search(
        prompt=load_prompt("research", path=_PROMPT_PATH),
        user=f"Recherchiere zu folgendem Thema: {thema}",
        schema=SCHEMA,
        model=model,
        max_tokens=6000,
        max_uses=5,
        label="research",
    )


def run_video(*, titel: str, url: str, transcript: str, gekuerzt: bool = False,
              model: str = SONNET) -> dict:
    """Wertet ein Video-/Podcast-Transkript aus (v2.9.2) — Transkript kommt fertig
    von youtube.py, hier passiert nur noch die Bewertung. Nutzt dasselbe SCHEMA
    wie run(): knowledge.add_findings() muss nicht wissen, ob ein Fund aus einer
    Websuche oder einem Transkript stammt."""
    hinweis = ("\n\n[Hinweis: Transkript wurde gekürzt, du siehst nicht das "
               "ganze Video.]" if gekuerzt else "")
    user = f"Video-Titel: {titel}\nURL: {url}\n\nTranskript:\n{transcript}{hinweis}"
    return call_agent_with_search(
        prompt=load_prompt("research_video", path=_VIDEO_PROMPT_PATH),
        user=user,
        schema=SCHEMA,
        model=model,
        max_tokens=6000,
        max_uses=5,
        label="research_video",
    )
