"""Coach-Chat — freies Gespräch mit Zugriff auf Plan, Wetter und Belastung.

Der einzige Agent ohne Schema: die Antwort geht direkt an den Athleten, nicht
an ein weiterverarbeitendes System. Der Kontext wird deterministisch gebaut —
was nicht drinsteht, hat der Coach nicht, und das sagt der Prompt ihm auch.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from ..base import HAIKU, call_agent_with_consult, call_agent_with_tools, load_prompt

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
        "Titel/Beschreibung. Gib MINDESTENS eines von new_title/new_description an — "
        "ein Aufruf ohne beides wird verworfen. Ruf dieses Tool NUR auf, wenn der "
        "Athlet klar und konkret eine Änderung an EINER bestimmten, dir bereits "
        "bekannten Einheit verlangt. Rate niemals eine workout_id — du bekommst nie "
        "eine gezeigt; date + workout_hint reichen, der Server findet die Einheit "
        "selbst. Bist du unsicher, welche Einheit oder welcher Tag gemeint ist, rufe "
        "das Tool NICHT auf, sondern frag im Text nach."
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

PROPOSE_WORKOUT_SKIP_TOOL = {
    "name": "propose_workout_skip",
    "description": (
        "Schlägt vor, EINE bestehende TrainingPeaks-Einheit zu streichen — z.B. weil "
        "sie ausfällt oder etwas anderes Vorrang hat. Die Einheit wird dabei NICHT "
        "gelöscht, sondern genau wie im Abend-/Morgen-Check mit ❌ im Titel markiert "
        "(derselbe Titel-Präfix, den auch der SKIP-Badge dort setzt). Du gibst keinen "
        "neuen Titel an — der Server übernimmt die Umbenennung nach dieser festen "
        "Konvention. Ruf dieses Tool auf, wenn der Athlet klar eine bestimmte Einheit "
        "streichen will (\"streich\", \"fällt aus\", \"lass weg\", \"nicht heute\"). "
        "Rate niemals eine workout_id — date + workout_hint reichen, der Server findet "
        "die Einheit selbst."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "ISO-Datum (YYYY-MM-DD) der Einheit, exakt wie im "
                    "TrainingPeaks-Plan-Abschnitt oben angegeben."
                ),
            },
            "workout_hint": {
                "type": "string",
                "description": (
                    "Sportart oder ein Ausschnitt aus dem Titel der Einheit, WÖRTLICH "
                    "aus der passenden Plan-Zeile oben kopiert."
                ),
            },
            "summary": {
                "type": "string",
                "description": (
                    "Ein kurzer, an den Athleten gerichteter deutscher Satz, der das "
                    "Streichen zusammenfasst. Wird wörtlich als Chat-Antwort und "
                    "Karten-Überschrift verwendet."
                ),
            },
        },
        "required": ["date", "workout_hint", "summary"],
    },
}

PROPOSE_WORKOUT_SERIES_TOOL = {
    "name": "propose_workout_series",
    "description": (
        "Schlägt EINE ODER MEHRERE NEUE TrainingPeaks-Einheiten vor — auch eine "
        "ganze Serie auf einmal (z.B. 'Mo/Mi/Fr je 45min lockeres Rad'). NUR für "
        "neue Einheiten, NICHT für bestehende: eine bestehende Einheit umbenennen "
        "geht über propose_workout_update, streichen über propose_workout_skip. "
        "Du kannst KEINE bestehende Einheit verschieben oder umplanen — dafür gibt "
        "es kein Tool, verweise den Athleten auf den Abend-/Morgen-Check. Jede "
        "Einheit braucht mindestens 20 Minuten Dauer. Baue KEINE Intervallstruktur "
        "und erfinde keinen TSS ohne Grundlage — für echte Intervalle verweist du "
        "auf den Check (dort formuliert der zuständige Disziplin-Coach das aus). "
        "Ruf dieses Tool nur bei einer klaren Bitte auf, neue Einheit(en) "
        "anzulegen; bei Unsicherheit über Sportart, Datum oder Dauer frag im Text "
        "nach, statt zu raten."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "workouts": {
                "type": "array",
                "minItems": 1,
                "description": "Ein Eintrag pro neuer Einheit — bei einer Serie mehrere Einträge.",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "ISO-Datum (YYYY-MM-DD) der neuen Einheit.",
                        },
                        "sport": {
                            "type": "string",
                            "enum": ["Schwimmen", "Rad", "Laufen", "Kraft", "Sonstiges"],
                        },
                        "title": {"type": "string", "description": "Titel der neuen Einheit."},
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Dauer in Minuten, mindestens 20.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optionale Beschreibung/Hinweis für das TP-Beschreibungsfeld.",
                        },
                        "tss": {
                            "type": "integer",
                            "description": "Nur wenn eine sinnvolle Schätzung möglich ist, sonst weglassen.",
                        },
                        "distance_km": {
                            "type": "number",
                            "description": "Nur bei Schwimmen, wenn eine Distanz genannt wurde.",
                        },
                    },
                    "required": ["date", "sport", "title", "duration_minutes"],
                },
            },
            "summary": {
                "type": "string",
                "description": (
                    "Ein kurzer, an den Athleten gerichteter deutscher Satz, der die "
                    "vorgeschlagene(n) neue(n) Einheit(en) zusammenfasst. Wird wörtlich "
                    "als Chat-Antwort und Karten-Überschrift verwendet."
                ),
            },
        },
        "required": ["workouts", "summary"],
    },
}

CHAT_TOOLS = [
    PROPOSE_WORKOUT_UPDATE_TOOL, PROPOSE_CALENDAR_NOTE_TOOL,
    PROPOSE_WORKOUT_SKIP_TOOL, PROPOSE_WORKOUT_SERIES_TOOL,
]

# Consult-Tools: LESEND, kein TP-Zugriff, keine pending action/Karte nötig.
# Anders als bei den propose_*-Tools führt app.py hier den echten Spezialisten
# aus (call_agent_with_consult) und spielt dessen Ergebnis Claude zurück, damit
# eine echte fachliche Einschätzung in die Antwort einfließt — nicht nur
# geratener Tool-Input. Alle Felder bewusst optional: Anthropic-Tool-Input muss
# aus Fließtext extrahiert werden, und die Spezialisten defaulten fehlende
# koerper-Werte selbst schon auf neutral (medic.build_input etc.).
_CONSULT_HINWEIS = (
    " Ruf dieses Tool NUR bei echtem fachlichem Bedarf auf — nicht bei Small "
    "Talk, nicht wenn die Antwort schon oben im Kontext steht."
)

CONSULT_MEDIC_TOOL = {
    "name": "consult_medic",
    "description": (
        "Befragt den Sportmediziner zu einer akuten muskuloskelettalen "
        "Beschwerde (Wade, Knie, Achillessehne, Muskelkater) — liefert ein "
        "echtes Belastungsurteil pro geplanter Sportart, keine Vermutung. Fülle "
        "nur Felder, die der Athlet im Gespräch tatsächlich erwähnt hat; alles "
        "andere weglassen." + _CONSULT_HINWEIS
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "waden": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Wadenbeschwerden, 0-10."},
            "knie": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Kniebeschwerden, 0-10."},
            "achilles_l": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Achillessehne links, 0-10."},
            "achilles_r": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Achillessehne rechts, 0-10."},
            "muedigkeit": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Allgemeine Müdigkeit, 1-5."},
            "muskelkater": {"type": "string", "description": "Freitext, z.B. 'Beine stark' oder 'Oberkörper'."},
        },
    },
}

CONSULT_ALLGEMEINMEDIC_TOOL = {
    "name": "consult_allgemeinmedic",
    "description": (
        "Befragt den Allgemeinmediziner zu Krankheit, Fieber, Blutdruck oder "
        "Medikamenten — liefert ein echtes Belastungsurteil, keine Vermutung. "
        "Fülle nur Felder, die der Athlet erwähnt hat." + _CONSULT_HINWEIS
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symptome": {
                "type": "string",
                "description": "Freitext der genannten Krankheitssymptome, z.B. 'Halsschmerzen, neu seit heute'.",
            },
            "fieber": {"type": "number", "description": "Gemessene Temperatur in °C, falls genannt."},
            "blutdruck_sys": {"type": "integer", "description": "Systolischer Blutdruck, falls genannt."},
            "blutdruck_dia": {"type": "integer", "description": "Diastolischer Blutdruck, falls genannt."},
            "medikamente": {"type": "string", "description": "Genannte Medikamente, falls relevant."},
        },
    },
}

CONSULT_WEATHER_TOOL = {
    "name": "consult_weather",
    "description": (
        "Befragt den Wetter-Taktiker für eine konkrete taktische Empfehlung "
        "(Zeitfenster, Indoor-Wechsel, Ausrüstung) — mehr als die reinen "
        "Wetterdaten im Kontext oben. Nutze das für Fragen wie 'soll ich das "
        "heute lieber drinnen fahren?', nicht für reine Wetterfragen, die der "
        "Kontext oben schon beantwortet." + _CONSULT_HINWEIS
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "ISO-Datum (YYYY-MM-DD), für das die Taktik gefragt ist — heute oder morgen.",
            },
            "frage_fokus": {
                "type": "string",
                "description": "Worauf es dem Athleten ankommt, z.B. 'lange Radausfahrt bei Regen'.",
            },
        },
        "required": ["date"],
    },
}

CONSULT_PERIODIZER_TOOL = {
    "name": "consult_periodizer",
    "description": (
        "Befragt den Periodisierer zur aktuellen Trainings-/Belastungslage "
        "(Phase, Rolle des heutigen Tages, Spielraum für mehr/weniger) — nutzt "
        "die bereits geladene Belastungslage und den Wochenplan, braucht keine "
        "Angaben vom Athleten. Für Fragen wie 'bin ich gerade im Loch?' oder "
        "'kann ich noch eine harte Einheit dranhängen?'." + _CONSULT_HINWEIS
    ),
    "input_schema": {"type": "object", "properties": {}},
}

CONSULT_FUELING_TOOL = {
    "name": "consult_fueling",
    "description": (
        "Befragt den Ernährungsberater zu einer KONKRETEN, bereits im "
        "TrainingPeaks-Plan stehenden Einheit — z.B. wie die Verpflegung bei "
        "Hitze oder auf einer langen Ausfahrt angepasst werden sollte. Für "
        "allgemeine Fragen zur Ernährungstabelle antworte direkt aus dem "
        "Kontext oben, ohne dieses Tool. Rate niemals eine workout_id — date + "
        "workout_hint reichen, der Server findet die Einheit selbst."
        + _CONSULT_HINWEIS
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "ISO-Datum (YYYY-MM-DD) der Einheit, wie im TrainingPeaks-Plan oben.",
            },
            "workout_hint": {
                "type": "string",
                "description": "Sportart oder Titel-Ausschnitt, wörtlich aus der Plan-Zeile kopiert.",
            },
        },
        "required": ["date", "workout_hint"],
    },
}

CONSULT_TOOLS = [
    CONSULT_MEDIC_TOOL, CONSULT_ALLGEMEINMEDIC_TOOL, CONSULT_WEATHER_TOOL,
    CONSULT_PERIODIZER_TOOL, CONSULT_FUELING_TOOL,
]
CONSULT_TOOL_NAMES = {t["name"] for t in CONSULT_TOOLS}


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
        consult_executor: Optional[Callable[[str, dict], dict]] = None,
        model: str = HAIKU, max_tokens: int = 1500) -> dict:
    """Gibt {"text": str, "tool_call": {"name","input"}|None} zurück — der
    Aufrufer (app.py) entscheidet, ob/wie er aus einem propose_*-Tool-Call eine
    pending action baut. Der Chat selbst führt nie etwas Schreibendes aus.

    Ist consult_executor gesetzt, bekommt Claude zusätzlich die CONSULT_TOOLS
    und ein echter Spezialisten-Aufruf kann in derselben Antwort ausgeführt
    und zurückgespielt werden (call_agent_with_consult). Ohne consult_executor
    (Default) bleibt exakt das alte Ein-Call-Verhalten erhalten."""
    system = load_prompt("chat", path=_PROMPT_PATH)
    if kontext:
        system = f"{system}\n\n---\n\n{kontext}"

    messages = []
    for h in (historie or [])[-MAX_HISTORIE:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": nachricht})

    if consult_executor is not None:
        return call_agent_with_consult(
            prompt=system, messages=messages, tools=CHAT_TOOLS + CONSULT_TOOLS,
            consult_tool_names=CONSULT_TOOL_NAMES, executor=consult_executor,
            model=model, max_tokens=max_tokens, label="chat",
        )
    return call_agent_with_tools(prompt=system, messages=messages, tools=CHAT_TOOLS,
                                 model=model, max_tokens=max_tokens, label="chat")
