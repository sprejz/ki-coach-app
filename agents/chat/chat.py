"""Coach-Chat — freies Gespräch mit Zugriff auf Plan, Wetter und Belastung.

Der einzige Agent ohne Schema: die Antwort geht direkt an den Athleten, nicht
an ein weiterverarbeitendes System. Der Kontext wird deterministisch gebaut —
was nicht drinsteht, hat der Coach nicht, und das sagt der Prompt ihm auch.
"""
import logging
from typing import Optional

from ..base import HAIKU, call_agent_text, load_prompt

logger = logging.getLogger(__name__)

MAX_HISTORIE = 10


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
        model: str = HAIKU, max_tokens: int = 1500) -> str:
    system = load_prompt("chat")
    if kontext:
        system = f"{system}\n\n---\n\n{kontext}"

    messages = []
    for h in (historie or [])[-MAX_HISTORIE:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": nachricht})

    return call_agent_text(prompt=system, messages=messages, model=model,
                           max_tokens=max_tokens, label="chat")
