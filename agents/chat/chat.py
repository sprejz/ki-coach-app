"""Coach-Chat — freies Gespräch mit Zugriff auf Plan, Wetter und Belastung.

Der einzige Agent ohne Schema: die Antwort geht direkt an den Athleten, nicht
an ein weiterverarbeitendes System. Der Kontext wird deterministisch gebaut —
was nicht drinsteht, hat der Coach nicht, und das sagt der Prompt ihm auch.
"""
import logging
from pathlib import Path
from typing import Optional

from ..base import HAIKU, call_agent_with_tools, load_prompt

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "chat.md"

MAX_HISTORIE = 10

# Feldnamen bewusst identisch zu den call_tp_mcp-Argumenten (title, description,
# date, text) — der Server reicht ein Tool-Input 1:1 weiter, keine Umbenennung
# zwischen Tool-Aufruf und MCP-Call nötig. Wichtig: der Server EXECUTED hier
# nichts — er löst date+workout_hint nur zu einer echten workout_id auf und legt
# eine pending action an, die der Athlet erst per Klick bestätigen muss.
PROPOSE_WORKOUT_UPDATE_TOOL = {
    "name": "propose_workout_update",
    "description": (
        "Schlägt eine Änderung von Titel und/oder Beschreibung EINER bestehenden "
        "TrainingPeaks-Einheit vor, die weiter oben im Kontext (TrainingPeaks-Plan) "
        "aufgeführt ist. KEINE Änderung von Datum, Dauer oder Sportart möglich — nur "
        "Titel/Beschreibung. Ruf dieses Tool NUR auf, wenn der Athlet klar und konkret "
        "eine Änderung an EINER bestimmten, dir bereits bekannten Einheit verlangt. "
        "Rate niemals eine workout_id — du bekommst nie eine gezeigt; date + "
        "workout_hint reichen, der Server findet die Einheit selbst. Bist du unsicher, "
        "welche Einheit oder welcher Tag gemeint ist, rufe das Tool NICHT auf, sondern "
        "frag im Text nach."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "ISO-Datum (YYYY-MM-DD) der Einheit, exakt wie im "
                    "TrainingPeaks-Plan-Abschnitt oben angegeben — nicht selbst "
                    "berechnen oder raten."
                ),
            },
            "workout_hint": {
                "type": "string",
                "description": (
                    "Sportart oder ein Ausschnitt aus dem Titel der Einheit, WÖRTLICH "
                    "aus der passenden Plan-Zeile oben kopiert, damit der Server an "
                    "diesem Datum eindeutig die richtige Einheit findet."
                ),
            },
            "new_title": {
                "type": "string",
                "description": "Neuer Titel der Einheit. Weglassen, wenn nur die Beschreibung geändert werden soll.",
            },
            "new_description": {
                "type": "string",
                "description": "Neue oder ergänzte Beschreibung der Einheit. Weglassen, wenn nur der Titel geändert werden soll.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "Ein kurzer, an den Athleten gerichteter deutscher Satz, der die "
                    "vorgeschlagene Änderung zusammenfasst. Wird WÖRTLICH als "
                    "Chat-Antwort und als Überschrift der Bestätigungs-Karte angezeigt, "
                    "z.B. 'Ich schlage vor, den Longrun morgen in \"Longrun locker – "
                    "Regen\" umzubenennen.'"
                ),
            },
        },
        "required": ["date", "workout_hint", "summary"],
        "anyOf": [
            {"required": ["new_title"]},
            {"required": ["new_description"]},
        ],
    },
}

PROPOSE_CALENDAR_NOTE_TOOL = {
    "name": "propose_calendar_note",
    "description": (
        "Schlägt eine NEUE Kalendernotiz in TrainingPeaks vor — z.B. für Krankheit, "
        "Reise oder eine sonstige Information für den Kalender. KEINE neue "
        "Trainingseinheit, keine Änderung einer bestehenden Einheit — dafür gibt es "
        "propose_workout_update. Ruf dieses Tool nur bei einer klaren Bitte um einen "
        "Kalendereintrag auf."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date":    {"type": "string", "description": "ISO-Datum (YYYY-MM-DD) für die Notiz."},
            "title":   {"type": "string", "description": "Kurzer Betreff der Notiz."},
            "text":    {"type": "string", "description": "Notiztext."},
            "summary": {
                "type": "string",
                "description": (
                    "Kurzer deutscher Satz an den Athleten, der die vorgeschlagene "
                    "Notiz zusammenfasst — wird wörtlich als Chat-Antwort und "
                    "Karten-Überschrift verwendet."
                ),
            },
        },
        "required": ["date", "title", "text", "summary"],
    },
}

CHAT_TOOLS = [PROPOSE_WORKOUT_UPDATE_TOOL, PROPOSE_CALENDAR_NOTE_TOOL]


def build_context(*, athlete: dict, a_race: Optional[dict], tage_bis_a: Optional[int],
                  tp_tage: Optional[list] = None, wetter_heute: Optional[dict] = None,
                  wetter_morgen: Optional[dict] = None, load: Optional[dict] = None,
                  ladend: Optional[list] = None, heute_str: str = "") -> str:
    """Baut den Datenteil, der an den statischen Prompt gehängt wird."""
    lines = []
    if heute_str:
        lines.append(f"## Heute ist {heute_str}")

    lines.append("\n## Athlet")
    lines.append(f"- {athlete.get('name', 'Athlet')}, {athlete.get('weight_kg', '?')} kg")
    lines.append(f"- FTP Rad {athlete.get('ftp_watt', '?')} W · "
                 f"Laufschwelle {athlete.get('run_threshold_pace', '?')} /km · "
                 f"CSS {athlete.get('css_per_100m', '?')} /100m")
    if a_race:
        lines.append(f"- A-Rennen: {a_race.get('name')} am {a_race.get('date')}"
                     + (f", noch {tage_bis_a} Tage" if tage_bis_a is not None else "")
                     + (f", Zielzeit {a_race['goal_total']} h" if a_race.get("goal_total") else ""))
    if athlete.get("chronische_befunde"):
        lines.append(f"- Chronische Befunde: {athlete['chronische_befunde']}")

    n = athlete.get("nutrition") or {}
    if n:
        lines.append("\n## Ernährungsregeln (Tabelle des Athleten — echte Zahlen, nutze sie wörtlich)")
        lines.append(
            f"- Mix: {n.get('mix', '?')} · Carbs: {n.get('carbs_per_hour_g', '?')} g/h · "
            f"Flüssigkeit: {n.get('fluid_per_hour_ml', '?')} ml/h "
            f"(Hitze ab {n.get('heat_threshold_celsius', '?')} °C: {n.get('fluid_heat_per_hour_ml', '?')} ml/h) · "
            f"Salz: {n.get('salt_per_hour', '?')} Saltstick/h (Hitze: {n.get('salt_heat_per_hour', '?')})"
        )
        for rule in n.get("rules", []):
            lo, hi = rule.get("duration_min_min", 0), rule.get("duration_max_min")
            dauer_label = f"{lo}–{hi} min" if hi else f"ab {lo} min"
            teile = [t for t in (
                f"Vorher: {rule['before']}" if rule.get("before") else "",
                f"Während: {rule['during']}" if rule.get("during") else "",
                f"Nachher: {rule['after']}" if rule.get("after") else "",
            ) if t]
            lines.append(f"  - {dauer_label}: {' | '.join(teile)}")
        lines.append(
            "Nutze diese Zahlen wörtlich, wenn er nach Ernährung fragt. Erfinde keine "
            "eigenen Gramm-/ml-Werte — was hier nicht steht, weißt du nicht."
        )

    if load:
        lines.append("\n## Belastungslage")
        lines.append(f"- CTL {load.get('ctl')} (Fitness) · ATL {load.get('atl')} (Ermüdung) · "
                     f"TSB {load.get('tsb')} (Frische)")
        lines.append(f"- Ramp Rate 7 Tage: {load.get('ramp_7d')} · "
                     f"TSS letzte 7 Tage: {load.get('tss_7d')}")

    lines.append("\n## TrainingPeaks-Plan")
    if tp_tage:
        for eintrag in tp_tage:
            lines.append(f"- {eintrag}")
    else:
        lines.append("- Für die angefragten Tage sind keine Einheiten geplant.")
    if ladend:
        lines.append(f"- Für diese Tage werden die Daten noch geladen: {', '.join(ladend)}. "
                     "Sag dem Athleten, dass er in etwa einer Minute nochmal fragen kann.")

    lines.append("\n## Wetter")
    if wetter_heute or wetter_morgen:
        for label, w in (("heute", wetter_heute), ("morgen", wetter_morgen)):
            if w:
                lines.append(f"- {label}: {w.get('description', '?')}, "
                             f"{w.get('temp_min', '?')}–{w.get('temp_max', '?')} °C, "
                             f"Regen {w.get('rain_prob', 0)} %")
    else:
        lines.append("- Keine Wetterdaten verfügbar. Antworte ohne Wetterbezug, "
                     "spekuliere nicht.")

    return "\n".join(lines)


def run(*, nachricht: str, historie: Optional[list] = None, kontext: str = "",
        model: str = HAIKU, max_tokens: int = 1500) -> dict:
    """Gibt {"text": str, "tool_call": {"name","input"}|None} zurück — der
    Aufrufer (app.py) entscheidet, ob/wie er aus einem Tool-Call eine pending
    action baut. Der Chat selbst führt nie etwas aus."""
    system = load_prompt("chat", path=_PROMPT_PATH)
    if kontext:
        system = f"{system}\n\n---\n\n{kontext}"

    messages = []
    for h in (historie or [])[-MAX_HISTORIE:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": nachricht})

    return call_agent_with_tools(prompt=system, messages=messages, tools=CHAT_TOOLS,
                                 model=model, max_tokens=max_tokens, label="chat")
