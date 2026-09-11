"""Prüft die Verdrahtung der Agent-Pipeline in app.py — ohne API-Calls.

Die drei Agents werden durch Attrappen ersetzt, die die Eingaben mitschreiben.
Damit lässt sich prüfen, ob die Fragebogenwerte korrekt ankommen, ob der
Fallback greift und ob die Antwort die Form hat, die das Frontend erwartet.

    .venv/bin/python -m tests.test_wiring
"""
import asyncio
import inspect
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from fastapi import HTTPException  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["COACH_AGENTS"] = "1"
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-fuer-test")

import agents.allgemeinmedic as allgemeinmedic  # noqa: E402
import agents.base as base_agent  # noqa: E402
import agents.chat.chat as chat_agent  # noqa: E402
import agents.architect as architect  # noqa: E402
import agents.architect_bike as architect_bike  # noqa: E402
import agents.architect_run as architect_run  # noqa: E402
import agents.architect_swim as architect_swim  # noqa: E402
import agents.fueling as fueling  # noqa: E402
import agents.head_coach as head_coach  # noqa: E402
import agents.medic as medic  # noqa: E402
import agents.periodizer as periodizer  # noqa: E402
import agents.research as research_agent  # noqa: E402
import agents.weather as weather  # noqa: E402
import knowledge  # noqa: E402
import youtube  # noqa: E402
import app  # noqa: E402
import orchestrator  # noqa: E402
from translations import TRANSLATIONS  # noqa: E402
from tests import fixtures as fx  # noqa: E402

fehler = []
mitschrieb = {}


def pruefe(bedingung, text):
    print(f"  {'ok   ' if bedingung else 'FEHLT'} {text}")
    if not bedingung:
        fehler.append(text)


FAKE_MEDIC = {
    "sportarten": [{"sport": "Laufen", "urteil": "stop", "grund": "Achilles rechts 5/10"}],
    "alternativen": ["Aquajogging"], "erholung": "HRV im Rahmen",
}
FAKE_ALLGEMEIN_FREI = {
    "gesamturteil": "frei", "leitbefund": "", "sportarten": [],
    "alternativen": [], "hinweis_chronisch": "",
}
FAKE_ALLGEMEIN_PAUSE = {
    "gesamturteil": "pause", "leitbefund": "Fieber 38.9°C",
    "sportarten": [{"sport": "Laufen", "urteil": "stop", "grund": "Fieber 38.9°C"}],
    "alternativen": [], "hinweis_chronisch": "",
}
FAKE_WETTER = {
    "gesamtlage": "anpassen", "hinweis": "31 °C, sonnig",
    "sportarten": [{"sport": "Laufen", "empfehlung": "zeitfenster",
                    "anpassung": "Pace 5 % langsamer", "zeitfenster": "vor 09:00"}],
    "versorgung": "750 ml/h",
}
FAKE_COACH = {
    "status": "orange", "status_text": "Angepasst",
    "sportarten": [
        {"sport": "Laufen", "badge": "MOD", "details": "Kürzer, kein Tempo",
         "begruendung": "Achilles rechts 5/10",
         "anpassung": {"dauer_min": 40, "zone": "Z2", "kein_tempo": True,
                       "indoor": False, "sportwechsel": None, "hinweis": ""}},
        {"sport": "Rad", "badge": "GO", "details": "Läuft wie geplant",
         "begruendung": "",
         "anpassung": {"dauer_min": None, "zone": "", "kein_tempo": False,
                       "indoor": False, "sportwechsel": None, "hinweis": ""}},
    ],
    "autosleep_summary": None, "wetter_hinweis": "31 °C", "prep": "Früh schlafen",
}
FAKE_ARCHITEKT = {
    "beschreibung": "STOP-Ausweich-Text (Kraft/Sonstiges-Fallback)",
    "dauer_min": 30, "tp_struktur": None, "distanz_m": None,
}
FAKE_ARCHITEKT_RUN = {
    "beschreibung": "40 min ganz locker (6:30–7:05/km)\nHITZE: 750ml/h",
    "dauer_min": 40, "tp_struktur": None, "distanz_m": None,
}
FAKE_ARCHITEKT_BIKE = {
    "beschreibung": "60 min Z2 auf der Rolle, 85-95 rpm",
    "dauer_min": 60, "tp_struktur": None, "distanz_m": None,
}
FAKE_ARCHITEKT_SWIM = {
    "beschreibung": "Gesamt: ~1500m\n20×75m Technik, 15s Pause",
    "dauer_min": 35, "tp_struktur": None, "distanz_m": 1500,
}
FAKE_FUELING_HITZE = fx.FAKE_FUELING_HITZE
FAKE_FUELING_LEER = fx.FAKE_FUELING_LEER
FAKE_BLOCK = {
    "phase": "aufbau", "wochenintention": "Schwellenblock, zweite Woche",
    "heute_rolle": "schluesseleinheit", "heute_begruendung": "einzige Intensität der Woche",
    "belastungsurteil": "grenzwertig", "spielraum": "zuruecknehmen",
    "hinweis": "Ramp Rate 9.4, TSB -34.6", "warnung": "Ramp Rate über 7",
}
FAKE_RESEARCH = {
    "zusammenfassung": "Multiple-transportable-carbohydrate-Mischungen verbessern die Verträglichkeit.",
    "erkenntnisse": [
        {"titel": "Glukose+Fruktose bei Ultradistanz", "aussage": "Über 90g/h profitieren Mischungen "
         "aus Glukose und Fruktose von besserer Verträglichkeit als reine Glukose.",
         "quelle": "https://example.org/study", "konfidenz": "hoch", "betrifft": "Ernährung"},
        {"titel": "Einzelstudie zu Koffein-Timing", "aussage": "Eine kleine Studie deutet auf einen "
         "Vorteil von Koffein 60min vor dem Start hin, Evidenz ist aber dünn.",
         "quelle": "https://example.org/study2", "konfidenz": "mittel", "betrifft": "Ernährung"},
    ],
}
FAKE_VIDEO_RESEARCH = {
    "zusammenfassung": "Der Podcast nennt eine Zahl zum Tapering, die sich per Suche bestätigen ließ.",
    "erkenntnisse": [
        {"titel": "Tapering-Dauer laut Podcast", "aussage": "Der Gast empfiehlt 10-14 Tage Tapering vor "
         "einer Langdistanz, was sich mit einer gefundenen Übersichtsarbeit deckt.",
         "quelle": "https://example.org/tapering-review", "konfidenz": "mittel", "betrifft": "Tapering"},
    ],
}


def attrappe(name, antwort):
    def _run(**kwargs):
        mitschrieb.setdefault(name, []).append(kwargs)
        mitschrieb[name + "_last"] = kwargs
        return antwort
    return _run


class _FakeRequest:
    """Attrappe für Request — coach_chat liest nur await .json()."""
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


medic.run = attrappe("medic", FAKE_MEDIC)
weather.run = attrappe("weather", FAKE_WETTER)
allgemeinmedic.run = attrappe("allgemeinmedic", FAKE_ALLGEMEIN_FREI)
head_coach.run = attrappe("head_coach", FAKE_COACH)
architect.run = attrappe("architect", FAKE_ARCHITEKT)
architect_run.run = attrappe("architect_run", FAKE_ARCHITEKT_RUN)
architect_bike.run = attrappe("architect_bike", FAKE_ARCHITEKT_BIKE)
architect_swim.run = attrappe("architect_swim", FAKE_ARCHITEKT_SWIM)
periodizer.run = attrappe("periodizer", FAKE_BLOCK)
fueling.run = attrappe("fueling", FAKE_FUELING_HITZE)
research_agent.run = attrappe("research", FAKE_RESEARCH)
research_agent.run_video = attrappe("research_video", FAKE_VIDEO_RESEARCH)
# Der Orchestrator hat die Module beim Import gebunden — Attrappen nachziehen.
orchestrator.medic, orchestrator.weather = medic, weather
orchestrator.allgemeinmedic = allgemeinmedic
orchestrator.head_coach, orchestrator.architect = head_coach, architect
orchestrator.periodizer = periodizer
orchestrator.fueling = fueling
# _ARCHITECT_BY_SPORT wurde beim Import von orchestrator.py mit den ECHTEN
# run-Funktionen befüllt (Dict-Werte sind Funktionsobjekte, kein Modul-Lookup
# zur Laufzeit) — die obigen architect_*.run = attrappe(...)-Zuweisungen
# ändern die bereits im Dict gespeicherten Referenzen nicht mehr. Ohne diesen
# Rebuild würde jeder MOD-Aufruf für Laufen/Rad/Schwimmen an der Attrappe
# vorbei die echte Anthropic-API treffen.
orchestrator._ARCHITECT_BY_SPORT = {
    "Laufen": architect_run.run, "Rad": architect_bike.run, "Schwimmen": architect_swim.run,
}

# Kein TP-MCP im Test: Belastungsdaten werden direkt eingespeist.
app._fetch_training_load = lambda athlete: asyncio.sleep(
    0, result=(fx.LOAD_UEBERLASTET, fx.WOCHE_MIT_SCHLUESSELEINHEIT)
)


async def main():
    print("\n=== Abend-Check über die Agent-Pipeline ===")
    ergebnis = await app._try_agent_check(
        athlete={"name": "Hendrik", "swim_outdoor_min_celsius": 15,
                 "ftp_watt": 286,
                 "nutrition": {"rules": [
                     {"duration_min_min": 0, "duration_max_min": 60, "during": "Wasser reicht"},
                     {"duration_min_min": 60, "duration_max_min": 180, "during": "90g Carbs/h"},
                 ]},
                 "races": [{"name": "Malbork", "date": "2099-09-06", "priority": "A",
                            "goal_total": "10:50"}],
                 "chronische_befunde": "keine"},
        baseline={"SchlafHRV": {"median": 35, "flag_low": 29}},
        weather={"description": "Sonnig", "temp_max": 31.0, "temp_min": 19.0,
                 "rain_prob": 5, "is_hot": True},
        koerper={"waden": 4, "knie": 1, "achilles_l": 1, "achilles_r": 5,
                 "muedigkeit": 3, "muskelkater": ["Beine leicht"], "symptome": "keine",
                 "geplante_einheiten": ["Run"]},
        tp_workouts=[
            {"id": "1", "sport": "Run", "title": "Schwellenlauf",
             "duration_min": 60, "description": "4×8min @ 5:20"},
            {"id": "2", "sport": "Bike", "title": "GA1 Rad",
             "duration_min": 120, "description": "2h Z2, 117-130 bpm"},
        ],
        sleep=None, wasser_temp=None, tag="morgen, 26.07.2026",
    )

    pruefe(ergebnis is not None, "Pipeline liefert ein Ergebnis")
    pruefe(ergebnis.get("_pipeline") == "agents", "Antwort ist als Agent-Pfad markiert")
    pruefe(ergebnis.get("weather", {}).get("temp_max") == 31.0, "Wetter hängt an der Antwort")

    print("\n=== Periodisierer ===")
    p = mitschrieb["periodizer_last"]
    pruefe(p["load"]["ramp_7d"] == 9.4, "Periodisierer bekommt die Belastungskennzahlen")
    pruefe(len(p["woche"]) == 7, "Periodisierer bekommt die ganze Woche")
    pruefe(p["tage_bis_a"] is not None, "Periodisierer bekommt den Abstand zum A-Rennen")
    h_block = mitschrieb["head_coach_last"]["block"]
    pruefe(h_block == FAKE_BLOCK, "Chefcoach bekommt den Blockkontext")
    pruefe(ergebnis["_agents"]["block"]["spielraum"] == "zuruecknehmen",
           "Blockurteil hängt am Ergebnis (für Debugging sichtbar)")

    print("\n=== Architekt läuft nur für MOD ===")
    pruefe(len(mitschrieb.get("architect_run", [])) == 1,
           "Genau ein Architekt-Aufruf bei 1× MOD + 1× GO — dispatcht an architect_run (Laufen)")
    pruefe(not mitschrieb.get("architect"),
           "Der generische Fallback (architect) läuft NICHT für Laufen — dafür gibt es architect_run")
    a = mitschrieb["architect_run_last"]
    pruefe(a["auftrag"]["anpassung"]["dauer_min"] == 40, "Architekt bekommt die Zieldauer 40")
    pruefe(a["auftrag"]["begruendung"] == "Achilles rechts 5/10", "Architekt bekommt die Begründung")
    pruefe(a["workout"]["title"] == "Schwellenlauf", "Architekt bekommt das RICHTIGE Workout (Index-Zuordnung)")
    pruefe("31.0 °C" in a["wetter_zeile"], "Architekt bekommt die Wetterzeile")
    pruefe(a["sport"] == "Laufen", "Architekt bekommt weiterhin sport= mitgegeben (einheitliche Aufrufsignatur)")

    lauf, rad = ergebnis["sportarten"]
    pruefe(lauf["beschreibung"].startswith("40 min ganz locker"), "MOD nutzt den Architekten-Text")
    pruefe(rad["beschreibung"] == "2h Z2, 117-130 bpm", "GO übernimmt das Original ZEICHENGENAU")
    # Hitze (is_hot=True) triggert den Ernährungsberater — Basiszahlen bleiben
    # erhalten, der Fueling-Hinweis wird nur angehängt.
    pruefe(lauf["ernaehrung"].startswith("Während: Wasser reicht"),
           "MOD: Ernährung nach neuer Dauer (40 min), Basis erhalten")
    pruefe(rad["ernaehrung"].startswith("Während: 90g Carbs/h"),
           "GO: Ernährung nach Originaldauer (120 min), Basis erhalten")
    pruefe(" — " in lauf["ernaehrung"] and " — " in rad["ernaehrung"],
           "Bei Hitze wird der Fueling-Hinweis an beide Einheiten angehängt")
    pruefe(len(mitschrieb.get("fueling", [])) == 2,
           "Ernährungsberater läuft für beide Einheiten (GO und MOD) bei Hitze")
    pruefe(lauf["ernaehrung_von_berater"] is True and rad["ernaehrung_von_berater"] is True,
           "ernaehrung_von_berater ist explizit gesetzt, statt am Text zu raten")
    pruefe(ergebnis["_chefcoach_ran"] is True, "_chefcoach_ran ist True im Normalpfad")

    print("\n=== Architekt-Dispatch: jede Disziplin an ihren eigenen Agenten (v2.7.12) ===")
    # Direkter Test von _baue_einheit statt über den ganzen Chefcoach-Pfad —
    # damit lässt sich für alle drei Disziplinen + den Kraft/Sonstiges-
    # Fallback in einem Rutsch belegen, dass _ARCHITECT_BY_SPORT tatsächlich
    # an den richtigen Agenten dispatcht und nicht z.B. immer denselben trifft.
    for sport, erwartete_beschreibung in (
        ("Laufen", FAKE_ARCHITEKT_RUN["beschreibung"]),
        ("Rad", FAKE_ARCHITEKT_BIKE["beschreibung"]),
        ("Schwimmen", FAKE_ARCHITEKT_SWIM["beschreibung"]),
        ("Kraft", FAKE_ARCHITEKT["beschreibung"]),
    ):
        eintrag = await orchestrator._baue_einheit(
            entscheidung={"sport": sport, "badge": "MOD", "details": "Test",
                          "begruendung": "Testauftrag", "anpassung": {}},
            workout={"sport": sport, "description": "Original", "duration_min": 45},
            athlete={"nutrition": {"rules": []}}, wetter_zeile="Sonnig", model="egal",
        )
        pruefe(eintrag["beschreibung"] == erwartete_beschreibung,
               f"{sport}: _baue_einheit dispatcht an den richtigen Architekt-Agenten")
    pruefe(len(mitschrieb.get("architect_run", [])) == 2,
           "architect_run wurde jetzt zweimal aufgerufen (Normalpfad oben + Dispatch-Test hier)")
    pruefe(len(mitschrieb.get("architect_bike", [])) == 1, "architect_bike genau einmal aufgerufen")
    pruefe(len(mitschrieb.get("architect_swim", [])) == 1, "architect_swim genau einmal aufgerufen")
    pruefe(len(mitschrieb.get("architect", [])) == 1,
           "architect (Fallback) läuft nur für Kraft — kein einziges Mal für Laufen/Rad/Schwimmen")

    # v2.7.15: Das Chefcoach-Schema lässt für "sport" jeden String zu. Der
    # Dispatch war ein Exact-Match darauf, also landete "Run" oder auch nur
    # "Laufen " mit Leerzeichen beim Kraft/Sonstiges-Architekten — im Frontend
    # sichtbar als "Coach Lea Fromm" über einer Laufeinheit.
    for roh in ("Run", "Lauf", "laufen", "Laufen (LIT)", "Laufen ", "running"):
        eintrag = await orchestrator._baue_einheit(
            entscheidung={"sport": roh, "badge": "MOD", "details": "T",
                          "begruendung": "T", "anpassung": {}},
            workout={"sport": roh, "description": "Original", "duration_min": 45},
            athlete={"nutrition": {"rules": []}}, wetter_zeile="Sonnig", model="egal",
        )
        pruefe(eintrag["beschreibung"] == FAKE_ARCHITEKT_RUN["beschreibung"],
               f"{roh!r} landet beim Laufcoach, nicht beim Kraft/Sonstiges-Fallback")
        pruefe(eintrag["architekt"] == "architect_run",
               f"{roh!r}: der Vertrag nennt den Agenten, der wirklich gelaufen ist")
        pruefe(eintrag["sport"] == "Laufen",
               f"{roh!r}: angezeigt wird die bekannte Disziplin, nicht der Rohtext des Chefcoachs")
    pruefe(len(mitschrieb.get("architect", [])) == 1,
           "der Kraft/Sonstiges-Fallback wurde durch die sechs Schreibweisen kein weiteres Mal gerufen")

    # Unbekannte Sportarten dürfen nicht zu "Sonstiges" verarmen — die Karte
    # soll "Golf" zeigen, auch wenn der Kraft/Sonstiges-Architekt schreibt.
    eintrag = await orchestrator._baue_einheit(
        entscheidung={"sport": "Golf", "badge": "MOD", "details": "T",
                      "begruendung": "T", "anpassung": {}},
        workout={"sport": "Golf", "description": "Original", "duration_min": 45},
        athlete={"nutrition": {"rules": []}}, wetter_zeile="Sonnig", model="egal",
    )
    pruefe(eintrag["sport"] == "Golf" and eintrag["architekt"] == "architect",
           "Golf bleibt 'Golf' auf der Karte und geht an den Kraft/Sonstiges-Architekten")

    # Ohne Architekt darf auch kein Architekt drüberstehen (GO/SKIP, Monolith).
    for badge in ("GO", "SKIP"):
        eintrag = await orchestrator._baue_einheit(
            entscheidung={"sport": "Laufen", "badge": badge, "details": "T",
                          "begruendung": "T", "anpassung": {}},
            workout={"sport": "Run", "description": "Original", "duration_min": 45},
            athlete={"nutrition": {"rules": []}}, wetter_zeile="Sonnig", model="egal",
        )
        pruefe(eintrag["architekt"] is None,
               f"{badge}: kein Architekt gelaufen → keine Zuschreibung im Vertrag")
    _idx = (Path(__file__).parent.parent / "templates" / "index.html").read_text(encoding="utf-8")
    pruefe("ARCHITEKT_SPORT_KEY" not in _idx and "agentTag(s.architekt)" in _idx,
           "Frontend nennt den Architekten aus s.architekt statt ihn aus der Sportart zu raten")
    # v2.7.16: Bei GO schreibt kein Modell — statt einer leeren Zeile die
    # Herkunft des Textes nennen.
    pruefe("T.plan_original" in _idx and "s.badge === 'GO' && s.beschreibung" in _idx,
           "GO-Karten weisen den Originalplan aus TrainingPeaks aus")
    for lang in ("de", "en"):
        pruefe(bool(TRANSLATIONS[lang].get("plan_original")),
               f"plan_original ist in translations.py gepflegt ({lang})")

    # v2.7.20: Die Ernährungszeile stand ohne Urheber da. Anna Feld nur, wenn
    # sie wirklich etwas beigesteuert hat — sonst die Tabelle als Quelle.
    pruefe("T.nutrition_basis" in _idx and "s.ernaehrung_von_berater" in _idx,
           "Ernährungszeile weist ihre Herkunft aus: Anna Feld oder die Tabelle")
    for lang in ("de", "en"):
        pruefe(bool(TRANSLATIONS[lang].get("nutrition_basis")),
               f"nutrition_basis ist in translations.py gepflegt ({lang})")
    pruefe('op.get("ernaehrung")' in inspect.getsource(app.tp_apply)
           and "ERNÄHRUNG:" in inspect.getsource(app.tp_apply),
           "der Trotzdem-Pfad schreibt die Ernährung mit nach TrainingPeaks")

    # v2.7.21: eigener Ernährungs-Tab. Info ist ins Profil gewandert, damit die
    # Leiste bei sieben Buttons bleibt (11px, sonst bricht die Beschriftung).
    print("\n=== Ernährungs-Tab (v2.7.21) ===")
    pruefe(hasattr(app, "api_nutrition"), "Endpunkt /api/nutrition existiert")
    quelle_ep = inspect.getsource(app.api_nutrition)
    pruefe("anthropic" not in quelle_ep and "call_claude" not in quelle_ep,
           "der Tab rechnet deterministisch — kein Claude-Call")
    pruefe('data-tab="ernaehrung"' in _idx and 'data-panel="ernaehrung"' in _idx,
           "Tab-Button und Panel sind verdrahtet")
    # v2.9.3: die Sieben-Tabs-Grenze ist aufgehoben — .tabs scrollt jetzt
    # horizontal statt Labels zu quetschen, ein achter Tab (Recherche) bricht
    # die Beschriftung deshalb nicht mehr. Zähler bewusst nicht mehr auf einen
    # exakten Wert gepinnt (das würde beim nächsten Tab wieder brechen),
    # sondern nur noch geprüft, dass die Leiste tatsächlich scrollt.
    pruefe(_idx.count('class="tab-btn') == 8,
           "acht Tabs (Recherche als eigener Tab seit v2.9.3)")
    pruefe("overflow-x: auto" in _idx and ".tabs::-webkit-scrollbar" in _idx,
           "die Tab-Leiste scrollt horizontal statt Labels zu quetschen")
    # Reihenfolge: der Tab gehört neben die Checks, nicht ans Ende (v2.7.22).
    _reihenfolge = re.findall(r'class="tab-btn[^"]*" data-tab="(\w+)"', _idx)
    pruefe(_reihenfolge[:3] == ["morgen", "abend", "ernaehrung"],
           f"Fueling steht direkt hinter dem Abend-Tab: {_reihenfolge}")
    pruefe('data-tab="about"' not in _idx and 'data-panel="about"' not in _idx,
           "der About-Tab ist weg")
    pruefe('id="about-version"' in _idx and 'id="about-agents"' in _idx,
           "…seine Inhalte sind aber erhalten (jetzt im Profil)")
    _profil = _idx[_idx.index('data-panel="einstellungen"'):_idx.index("<!-- Einstellungen panel -->")]
    pruefe('id="about-version"' in _profil,
           "Version und Pipeline-Status stehen im Profil-Panel")
    pruefe("loadErnaehrung" in _idx and "T.ernaehrung_quelle" in _idx,
           "der Tab lädt beim Öffnen und weist die Herkunft der Dauer aus")
    # v2.7.25: Kraft/Schwimmen bleiben sichtbar, aber grau und ohne Detail —
    # der Tag soll vollständig sein, ohne leere Hinweiszeilen.
    pruefe("kein_bedarf" in quelle_ep,
           "der Endpunkt markiert Einheiten ohne Verpflegungsbedarf, statt sie zu verschweigen")
    pruefe("w.kein_bedarf" in _idx and "ern-ohne-bedarf" in _idx,
           "das Frontend stellt sie grau und ohne aufklappbares Detail dar")
    for lang in ("de", "en"):
        pruefe(bool(TRANSLATIONS[lang].get("ernaehrung_kein_bedarf")),
               f"ernaehrung_kein_bedarf ist gepflegt ({lang})")
    for lang in ("de", "en"):
        pruefe(all(TRANSLATIONS[lang].get(k) for k in
                   ("tab_ernaehrung", "sec_ernaehrung", "ernaehrung_quelle",
                    "ernaehrung_flaschen", "ernaehrung_keine")),
               f"alle Ernährungs-Texte sind gepflegt ({lang})")

    # v2.7.17: fetch() ohne Timeout konnte beim Netzwechsel oder einem
    # Container-Neustart ewig offen bleiben. Die 5-Minuten-Deadline wird nur
    # zwischen zwei Runden geprüft und griff deshalb nie — der Spinner drehte
    # endlos, ohne Fehlermeldung.
    check_js = _idx[_idx.index("async function runCheck"):_idx.index("function showError")]
    pruefe("await fetch(" not in check_js and check_js.count("fetchMitFrist(") >= 2,
           "runCheck nutzt ausschließlich fetch mit Frist — kein nackter fetch mehr")
    pruefe("new AbortController()" in _idx and "ctrl.abort()" in _idx,
           "Die Frist wird über AbortController durchgesetzt")
    pruefe("fehlerInFolge" in check_js and "CHECK_MAX_FEHLER" in check_js,
           "Ein einzelner Netzfehler wirft den laufenden Job nicht weg (Retry-Zähler)")
    pruefe("sr.status === 404" in check_js,
           "404 bleibt ein harter Abbruch — der Job existiert wirklich nicht mehr")
    # v2.8: eigene Fehleranzeige pro Check statt des globalen Banners — auf
    # Desktop laufen Morgen und Abend evtl. gleichzeitig, ein gemeinsamer
    # Banner würde sich überschreiben. showCheckError() hat keinen 8s-Timer
    # (bleibt stehen bis zum nächsten Check-Start) und ist per Klick schließbar
    # — dasselbe Prinzip wie das alte showError(..., bleibt=true).
    pruefe("showCheckError('abend'," in _idx and "showCheckError('morgen'," in _idx,
           "Abend- und Morgen-Check zeigen ihren Fehler in ihrer eigenen Anzeige")
    check_error_js = _idx[_idx.index("function showCheckError"):_idx.index("function showCheckError") + 400]
    pruefe("setTimeout" not in check_error_js and "el.onclick" in check_error_js,
           "Abend- und Morgen-Check zeigen ihren Fehler dauerhaft statt ihn nach 8 s zu verstecken")

    print("\n=== Eingaben kommen bei den Agents an ===")
    m = mitschrieb["medic_last"]
    pruefe(m["koerper"]["achilles_r"] == 5, "Mediziner bekommt Achilles rechts = 5")
    pruefe(m["koerper"]["waden"] == 4, "Mediziner bekommt Waden = 4")
    pruefe(m["sportarten"] == ["Laufen", "Rad"], "Sportarten normalisiert: Run→Laufen, Bike→Rad")
    pruefe(m["baseline"] is not None, "Mediziner bekommt die Baseline")

    w = mitschrieb["weather_last"]
    pruefe(w["weather"]["is_hot"] is True, "Wetter-Taktiker bekommt das Hitze-Flag")
    pruefe(w["titel"] == ["Schwellenlauf", "GA1 Rad"], "Wetter-Taktiker bekommt die Workout-Titel")
    pruefe(w["swim_min_c"] == 15, "Wetter-Taktiker bekommt die Freibad-Grenze")

    h = mitschrieb["head_coach_last"]
    pruefe(h["medic"] == FAKE_MEDIC, "Chefcoach bekommt das Mediziner-Urteil")
    pruefe(h["wetter"] == FAKE_WETTER, "Chefcoach bekommt das Wetter-Urteil")
    pruefe(h["allgemein"] == FAKE_ALLGEMEIN_FREI, "Chefcoach bekommt das Allgemeinmediziner-Urteil")
    pruefe(h["a_race"] and h["a_race"]["name"] == "Malbork", "Chefcoach bekommt das A-Rennen")
    pruefe("achilles_r" not in str(h.get("koerper", "")), "Chefcoach sieht KEINE Rohwerte mehr")

    al = mitschrieb["allgemeinmedic_last"]
    pruefe(al["chronische_befunde"] == "keine", "Allgemeinmediziner bekommt die chronischen Befunde aus dem Profil")
    pruefe(ergebnis["_agents"]["allgemein"] == FAKE_ALLGEMEIN_FREI,
           "Allgemeinmediziner-Urteil hängt am Ergebnis (für Debugging sichtbar)")

    print("\n=== Ohne TP-Belastungsdaten ===")
    mitschrieb.pop("periodizer", None)
    app._fetch_training_load = lambda athlete: asyncio.sleep(0, result=(None, None))
    fueling_calls_vorher = len(mitschrieb.get("fueling", []))
    ohne = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": []}},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20.0},
        koerper={"symptome": "keine"},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf", "duration_min": 40,
                      "description": "40 min locker"}],
        sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(ohne is not None, "Check läuft auch ohne Belastungsdaten durch")
    pruefe("periodizer" not in mitschrieb,
           "Periodisierer wird NICHT aufgerufen, wenn keine Daten da sind")
    pruefe(mitschrieb["head_coach_last"]["block"] is None,
           "Chefcoach bekommt block=None statt erfundener Zahlen")
    pruefe(ohne["_agents"]["block"] is None, "Blockurteil ist None, nicht leer erfunden")
    pruefe(len(mitschrieb.get("fueling", [])) == fueling_calls_vorher,
           "Ernährungsberater läuft NICHT ohne Grund (mildes Wetter, 40min, keine Befunde) — Kostendisziplin")

    print("\n=== Ernährungsberater: Gating ===")
    # Chronischer Befund allein (mildes Wetter, kurze Dauer) muss auch ohne
    # Hitze auslösen.
    fueling.run = attrappe("fueling", FAKE_FUELING_LEER)
    orchestrator.fueling = fueling
    fueling_calls_vorher = len(mitschrieb.get("fueling", []))
    mit_befund = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": [
            {"duration_min_min": 0, "duration_max_min": 60, "during": "Wasser reicht"}]},
            "chronische_befunde": "Reizdarm"},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20.0},
        koerper={"symptome": "keine"},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf", "duration_min": 40,
                      "description": "40 min locker"}],
        sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(mit_befund is not None, "Check läuft mit chronischem Befund durch")
    pruefe(len(mitschrieb.get("fueling", [])) == fueling_calls_vorher + 1,
           "Chronischer Befund allein (ohne Hitze) triggert den Ernährungsberater")
    pruefe(mitschrieb["fueling_last"]["chronische_befunde"] == "Reizdarm",
           "Ernährungsberater bekommt den chronischen Befund")
    pruefe("relevant=false" not in str(mit_befund["sportarten"][0]["ernaehrung"]),
           "relevant=false hängt KEINEN Hinweis an (FAKE_FUELING_LEER)")

    # "keine"/"keine bekannt" sind Platzhalter, kein echter Befund — dürfen
    # den Call nicht auslösen (Regressionsschutz für den Truthy-String-Bug).
    fueling_calls_vorher = len(mitschrieb.get("fueling", []))
    platzhalter = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": [
            {"duration_min_min": 0, "duration_max_min": 60, "during": "Wasser reicht"}]},
            "chronische_befunde": "keine bekannt"},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20.0},
        koerper={"symptome": "keine"},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf", "duration_min": 40,
                      "description": "40 min locker"}],
        sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(platzhalter is not None
           and len(mitschrieb.get("fueling", [])) == fueling_calls_vorher,
           "'keine bekannt' als chronischer Befund triggert NICHT (Platzhalter, kein echter Befund)")

    # Ein Fehler im Ernährungsberater darf den Check nie kippen — anders als
    # bei medic/weather/architect wird das lokal abgefangen.
    def fueling_kaputt(**kwargs):
        raise RuntimeError("simulierter Fueling-Ausfall")
    fueling.run = fueling_kaputt
    orchestrator.fueling = fueling
    trotz_fehler = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": [
            {"duration_min_min": 0, "duration_max_min": 60, "during": "Wasser reicht"}]}},
        baseline=None, weather={"description": "Sonnig", "temp_max": 31.0, "is_hot": True},
        koerper={"symptome": "keine"},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf", "duration_min": 40,
                      "description": "40 min locker"}],
        sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(trotz_fehler is not None and trotz_fehler.get("_pipeline") == "agents",
           "Ein Fueling-Fehler kippt den Check NICHT auf den Monolith-Fallback")
    pruefe(trotz_fehler["sportarten"][0]["ernaehrung"] == "Während: Wasser reicht",
           "Bei Fueling-Fehler bleibt die reine Tabellen-Basis erhalten")
    fueling.run = attrappe("fueling", FAKE_FUELING_HITZE)
    orchestrator.fueling = fueling

    print("\n=== Allgemeinmediziner pause = harter Stop (Sicherheitsregel) ===")
    allgemeinmedic.run = attrappe("allgemeinmedic", FAKE_ALLGEMEIN_PAUSE)
    orchestrator.allgemeinmedic = allgemeinmedic
    head_coach_calls_vorher = len(mitschrieb.get("head_coach", []))
    architekt_module = ("architect", "architect_run", "architect_bike", "architect_swim")
    architect_calls_vorher = {m: len(mitschrieb.get(m, [])) for m in architekt_module}
    pause_ergebnis = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": []}, "chronische_befunde": "keine"},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20.0},
        koerper={"symptome": "keine", "fieber": 38.9, "geplante_einheiten": ["Run", "Bike"]},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf", "duration_min": 40, "description": "Z2"},
                     {"id": "2", "sport": "Bike", "title": "Rad", "duration_min": 60, "description": "Z2"}],
        sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(pause_ergebnis is not None and all(s["badge"] == "SKIP" for s in pause_ergebnis["sportarten"]),
           "gesamturteil=pause erzwingt SKIP für JEDE Sportart, ausnahmslos")
    pruefe(len(mitschrieb.get("head_coach", [])) == head_coach_calls_vorher,
           "Chefcoach wird bei pause NICHT aufgerufen (harter Stop im Code, nicht im Prompt)")
    pruefe(all(len(mitschrieb.get(m, [])) == architect_calls_vorher[m] for m in architekt_module),
           "Architekt (weder Fallback noch Lauf/Rad/Schwimm-Agenten) wird bei pause aufgerufen")
    pruefe(pause_ergebnis["_agents"]["allgemein"]["gesamturteil"] == "pause",
           "Allgemeinmediziner-Urteil hängt sichtbar am Ergebnis")
    pruefe(pause_ergebnis["status"] == "red", "Status ist 'red' bei Pause")
    pruefe(pause_ergebnis["_chefcoach_ran"] is False,
           "_chefcoach_ran ist explizit False bei Pause, statt aus status_text zu raten")
    # Zurück auf 'frei', damit spätere Tests nicht versehentlich kurzgeschlossen werden.
    allgemeinmedic.run = attrappe("allgemeinmedic", FAKE_ALLGEMEIN_FREI)
    orchestrator.allgemeinmedic = allgemeinmedic

    print("\n=== Coach-Chat und Analyst verdrahtet ===")
    import agents.analyst_bike as analyst_bike_mod
    import agents.analyst_run as analyst_run_mod
    import agents.analyst_swim as analyst_swim_mod
    import agents.chat as chat_mod
    pruefe(app.chat_agent is chat_mod, "app.py nutzt den Chat-Agent")
    pruefe(hasattr(app, "_run_analysis_job_agent"), "Analyse-Job über den Agent existiert")

    # v2.7.28: Lauf/Rad/Schwimmen bekommen im Analyse-Tab denselben Disziplin-
    # Coach, der ihre Einheiten auch anpasst — vorher lief für jede Sportart
    # derselbe generische Performance-Analyst (Coach Ben Krause), der über die
    # UI nie erreichbar war (Analyse-Tab zeigt nur Lauf/Rad/Schwimmen) und
    # deshalb ganz entfernt wurde.
    pruefe(app._ANALYST_BY_SPORT.get("Laufen") is analyst_run_mod.run,
           "app.py dispatcht 'Laufen' im Analyse-Tab an analyst_run")
    pruefe(app._ANALYST_BY_SPORT.get("Rad") is analyst_bike_mod.run,
           "app.py dispatcht 'Rad' im Analyse-Tab an analyst_bike")
    pruefe(app._ANALYST_BY_SPORT.get("Schwimmen") is analyst_swim_mod.run,
           "app.py dispatcht 'Schwimmen' im Analyse-Tab an analyst_swim")
    pruefe(app._ANALYST_BY_SPORT.get("Kraft") is None
           and app._ANALYST_BY_SPORT.get("Sonstiges") is None
           and len(app._ANALYST_BY_SPORT) == 3,
           "Kraft/Sonstiges/alles andere haben KEINEN Dispatch-Eintrag — kein generischer Fallback mehr")
    pruefe(not hasattr(app, "analyst"),
           "app.py importiert den generischen Analyst-Agent nicht mehr (entfernt)")
    pruefe(app._ANALYST_AGENT_KEY_BY_SPORT.get("Laufen") == "architect_run"
           and app._ANALYST_AGENT_KEY_BY_SPORT.get("Rad") == "architect_bike"
           and app._ANALYST_AGENT_KEY_BY_SPORT.get("Schwimmen") == "architect_swim",
           "Der Agent-Key für die Anzeige ist derselbe wie beim Architekten (gleicher Coach, gleiche Identität)")

    # Eine nicht unterstützte Sportart wird jetzt vor dem Jobstart klar
    # abgelehnt, statt still auf einen generischen Analysten zu fallen.
    import inspect as _inspect_analyze
    _analyze_quelle = _inspect_analyze.getsource(app.workout_analyze)
    pruefe("err_analysis_sport_unsupported" in _analyze_quelle,
           "workout_analyze lehnt nicht unterstützte Sportarten mit einer klaren Fehlermeldung ab")

    # _run_analysis_job_agent ruft die übergebene analyst_fn auf und markiert
    # das Ergebnis mit dem passenden Agent-Key fürs Frontend.
    _analysis_job_id = "test-analyst-dispatch"
    app._analysis_jobs.pop(_analysis_job_id, None)
    app._run_analysis_job_agent(
        job_id=_analysis_job_id,
        analyst_fn=lambda **kw: {"bewertung": "gut", "urteil": "x", "naechster_schritt": "y",
                                 "datenlage": "nur_plan", "ernaehrung_einschaetzung": ""},
        analyst_agent="architect_run",
        athlete={}, sport="Laufen", titel="Lauf", datum="2026-08-19",
    )
    _job = app._analysis_jobs.get(_analysis_job_id, {})
    pruefe(_job.get("status") == "done" and _job.get("result", {}).get("analyst_agent") == "architect_run",
           "_run_analysis_job_agent trägt den übergebenen analyst_agent-Key ins Ergebnis ein")
    app._analysis_jobs.pop(_analysis_job_id, None)

    # Regression v2.7.1: tomorrow_str war im Monolith-Chatpfad nie definiert.
    # Der NameError landete im except und der Chat bekam immer
    # "Wetterdaten nicht verfügbar". Der Bezeichner muss zugewiesen werden,
    # bevor er im f-String auftaucht.
    quelle = inspect.getsource(app.coach_chat)
    zuweisung = quelle.find("tomorrow_str =")
    verwendung = quelle.find("{tomorrow_str}")
    pruefe(zuweisung != -1, "tomorrow_str wird zugewiesen (war der NameError-Bug)")
    pruefe(zuweisung < verwendung, "tomorrow_str wird VOR der Verwendung zugewiesen")

    # v2.7.13: app.py las die camelCase-Namen der TP-eigenen API, der MCP
    # liefert aber snake_case (Dauern in Stunden, Kennzahlen im Detail unter
    # "metrics"). Die Attrappen unten sind der echte Antwortschnitt des
    # MCP-Servers, abgenommen an tp_get_workouts/tp_get_workout.
    print("\n=== TP-Feldnamen: snake_case wie der MCP sie liefert (v2.7.13) ===")
    LISTE = {"id": "3884239026", "date": "2026-08-05", "title": "Lauf 7x400m HIT",
             "type": "completed", "sport": "Run",
             "duration_planned": 1.5, "duration_actual": 1.0,
             "distance_planned_km": None, "distance_actual_km": 6.65,
             "tss": 56.76, "tss_planned": 62.7, "tss_actual": 56.76,
             "description": "Nicht übertreiben"}
    geplant = app._map_tp_workout(LISTE)
    absolviert = app._map_tp_workout(LISTE, prefer="actual")
    pruefe(geplant["duration_min"] == 90 and geplant["tss"] == 62.7,
           "Planungspfad nimmt die Planwerte und rechnet Stunden in Minuten um")
    pruefe(absolviert["duration_min"] == 60 and absolviert["tss"] == 56.8,
           "History-Pfad nimmt die Ist-Werte (prefer='actual')")
    pruefe(geplant["id"] == "3884239026" and geplant["sport"] == "Run"
           and geplant["_day"] == "2026-08-05",
           "Id, Sportart und Tag kommen aus den MCP-Feldern (id/sport/date)")
    pruefe(app._map_tp_workout({"id": "1", "date": "2026-08-05",
                                "totalTimePlanned": 5400, "tssPlanned": 62.7})["duration_min"] is None,
           "Die alten camelCase-Namen liefern nichts — genau das war der Bug")

    DETAIL = {"id": "3884239026", "date": "2026-08-05", "sport": "Run",
              "workout_type": 3, "description": "Original", "rpe": 6, "feeling": 4,
              "metrics": {"duration_planned": 1.5, "duration_actual": 1.0,
                          "tss_planned": 62.7, "tss_actual": 56.76,
                          "distance_actual_km": 6.65, "avg_power": 204.0,
                          "normalized_power": 235.0, "avg_hr": 132,
                          "avg_cadence": 144.0, "calories": 417}}
    pruefe(app._tp_dauer_min(DETAIL, prefer="planned") == 90,
           "Die Detail-Antwort verschachtelt dieselben Namen unter 'metrics'")
    analyse_prompt = app._build_analysis_prompt(
        athlete={"name": "Hendrik"}, a_race={}, workout_id="3884239026", sport="Run",
        title="Lauf 7x400m HIT", target_date="2026-08-05", fit_data={}, tp_data=DETAIL)
    for erwartet in ("Ø HF Ist: 132", "Ø Leistung Ist (W): 204", "TSS Ist: 56.8",
                     "Dauer Ist (min): 60", "RPE (1–10): 6"):
        pruefe(erwartet in analyse_prompt, f"Monolith-Analyse sieht '{erwartet}'")
    pruefe("TRAININGPEAKS IST-DATEN" in analyse_prompt,
           "Mit HF/Watt gilt die Einheit als absolviert")
    nur_plan = app._build_analysis_prompt(
        athlete={"name": "Hendrik"}, a_race={}, workout_id="1", sport="Run",
        title="X", target_date="2026-08-05", fit_data={},
        tp_data={"metrics": {"duration_planned": 1.5, "tss_planned": 62.7}})
    pruefe("TRAININGPEAKS PLAN-DATEN" in nur_plan,
           "Ohne HF/Watt/Kadenz bleibt es eine Plan-Einheit (duration_planned allein zählt nicht)")

    # v2.7.18: Der Umweg über den Claude-MCP-Connector war komplett tot —
    # _tp_call_sync hatte keinen Aufrufer, und damit hing call_claude_tp_mcp
    # (sein einziger Nutzer) plus der 6-Minuten-HTTP-Client mit am Ast.
    # TP läuft ausschließlich über direktes JSON-RPC (call_tp_mcp).
    print("\n=== Toter Code bleibt entfernt (v2.7.18) ===")
    for name in ("_tp_call_sync", "call_claude_tp_mcp", "_tp_http_long",
                 "_run_analysis_job", "build_pain_rules"):
        pruefe(not hasattr(app, name), f"app.{name} existiert nicht mehr")
    pruefe(hasattr(app, "call_tp_mcp"), "der genutzte JSON-RPC-Pfad ist unangetastet")
    pruefe("tp_workouts_prompt" not in TRANSLATIONS["de"]
           and "tp_workouts_prompt" not in TRANSLATIONS["en"],
           "der nur davon genutzte Prompt ist in beiden Sprachen weg")
    pruefe(not (Path(__file__).parent.parent / "CLAUDE_14.md").exists(),
           "die veraltete Vorgängerspec CLAUDE_14.md ist gelöscht")
    # Gegenprobe: pain_thresholds ist NICHT tot — das Frontend rechnet damit
    # den MOD-Grund für TrainingPeaks aus. Nur der Backend-Prompt nutzte es nie.
    pruefe("pain_thresholds" in (Path(__file__).parent.parent / "athlete.json").read_text(encoding="utf-8"),
           "pain_thresholds bleibt in athlete.json — das Frontend liest es")
    pruefe("athlete?.pain_thresholds" in _idx,
           "buildModReason() liest die Schwellen weiterhin aus dem Profil")

    # v2.7.27: wttr.in meldete am 17.08.2026 „Blizzard, −2 °C" für Brandenburg,
    # die App baute daraus Kälte-Empfehlungen. Open-Meteo ist jetzt Primärquelle,
    # und unplausible Daten werden verworfen statt durchgereicht.
    print("\n=== Wetter: Quelle und Plausibilität (v2.7.27) ===")
    _p = app._wetter_plausibel
    pruefe(_p({"datum": "2026-08-18", "temp_min": -2.0, "temp_max": -2.0, "code": 75}, 52.3),
           "−2 °C im August werden verworfen (der echte wttr.in-Fehler)")
    pruefe(_p({"datum": "2026-08-18", "temp_min": 12.0, "temp_max": 20.0, "code": 75}, 52.3),
           "Schnee-Code bei 20 °C wird verworfen")
    pruefe(_p({"datum": "2026-08-18", "temp_min": 20.0, "temp_max": 10.0, "code": 1}, 52.3),
           "Maximum unter Minimum wird verworfen")
    pruefe(not _p({"datum": "2026-08-18", "temp_min": 12.2, "temp_max": 20.4, "code": 61}, 52.3),
           "echte Open-Meteo-Werte kommen durch")
    pruefe(not _p({"datum": "2026-07-20", "temp_min": 22.0, "temp_max": 38.0, "code": 0}, 52.3)
           and not _p({"datum": "2026-01-20", "temp_min": -12.0, "temp_max": -8.0, "code": 75}, 52.3),
           "echte Extreme (38 °C im Juli, −8 °C im Januar) bleiben gültig")
    pruefe(not _p({"datum": "2026-08-18", "temp_min": -2.0, "temp_max": -2.0, "code": 75}, None),
           "ohne Breitengrad greift die Jahreszeit-Regel nicht — keine Fehlalarme anderswo")
    # Nicht Textpositionen vergleichen (der Docstring nennt wttr.in zuerst),
    # sondern die tatsächliche Reihenfolge der Quellen im Code.
    _wq = inspect.getsource(app.fetch_weather)
    _reihenfolge = re.findall(r'\("(open-meteo|wttr\.in)",\s*_fetch_', _wq)
    pruefe(_reihenfolge == ["open-meteo", "wttr.in"],
           f"Open-Meteo wird vor wttr.in versucht (Reihenfolge: {_reihenfolge})")
    pruefe("quelle" in inspect.getsource(app._wetter_dict),
           "die Antwort nennt ihre Quelle, damit so ein Fehler auffindbar bleibt")

    print("\n=== Fallback bei Agent-Fehler ===")
    def kaputt(**kwargs):
        raise RuntimeError("simulierter Ausfall")
    medic.run = kaputt
    fallback = await app._try_agent_check(
        athlete={"name": "Hendrik", "races": []}, baseline=None,
        weather={"description": "Sonnig"}, koerper={"symptome": "keine"},
        tp_workouts=[], sleep=None, wasser_temp=None, tag="heute",
    )
    pruefe(fallback is None, "Fehler gibt None zurück → Monolith übernimmt")

    print("\n=== Schalter ===")
    os.environ["COACH_AGENTS"] = "0"
    pruefe(app.agents_enabled() is False, "COACH_AGENTS=0 schaltet die Pipeline ab")
    os.environ["COACH_AGENTS"] = "on"
    pruefe(app.agents_enabled() is True, "COACH_AGENTS=on schaltet sie ein")
    del os.environ["COACH_AGENTS"]
    pruefe(app.agents_enabled() is False, "ohne ENV bleibt sie aus (sicherer Default)")

    # v2.7.3: Diagnose ohne Railway-Log. /api/version muss sagen, ob die
    # Pipeline importierbar und eingeschaltet ist, und jede Antwort muss
    # verraten, welcher Pfad sie erzeugt hat.
    print("\n=== Diagnose (v2.7.3) ===")
    _WURZEL = Path(__file__).parent.parent
    _INDEX = (_WURZEL / "templates" / "index.html").read_text(encoding="utf-8")
    _TRANS = (_WURZEL / "translations.py").read_text(encoding="utf-8")
    st = app.agents_status()
    pruefe(set(st) == {"importable", "enabled", "env", "import_error",
                       "anthropic_version"}, "agents_status hat alle Felder")
    pruefe(st["enabled"] is False and st["env"] is None,
           "ohne ENV meldet der Status ehrlich 'aus'")
    os.environ["COACH_AGENTS"] = "1"
    st = app.agents_status()
    pruefe(st["enabled"] is True and st["env"] == "1",
           "mit ENV=1 meldet der Status 'an' und zeigt den Rohwert")
    pruefe(st["importable"] is True and st["import_error"] is None,
           "Pipeline ist importierbar, kein Importfehler")
    version = (await app.api_version())
    pruefe(version.get("agents") == st, "/api/version liefert den Status mit")

    for name, fn in (("check-abend", app._check_abend_run),
                     ("check-morgen", app._check_morgen_run),
                     ("Chat", app.coach_chat),
                     ("Analyse", app._run_analysis_job_fast)):
        quelle = inspect.getsource(fn)
        pruefe('"_pipeline"] = "monolith"' in quelle or '"_pipeline": "monolith"' in quelle,
               f"{name} markiert den Monolith-Pfad")

    pruefe('_pipeline" in data' in _INDEX or "engineNote(data._pipeline)" in _INDEX,
           "Frontend zeigt den benutzten Pfad an")
    pruefe("renderAgentsStatus" in _INDEX, "About-Tab rendert den Pipeline-Status")

    print("\n=== Ernährungsberater: tp/apply nutzt vorgerechneten Wert (v2.8) ===")
    pruefe("ernaehrung:    sportarten[i]?.ernaehrung" in _INDEX,
           "Frontend schickt die berechnete Ernährung mit in die tp/apply-Operation")
    pruefe('op.get("ernaehrung")' in inspect.getsource(app.tp_apply),
           "tp_apply nutzt die vorgerechnete Ernährung statt eines zweiten Claude-Calls")

    print("\n=== Chat schlägt TP-Änderungen vor, führt nie direkt aus (v2.8) ===")
    pruefe(len(chat_agent.CHAT_TOOLS) == 4,
           "genau vier Tools: Einheit anpassen, Notiz anlegen, Einheit streichen, Serie anlegen")
    pruefe({t["name"] for t in chat_agent.CHAT_TOOLS}
           == {"propose_workout_update", "propose_calendar_note",
               "propose_workout_skip", "propose_workout_series"},
           "die Tool-Namen sind die erwarteten")
    for t in chat_agent.CHAT_TOOLS + chat_agent.CONSULT_TOOLS:
        pruefe("workout_id" not in t["input_schema"]["properties"],
               f"{t['name']}: Claude bekommt nie eine workout_id zum Raten angeboten")
        pruefe("anyOf" not in t["input_schema"] and "oneOf" not in t["input_schema"]
               and "allOf" not in t["input_schema"],
               f"{t['name']}: kein oneOf/allOf/anyOf auf oberster Ebene (von Anthropic abgelehnt, v2.8.2)")

    print("\n=== Consult-Tools: fünf Namen, lesend, Root-Schema sauber (v2.9.1) ===")
    pruefe(len(chat_agent.CONSULT_TOOLS) == 5,
           "fünf Consult-Tools: medic, allgemeinmedic, weather, periodizer, fueling")
    pruefe(chat_agent.CONSULT_TOOL_NAMES == {
        "consult_medic", "consult_allgemeinmedic", "consult_weather",
        "consult_periodizer", "consult_fueling",
    }, "die Consult-Tool-Namen sind die erwarteten")

    # _tp_cache direkt befüllen — dieselbe Form wie _map_tp_workout sie liefert.
    app._tp_cache.clear()
    app._tp_cache_set("2026-01-15", {"workouts": [
        {"id": "111", "sport": "Laufen", "title": "Longrun locker"},
    ]})
    app._tp_cache_set("2026-01-16", {"workouts": [
        {"id": "222", "sport": "Rad", "title": "Grundlage"},
        {"id": "333", "sport": "Rad", "title": "Grundlage lang"},
    ]})

    app._pending_tp_actions.clear()
    summary, proposal = app._resolve_workout_update_proposal({
        "date": "2026-01-15", "workout_hint": "Longrun",
        "new_title": "Longrun locker – Regen", "summary": "Ich schlage eine Umbenennung vor.",
    })
    pruefe(proposal is not None and proposal["pending_id"] in app._pending_tp_actions,
           "eindeutiger Treffer legt eine pending action an")
    pruefe(app._pending_tp_actions[proposal["pending_id"]]["workout_id"] == "111",
           "die richtige workout_id wurde server-seitig aufgelöst, nicht von Claude geraten")
    pruefe(summary == "Ich schlage eine Umbenennung vor.",
           "Claudes summary wird wörtlich als Antwort verwendet")

    app._pending_tp_actions.clear()
    _, proposal_mehrdeutig = app._resolve_workout_update_proposal({
        "date": "2026-01-16", "workout_hint": "Rad",
        "new_title": "X", "summary": "…",
    })
    pruefe(proposal_mehrdeutig is None and not app._pending_tp_actions,
           "zwei Treffer am selben Tag → keine pending action, sondern Rückfrage")

    _, proposal_kein_treffer = app._resolve_workout_update_proposal({
        "date": "2026-01-15", "workout_hint": "Schwimmen",
        "new_title": "X", "summary": "…",
    })
    pruefe(proposal_kein_treffer is None,
           "kein Treffer → keine pending action, sondern Rückfrage")

    _, proposal_ohne_aenderung = app._resolve_workout_update_proposal({
        "date": "2026-01-15", "workout_hint": "Longrun", "summary": "…",
    })
    pruefe(proposal_ohne_aenderung is None,
           "weder new_title noch new_description → ungültig, auch ohne API-seitige Schema-Pflicht")

    app._pending_tp_actions.clear()
    _, note_proposal = app._resolve_calendar_note_proposal({
        "date": "2026-01-20", "title": "Krank", "text": "Erkältung, pausiert",
        "summary": "Ich lege eine Notiz an.",
    })
    pruefe(note_proposal is not None and note_proposal["type"] == "calendar_note",
           "Kalendernotiz-Vorschlag wird angelegt")

    # v2.8.3 — "streich die Einheit" darf jetzt vorgeschlagen werden (dieselbe
    # ❌-Titel-Konvention wie SKIP im Check, kein echtes Löschen).
    app._pending_tp_actions.clear()
    _, skip_proposal = app._resolve_workout_skip_proposal({
        "date": "2026-01-15", "workout_hint": "Longrun", "summary": "Ich streiche den Longrun.",
    })
    pruefe(skip_proposal is not None and skip_proposal["type"] == "workout_skip",
           "eindeutiger Treffer legt einen Streich-Vorschlag an")
    pruefe(skip_proposal["new_title"] == app.T["tp_skip_renamed"].format(title="Longrun locker"),
           "derselbe ❌-Titel-Präfix wie SKIP im Abend-/Morgen-Check")
    pruefe(app._pending_tp_actions[skip_proposal["pending_id"]]["workout_id"] == "111",
           "auch hier die server-seitig aufgelöste workout_id, nicht geraten")

    async def _fake_call_tp_mcp(tool_name, arguments):
        mitschrieb.setdefault("call_tp_mcp", []).append((tool_name, arguments))
        return {"id": arguments.get("workout_id", "neu")}
    _orig_call_tp_mcp = app.call_tp_mcp
    app.call_tp_mcp = _fake_call_tp_mcp
    os.environ["TP_MCP_URL"] = "https://example.invalid/mcp"
    try:
        app._pending_tp_actions.clear()
        _, p = app._resolve_workout_update_proposal({
            "date": "2026-01-15", "workout_hint": "Longrun",
            "new_title": "Neuer Titel", "summary": "…",
        })
        result = await app.chat_tp_action_confirm(p["pending_id"])
        pruefe(result["ok"] is True and result["actions"][0]["status"] == "ok",
               "Bestätigen führt tp_update_workout aus")
        pruefe(mitschrieb["call_tp_mcp"][-1] == ("tp_update_workout",
               {"workout_id": "111", "title": "Neuer Titel"}),
               "dieselben Parameter wie tp_apply, keine Extra-Felder")
        pruefe(p["pending_id"] not in app._pending_tp_actions,
               "pop-before-execute: der Eintrag ist danach weg")

        confirm_erneut_fehlgeschlagen = False
        try:
            await app.chat_tp_action_confirm(p["pending_id"])
        except HTTPException as e:
            confirm_erneut_fehlgeschlagen = (e.status_code == 404)
        pruefe(confirm_erneut_fehlgeschlagen,
               "ein zweites Bestätigen desselben Vorschlags kann nicht doppelt anwenden (404)")

        cancel_result = await app.chat_tp_action_cancel("gibt-es-nicht")
        pruefe(cancel_result == {"ok": True, "cancelled": False},
               "Verwerfen eines unbekannten/abgelaufenen Vorschlags ist harmlos (idempotent)")
    finally:
        app.call_tp_mcp = _orig_call_tp_mcp

    # coach_chat-Verdrahtung: chat_agent.run liefert jetzt {"text","tool_call"}.
    # app.chat_agent ist das agents.chat-PAKET (from .chat import * in
    # agents/chat/__init__.py kopiert den Namen beim Import) — das ist ein
    # eigenes Namens-Binding, unabhängig vom agents.chat.chat-Submodul-Import
    # oben. Gepatcht werden muss die Stelle, die app.py wirklich aufruft.
    _orig_chat_run = app.chat_agent.run
    app.chat_agent.run = lambda **kwargs: {
        "text": "", "tool_call": {"name": "propose_workout_update",
                                   "input": {"date": "2026-01-15", "workout_hint": "Longrun",
                                             "new_title": "X", "summary": "Testvorschlag"}},
    }
    try:
        req = _FakeRequest({"message": "Bitte den Longrun umbenennen", "history": []})
        resp = await app.coach_chat(req)
        data = json.loads(resp.body)
        pruefe(data.get("proposal", {}).get("type") == "workout_update"
               and data["reply"] == "Testvorschlag",
               "coach_chat gibt bei einem Tool-Call ein proposal-Feld zurück")
    finally:
        app.chat_agent.run = _orig_chat_run

    print("\n=== propose_workout_series: neue Einheit(en) anlegen (v2.9.1) ===")
    app._pending_tp_actions.clear()
    _, series_ok = app._resolve_workout_series_proposal({
        "workouts": [
            {"date": "2026-02-02", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
            {"date": "2026-02-04", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
            {"date": "2026-02-06", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
        ],
        "summary": "Ich lege drei Rad-Einheiten an.",
    })
    pruefe(series_ok is not None and series_ok["type"] == "workout_series"
           and len(series_ok["workouts"]) == 3,
           "drei gültige Einträge → eine pending action mit drei Workouts")
    pruefe(series_ok["pending_id"] in app._pending_tp_actions,
           "die Serie landet als EIN pending-action-Eintrag")

    app._pending_tp_actions.clear()
    _, series_ungueltig = app._resolve_workout_series_proposal({
        "workouts": [
            {"date": "2026-02-02", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
            {"date": "2026-02-04", "sport": "Rad", "title": "Zu kurz", "duration_minutes": 10},
        ],
        "summary": "…",
    })
    pruefe(series_ungueltig is None and not app._pending_tp_actions,
           "EIN ungültiger Eintrag (Dauer < 20min) verwirft die GANZE Anfrage, kein Teil-Erfolg")

    _, series_leer = app._resolve_workout_series_proposal({"workouts": [], "summary": "…"})
    pruefe(series_leer is None, "leere workouts-Liste ist ungültig")

    async def _fake_call_tp_mcp_series(tool_name, arguments):
        mitschrieb.setdefault("call_tp_mcp_series", []).append((tool_name, arguments))
        if arguments.get("title") == "Grundlage locker" and arguments.get("date") == "2026-02-04":
            raise RuntimeError("TP down")
        return {"id": "neu"}
    app.call_tp_mcp = _fake_call_tp_mcp_series
    os.environ["TP_MCP_URL"] = "https://example.invalid/mcp"
    try:
        app._pending_tp_actions.clear()
        _, series_proposal = app._resolve_workout_series_proposal({
            "workouts": [
                {"date": "2026-02-02", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
                {"date": "2026-02-04", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
                {"date": "2026-02-06", "sport": "Rad", "title": "Grundlage locker", "duration_minutes": 45},
            ],
            "summary": "…",
        })
        result = await app.chat_tp_action_confirm(series_proposal["pending_id"])
        pruefe(len(mitschrieb["call_tp_mcp_series"]) == 3,
               "drei tp_create_workout-Aufrufe, einer pro Einheit")
        pruefe(all(c[0] == "tp_create_workout" for c in mitschrieb["call_tp_mcp_series"]),
               "jeder Aufruf nutzt tp_create_workout")
        stati = [a["status"] for a in result["actions"]]
        pruefe(stati.count("ok") == 2 and stati.count("error") == 1,
               "ein fehlgeschlagenes Workout blockiert die übrigen zwei nicht — kein Alles-oder-nichts")
    finally:
        app.call_tp_mcp = _orig_call_tp_mcp

    print("\n=== Consult-Executor: liest echte Spezialisten, schreibt nie in TP (v2.9.1) ===")
    app._tp_cache.clear()
    app._tp_cache_set(date.today().isoformat(), {"workouts": [
        {"id": "444", "sport": "Laufen", "title": "Longrun locker", "duration_min": 90},
    ]})
    _orig_medic_run, _orig_weather_run = medic.run, weather.run
    _orig_periodizer_run, _orig_fueling_run = periodizer.run, fueling.run
    _orig_allgemein_run = allgemeinmedic.run
    consult_calls = {}
    medic.run = lambda **kw: (consult_calls.setdefault("medic", kw), FAKE_MEDIC)[1]
    allgemeinmedic.run = lambda **kw: (consult_calls.setdefault("allgemein", kw), FAKE_ALLGEMEIN_FREI)[1]
    weather.run = lambda **kw: (consult_calls.setdefault("weather", kw), {"gesamtlage": "unkritisch"})[1]
    periodizer.run = lambda **kw: (consult_calls.setdefault("periodizer", kw), {"phase": "grundlage"})[1]
    fueling.run = lambda **kw: (consult_calls.setdefault("fueling", kw), {"ergaenzung": "…"})[1]

    async def _call_tp_mcp_verboten(tool_name, arguments):
        raise AssertionError(f"Consult darf niemals call_tp_mcp aufrufen (versucht: {tool_name})")
    app.call_tp_mcp = _call_tp_mcp_verboten
    try:
        executor = app._build_consult_executor(
            athlete={"name": "Hendrik", "races": [], "nutrition": {"rules": []},
                    "chronische_befunde": "keine", "swim_outdoor_min_celsius": 15},
            baseline=None, load={"ctl": 80, "atl": 75, "tsb": 5},
            woche=[], a_race=None, tage_bis_a=None,
            wx_today={"description": "sonnig", "is_hot": False},
            wx_tomorrow={"description": "regnerisch"},
            workouts_by_date={date.today().isoformat(): [
                {"sport": "Laufen", "title": "Longrun locker", "duration_min": 90},
            ]},
        )
        r_medic = executor("consult_medic", {"knie": 6})
        pruefe(r_medic == FAKE_MEDIC and "medic" in consult_calls,
               "consult_medic ruft den echten medic.run auf und gibt sein Ergebnis zurück")
        pruefe(consult_calls["medic"]["koerper"]["knie"] == 6,
               "Tool-Input wird ins koerper-Dict übernommen")
        pruefe("Laufen" in consult_calls["medic"]["sportarten"],
               "sportarten werden aus den gecachten TP-Workouts abgeleitet")

        r_weather = executor("consult_weather", {"date": date.today().isoformat()})
        pruefe(r_weather.get("gesamtlage") == "unkritisch", "consult_weather ruft weather.run auf")

        r_period = executor("consult_periodizer", {})
        pruefe(r_period.get("phase") == "grundlage", "consult_periodizer ruft periodizer.run auf")

        r_fuel = executor("consult_fueling", {"date": date.today().isoformat(), "workout_hint": "Longrun"})
        pruefe(r_fuel.get("ergaenzung") == "…", "consult_fueling matcht die Einheit und ruft fueling.run auf")

        r_unbekannt = executor("consult_irgendwas", {})
        pruefe("error" in r_unbekannt, "unbekannter Consult-Name liefert einen Fehler, keinen Absturz")
        # Keiner der obigen Aufrufe hat die auf AssertionError gestellte
        # call_tp_mcp-Attrappe ausgelöst — sonst wäre dieser try-Block bereits
        # mit dieser AssertionError abgebrochen: Consults sind rein lesend.
    finally:
        medic.run, weather.run = _orig_medic_run, _orig_weather_run
        periodizer.run, fueling.run = _orig_periodizer_run, _orig_fueling_run
        allgemeinmedic.run = _orig_allgemein_run
        app.call_tp_mcp = _orig_call_tp_mcp

    print("\n=== call_agent_with_consult: Tool-Result-Loop (v2.9.1) ===")

    class _FakeBlock:
        def __init__(self, type_, text=None, name=None, input=None, id=None):
            self.type, self.text, self.name, self.input, self.id = type_, text, name, input, id

    class _FakeUsage:
        def __init__(self, i=10, o=10):
            self.input_tokens, self.output_tokens = i, o

    class _FakeResp:
        def __init__(self, content, stop_reason="end_turn"):
            self.content, self.stop_reason, self.usage = content, stop_reason, _FakeUsage()

    class _FakeMessages:
        def __init__(self, responses):
            self._responses, self.calls = list(responses), []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return self._responses.pop(0)

    class _FakeClient:
        def __init__(self, responses):
            self.messages = _FakeMessages(responses)

    _orig_client = base_agent._client
    _fake_tools = [{"name": "propose_workout_update", "input_schema": {"type": "object", "properties": {}}}]

    # Fall A: ein consult_medic-Aufruf, danach ein propose_*-Tool in Runde 2.
    fake_client = _FakeClient([
        _FakeResp([_FakeBlock("text", text="Ich frag kurz nach."),
                  _FakeBlock("tool_use", name="consult_medic", input={"knie": 6}, id="tu1")],
                 stop_reason="tool_use"),
        _FakeResp([_FakeBlock("text", text="Dein Knie braucht heute Vorsicht."),
                  _FakeBlock("tool_use", name="propose_workout_update",
                             input={"date": "2026-01-15", "workout_hint": "Lauf",
                                    "new_title": "X", "summary": "…"}, id="tu2")],
                 stop_reason="tool_use"),
    ])
    base_agent._client = lambda: fake_client
    executor_calls = []
    try:
        ergebnis = base_agent.call_agent_with_consult(
            prompt="sys", messages=[{"role": "user", "content": "Mein Knie tut weh"}],
            tools=_fake_tools, consult_tool_names={"consult_medic"},
            executor=lambda name, inp: executor_calls.append((name, inp)) or {"urteil": "reduziert"},
            label="test-consult",
        )
        pruefe(len(fake_client.messages.calls) == 2, "genau zwei Anthropic-Calls bei einer Konsultation")
        pruefe(len(executor_calls) == 1 and executor_calls[0][0] == "consult_medic",
               "der Executor wird genau einmal mit dem richtigen Namen aufgerufen")
        pruefe(ergebnis["tool_call"] is not None and ergebnis["tool_call"]["name"] == "propose_workout_update",
               "nach der Konsultation darf Claude noch ein propose_*-Tool aufrufen")
        pruefe(ergebnis["text"] == "Dein Knie braucht heute Vorsicht.",
               "der finale Text kommt aus der zweiten Antwort")
    finally:
        base_agent._client = _orig_client

    # Fall B: kein Consult-Tool im Spiel → identisches Verhalten zu call_agent_with_tools.
    fake_client_b = _FakeClient([
        _FakeResp([_FakeBlock("text", text="Alles im Rahmen.")], stop_reason="end_turn"),
    ])
    base_agent._client = lambda: fake_client_b
    try:
        ergebnis_b = base_agent.call_agent_with_consult(
            prompt="sys", messages=[{"role": "user", "content": "Wie ist das Wetter?"}],
            tools=_fake_tools, consult_tool_names={"consult_medic"},
            executor=lambda name, inp: (_ for _ in ()).throw(AssertionError("darf nicht aufgerufen werden")),
            label="test-consult",
        )
        pruefe(len(fake_client_b.messages.calls) == 1,
               "ohne Consult-Tool-Call nur EIN Anthropic-Call — keine Mehrkosten im Normalfall")
        pruefe(ergebnis_b == {"text": "Alles im Rahmen.", "tool_call": None},
               "Verhalten identisch zu call_agent_with_tools")
    finally:
        base_agent._client = _orig_client

    # Fall C: drei Consult-Aufrufe in Runde 1 → nur MAX_CONSULTS_PER_TURN (=2) ausgeführt.
    fake_client_c = _FakeClient([
        _FakeResp([
            _FakeBlock("tool_use", name="consult_medic", input={}, id="tu1"),
            _FakeBlock("tool_use", name="consult_medic", input={}, id="tu2"),
            _FakeBlock("tool_use", name="consult_medic", input={}, id="tu3"),
        ], stop_reason="tool_use"),
        _FakeResp([_FakeBlock("text", text="Fertig.")], stop_reason="end_turn"),
    ])
    base_agent._client = lambda: fake_client_c
    ausgefuehrt_c = []
    try:
        base_agent.call_agent_with_consult(
            prompt="sys", messages=[{"role": "user", "content": "…"}],
            tools=_fake_tools, consult_tool_names={"consult_medic"},
            executor=lambda name, inp: ausgefuehrt_c.append(1) or {"ok": True},
            label="test-consult",
        )
        pruefe(len(ausgefuehrt_c) == base_agent.MAX_CONSULTS_PER_TURN == 2,
               "Kostendeckel: nur MAX_CONSULTS_PER_TURN Consults werden wirklich ausgeführt")
        letzte_tool_results = fake_client_c.messages.calls[1]["messages"][-1]["content"]
        pruefe(len(letzte_tool_results) == 3, "trotzdem bekommt jeder tool_use-Block einen tool_result")
        pruefe("Konsultationslimit" in letzte_tool_results[2]["content"],
               "der dritte Aufruf bekommt einen synthetischen Limit-Fehler statt ausgeführt zu werden")
    finally:
        base_agent._client = _orig_client

    pruefe("Du änderst hier nichts in TrainingPeaks" not in
           (Path(__file__).parent.parent / "agents" / "chat" / "chat.md").read_text(encoding="utf-8"),
           "die alte Sperre im Prompt ist raus")

    # v2.7.4: die Checks laufen als Hintergrund-Job. Der POST darf nicht mehr
    # blockieren, das Ergebnis kommt per Polling, und die Stufen des
    # Orchestrators müssen bis in den Job durchschlagen.
    print("\n=== Job-Queue für die Checks (v2.7.4) ===")
    app._check_jobs.clear()
    job_id = app._check_job_start()
    pruefe(app._check_jobs[job_id]["status"] == "pending", "neuer Job startet als pending")

    stufen = []
    async def lauf_ok(progress):
        for s in orchestrator.STUFEN:
            progress(s)
            stufen.append(app._check_jobs[job_id]["stage"])
        return {"status": "green", "_pipeline": "agents"}

    await app._run_check_job(job_id, lauf_ok)
    pruefe(stufen == list(orchestrator.STUFEN), "jede Stufe landet sichtbar im Job")
    fertig = app._check_jobs[job_id]
    pruefe(fertig["status"] == "done" and fertig["result"]["status"] == "green",
           "Ergebnis liegt nach dem Lauf im Job")

    async def lauf_kaputt(progress):
        raise RuntimeError("simulierter Ausfall")

    job2 = app._check_job_start()
    await app._run_check_job(job2, lauf_kaputt)
    pruefe(app._check_jobs[job2]["status"] == "error",
           "ein Fehler wird zum Job-Status, nicht zum ewigen Spinner")
    pruefe("simulierter Ausfall" in app._check_jobs[job2]["error"],
           "die Fehlerursache steht im Job")

    # Abgelaufene Jobs müssen verschwinden — der Store ist prozesslokal und
    # wächst sonst mit jedem Check.
    app._check_jobs["uralt"] = {"status": "done", "ts": 0}
    app._check_job_start()
    pruefe("uralt" not in app._check_jobs, "abgelaufene Jobs werden aufgeräumt")

    quelle_ab = inspect.getsource(app.check_abend)
    quelle_mo = inspect.getsource(app.check_morgen)
    pruefe("job_id" in quelle_ab and "job_id" in quelle_mo,
           "beide Check-Endpoints antworten mit einer job_id")
    # asyncio hält nur schwache Referenzen — ohne _check_tasks dürfte der GC
    # einen laufenden Check einsammeln.
    pruefe("_check_task_spawn" in quelle_ab and "_check_task_spawn" in quelle_mo,
           "Tasks werden über den Store gestartet, nicht referenzlos")
    pruefe("_check_tasks.add" in inspect.getsource(app._check_task_spawn),
           "die Task-Referenz wird gehalten")
    pruefe("await csv_file.read()" in quelle_mo,
           "die CSV wird im Request gelesen, nicht erst im Hintergrundtask")
    pruefe("progress" in inspect.signature(orchestrator.run_check).parameters,
           "run_check nimmt den progress-Callback")
    pruefe("runCheck(" in _INDEX and "/api/check/" in _INDEX,
           "Frontend pollt den Job-Status")
    pruefe("sr.status === 404" in _INDEX,
           "Frontend bricht ab, wenn der Job weg ist (Neustart)")
    for s in orchestrator.STUFEN:
        pruefe(f'"stage_{s}"' in _TRANS, f"Stufe '{s}' hat einen UI-Text")

    # v2.9.0: Recherche-Agent — läuft nie automatisch mit einem Check, nur auf
    # Klick. Gleiches Job-Queue-Muster wie die Checks, aber ein eigener Store.
    print("\n=== Recherche-Agent (v2.9.0) ===")
    # Der Fallback-Test weiter oben hat medic.run absichtlich zerschossen (siehe
    # Kommentar bei der Rückstellung weiter unten) — für den _try_agent_check-
    # Aufruf in diesem Block muss die Pipeline aber tatsächlich durchlaufen.
    medic.run = attrappe("medic", FAKE_MEDIC)
    # knowledge.json liegt lokal (ohne DATA_DIR-Override) im Repo — für den Test
    # auf eine Tempdir umbiegen, sonst würde der Testlauf die echte Datei im
    # Arbeitsverzeichnis verändern (wie beim DATA_DIR-Volume-Test weiter unten).
    import shutil as _shutil_research
    import tempfile as _tempfile_research
    _orig_knowledge_file = app.KNOWLEDGE_FILE
    _tmp_knowledge_dir = Path(_tempfile_research.mkdtemp(prefix="knowledgetest-"))
    app.KNOWLEDGE_FILE = _tmp_knowledge_dir / "knowledge.json"

    app._research_jobs.clear()
    r_job_id = app._research_job_start()
    pruefe(app._research_jobs[r_job_id]["status"] == "pending", "neuer Recherche-Job startet als pending")

    app.KNOWLEDGE_FILE.write_text('{"eintraege": []}', encoding="utf-8")
    await app._run_research_job(r_job_id, "Carb-Intake Ultradistanz")
    fertig_research = app._research_jobs[r_job_id]
    pruefe(fertig_research["status"] == "done" and fertig_research["result"] == FAKE_RESEARCH,
           "Ergebnis liegt nach dem Lauf im Job")
    gespeichert = app.load_knowledge()["eintraege"]
    pruefe(len(gespeichert) == 2, "beide Funde landen in knowledge.json")
    hoch_gespeichert = next(e for e in gespeichert if e["konfidenz"] == "hoch")
    mittel_gespeichert = next(e for e in gespeichert if e["konfidenz"] == "mittel")
    pruefe(hoch_gespeichert["status"] == "akzeptiert" and hoch_gespeichert["entschieden_von"] == "system",
           "v2.9.0: Konfidenz 'hoch' wird automatisch akzeptiert, ohne Zustimmung (Herkunft 'system')")
    pruefe(mittel_gespeichert["status"] == "vorschlag",
           "Konfidenz 'mittel' bleibt Vorschlag zur Prüfung")
    pruefe(hoch_gespeichert["titel"] == FAKE_RESEARCH["erkenntnisse"][0]["titel"],
           "der gespeicherte Fund entspricht dem Agent-Ergebnis")

    def research_kaputt(**kwargs):
        raise RuntimeError("simulierter Recherche-Ausfall")
    _orig_research_run = research_agent.run
    research_agent.run = research_kaputt
    try:
        r_job2 = app._research_job_start()
        await app._run_research_job(r_job2, "kaputtes Thema")
        pruefe(app._research_jobs[r_job2]["status"] == "error",
               "ein Fehler wird zum Job-Status, nicht zum ewigen Spinner — kein unbehandelter Absturz")
    finally:
        research_agent.run = _orig_research_run

    app._research_jobs["uralt"] = {"status": "done", "ts": 0}
    app._research_job_start()
    pruefe("uralt" not in app._research_jobs, "abgelaufene Recherche-Jobs werden aufgeräumt")

    # Der Erfolgspfad spawnt einen echten Hintergrund-Task (asyncio.create_task,
    # fire-and-forget) — wie bei check_abend/check_morgen wird das hier bewusst
    # NICHT über den echten Endpoint-Call geprüft (Race mit dem Testende),
    # sondern per Quellcode-Prüfung, exakt das Muster von quelle_ab weiter oben.
    quelle_research_run = inspect.getsource(app.research_run)
    pruefe("job_id" in quelle_research_run,
           "POST /api/research/run antwortet sofort mit einer job_id")
    pruefe("_research_task_spawn" in quelle_research_run,
           "der Recherche-Lauf wird über den Store gestartet, nicht referenzlos")

    leer_thema_400 = False
    try:
        await app.research_run(_FakeRequest({"thema": "  "}))
    except HTTPException as e:
        leer_thema_400 = (e.status_code == 400)
    pruefe(leer_thema_400, "ein leeres Thema wird mit 400 abgelehnt")

    research_404 = False
    try:
        await app.research_status("gibt-es-nicht")
    except HTTPException as e:
        research_404 = (e.status_code == 404)
    pruefe(research_404, "ein unbekannter/abgelaufener Recherche-Job liefert 404")

    # knowledge.py — Vorschlag/Review über die Endpoints, nicht nur die reinen
    # Funktionen (die sind schon in test_offline.py geprüft).
    app.KNOWLEDGE_FILE.write_text(json.dumps({"eintraege": [
        {"id": "abc1234567", "thema": "t", "titel": "T", "aussage": "A", "quelle": "q",
         "konfidenz": "hoch", "betrifft": "Ernährung", "status": "vorschlag",
         "erstellt_am": "2026-01-01T00:00:00+00:00", "entschieden_am": None},
    ]}), encoding="utf-8")
    accept_result = await app.knowledge_accept("abc1234567")
    pruefe(accept_result == {"ok": True}, "Übernehmen eines bekannten Fundes klappt")
    pruefe(app.load_knowledge()["eintraege"][0]["status"] == "akzeptiert",
           "der Status steht danach persistiert auf akzeptiert")

    accept_404 = False
    try:
        await app.knowledge_accept("gibt-es-nicht")
    except HTTPException as e:
        accept_404 = (e.status_code == 404)
    pruefe(accept_404, "Übernehmen einer unbekannten id liefert 404")

    knowledge_list_resp = await app.knowledge_list()
    knowledge_list_data = json.loads(knowledge_list_resp.body)
    pruefe(knowledge_list_data["eintraege"][0]["status"] == "akzeptiert",
           "GET /api/knowledge zeigt den aktuellen Stand")

    # Der Check muss akzeptierte Funde tatsächlich an den Chefcoach durchreichen.
    await app._try_agent_check(
        athlete={"name": "Hendrik", "nutrition": {"rules": []}, "races": []},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20},
        koerper={"symptome": "keine", "geplante_einheiten": ["Run"]},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf",
                      "duration_min": 60, "description": "Z2"}],
        sleep=None, wasser_temp=None, tag="morgen",
    )
    pruefe(bool(mitschrieb["head_coach_last"].get("wissen"))
           and "Quelle: q" in mitschrieb["head_coach_last"]["wissen"],
           "akzeptierte Recherche-Funde erreichen den Chefcoach als 'wissen'-Kontext")

    for lang_block in ("research_title", "research_accept", "research_reject"):
        pruefe(f'"{lang_block}"' in _TRANS, f"'{lang_block}' ist in translations.py gepflegt")
    pruefe("wissen" in inspect.signature(orchestrator.run_check).parameters,
           "run_check nimmt den wissen-Parameter entgegen")
    # head_coach.run ist oben mit der Attrappe überschrieben (Signatur **kwargs)
    # — die echte Signatur liegt weiterhin unverändert am Submodul.
    pruefe("wissen" in inspect.signature(head_coach.head_coach.run).parameters,
           "head_coach.run nimmt den wissen-Parameter entgegen")

    # v2.9.2: Video-Transkript-Analyse — derselbe Job-Store, anderer Trigger.
    # youtube.fetch_transcript_and_title gemockt, kein echter Netzwerk-/Proxy-Call.
    _orig_fetch_transcript_and_title = app.youtube.fetch_transcript_and_title

    video_leer_400 = False
    try:
        await app.research_video(_FakeRequest({"url": "  "}))
    except HTTPException as e:
        video_leer_400 = (e.status_code == 400)
    pruefe(video_leer_400, "eine leere Video-URL wird mit 400 abgelehnt")

    video_ungueltig_400 = False
    try:
        await app.research_video(_FakeRequest({"url": "https://example.com/nicht-youtube"}))
    except HTTPException as e:
        video_ungueltig_400 = (e.status_code == 400)
    pruefe(video_ungueltig_400, "eine Nicht-YouTube-URL wird mit 400 abgelehnt")

    def _fetch_kaputt(video_id):
        raise youtube.YoutubeNotConfigured("kein Proxy konfiguriert")
    app.youtube.fetch_transcript_and_title = _fetch_kaputt
    video_not_configured_400 = False
    try:
        await app.research_video(_FakeRequest({"url": "https://youtu.be/dQw4w9WgXcQ"}))
    except HTTPException as e:
        video_not_configured_400 = (e.status_code == 400
                                     and e.detail == app.T["err_video_not_configured"])
    pruefe(video_not_configured_400,
           "fehlende Webshare-Konfiguration liefert 400 mit klarer Meldung, kein Absturz")

    def _fetch_ok(video_id):
        return ("Transkript-Text über Tapering.", "Test-Video-Titel", False)
    app.youtube.fetch_transcript_and_title = _fetch_ok
    video_run_resp = await app.research_video(_FakeRequest({"url": "https://youtu.be/dQw4w9WgXcQ"}))
    video_run_data = json.loads(video_run_resp.body)
    pruefe("job_id" in video_run_data and video_run_data["titel"] == "Test-Video-Titel",
           "POST /api/research/video liefert sofort job_id + Titel")

    # Der Erfolgspfad spawnt (wie bei research_run) einen echten Hintergrund-Task
    # — deshalb hier nur Quellcode-Prüfung, kein Warten auf den echten Task.
    quelle_research_video = inspect.getsource(app.research_video)
    pruefe("_video_task_spawn" in quelle_research_video,
           "der Video-Lauf wird über den Store gestartet, nicht referenzlos")

    app.youtube.fetch_transcript_and_title = _orig_fetch_transcript_and_title

    # _run_video_job direkt geprüft (ohne den Hintergrund-Task-Race).
    v_job_id = app._research_job_start()
    await app._run_video_job(v_job_id, url="https://youtu.be/dQw4w9WgXcQ", titel="Test-Video-Titel",
                             transcript="Transkript-Text", gekuerzt=False)
    fertig_video = app._research_jobs[v_job_id]
    pruefe(fertig_video["status"] == "done" and fertig_video["result"] == FAKE_VIDEO_RESEARCH,
           "_run_video_job liefert das Agent-Ergebnis in den Job")
    gespeichert_video = app.load_knowledge()["eintraege"]
    video_fund = next((e for e in gespeichert_video if e["thema"] == "Video: Test-Video-Titel"), None)
    pruefe(video_fund is not None and video_fund["konfidenz"] == "mittel" and video_fund["status"] == "vorschlag",
           "Video-Funde landen in knowledge.json mit thema='Video: <Titel>' und derselben Konfidenz-Regel")

    def video_kaputt(**kwargs):
        raise RuntimeError("simulierter Video-Ausfall")
    _orig_run_video = research_agent.run_video
    research_agent.run_video = video_kaputt
    try:
        v_job2 = app._research_job_start()
        await app._run_video_job(v_job2, url="https://youtu.be/x", titel="Kaputt",
                                 transcript="…", gekuerzt=False)
        pruefe(app._research_jobs[v_job2]["status"] == "error",
               "ein Fehler im Video-Job wird zum Job-Status, nicht zum ewigen Spinner")
    finally:
        research_agent.run_video = _orig_run_video

    for lang_block_video in ("research_video_label", "research_video_start", "err_video_url_missing"):
        pruefe(f'"{lang_block_video}"' in _TRANS, f"'{lang_block_video}' ist in translations.py gepflegt")
    # research_agent.run_video ist oben mit der Attrappe überschrieben (Signatur
    # **kwargs) — die echte Signatur liegt weiterhin unverändert am Submodul,
    # exakt dasselbe Muster wie beim head_coach.head_coach.run-Check oben.
    pruefe({"titel", "url", "transcript", "gekuerzt", "model"}
           <= set(inspect.signature(research_agent.research.run_video).parameters),
           "research.run_video nimmt titel/url/transcript/gekuerzt/model entgegen")

    # Aufräumen: echten Pfad zurücksetzen, Tempdir entfernen, Job-Store leeren.
    app.KNOWLEDGE_FILE = _orig_knowledge_file
    _shutil_research.rmtree(_tmp_knowledge_dir, ignore_errors=True)
    app._research_jobs.clear()

    # Der echte Orchestrator (mit den Agent-Attrappen von oben) muss die
    # Stufen tatsächlich melden — sonst bleibt der Spinner stumm.
    # Der Fallback-Test oben hat den Mediziner absichtlich zerschossen.
    medic.run = attrappe("medic", FAKE_MEDIC)
    echte_stufen = []
    await app._try_agent_check(
        athlete={"name": "Hendrik", "nutrition": {"rules": []}, "races": []},
        baseline=None, weather={"description": "Sonnig", "temp_max": 20},
        koerper={"symptome": "keine", "geplante_einheiten": ["Run"]},
        tp_workouts=[{"id": "1", "sport": "Run", "title": "Lauf",
                      "duration_min": 60, "description": "Z2"}],
        sleep=None, wasser_temp=None, tag="morgen",
        progress=echte_stufen.append,
    )
    pruefe(echte_stufen[:2] == ["spezialisten", "chefcoach"],
           "der echte Orchestrator meldet seine Stufen der Reihe nach")
    pruefe(set(echte_stufen) <= set(orchestrator.STUFEN),
           "es werden nur bekannte Stufen gemeldet")

    # v2.7.5: MCP-Server für Claude Desktop / Claude Code.
    # coach_mcp.py wird hier absichtlich NICHT importiert — das mcp-Paket zieht
    # ein neueres starlette nach, als fastapi 0.111 erlaubt. Deshalb ein eigenes
    # venv (.venv-mcp) und hier nur Quellcode-Prüfungen.
    print("\n=== MCP-Server (v2.7.5) ===")
    pruefe(hasattr(app, "api_load"), "/api/load existiert (Belastung für den MCP)")
    load_quelle = inspect.getsource(app.api_load)
    pruefe('"available": False' in load_quelle,
           "/api/load liefert available=False statt zu failen, wenn TP fehlt")
    pruefe("erfundene" not in load_quelle and "_fetch_training_load" in load_quelle,
           "/api/load nutzt die deterministische Berechnung, nicht ein Modell")

    _MCP = (_WURZEL / "coach_mcp.py").read_text(encoding="utf-8")
    for werkzeug in ("training", "belastung", "erholung", "wetter", "profil",
                     "einheiten_historie", "coach_frage", "app_status"):
        pruefe(f"async def {werkzeug}(" in _MCP, f"MCP-Tool '{werkzeug}' ist definiert")
    pruefe('transport="stdio"' in _MCP,
           "MCP läuft über stdio — keine neue öffentliche Angriffsfläche")
    pruefe("Schlafdauer" in _MCP,
           "erholung-Tool warnt, dass Schlafdauer kein Entscheidungsfaktor ist")
    # Getrennte Requirements: mcp auf Railway mitzuschleppen bricht starlette.
    pruefe((_WURZEL / "requirements-mcp.txt").exists(), "requirements-mcp.txt existiert")
    pruefe("mcp" not in (_WURZEL / "requirements.txt").read_text(encoding="utf-8"),
           "mcp steht NICHT in der Railway-requirements.txt")

    # v2.7.6: Railway-Volume. Ohne DATA_DIR verlor jeder Deploy Profil,
    # Baseline und Schlafverlauf — der Container hat kein persistentes FS.
    print("\n=== Persistenter Zustand / Volume (v2.7.6) ===")
    import shutil as _shutil
    import tempfile
    original_dir = app.DATA_DIR
    tmp = Path(tempfile.mkdtemp(prefix="voltest-"))
    try:
        app.DATA_DIR = tmp / "frisch"          # existiert noch nicht: wie ein neues Volume
        info = app._init_data_dir()
        pruefe(info["persistent"] is True, "DATA_DIR abweichend vom Repo gilt als persistent")
        pruefe(info["writable"] is True and info["error"] is None, "DATA_DIR ist beschreibbar")
        pruefe(set(info["seeded"]) == {"athlete.json", "baseline.json", "sleep_history.json", "knowledge.json"},
               "leeres Volume wird mit allen Zustandsdateien geseedet (inkl. knowledge.json seit v2.9.0)")
        pruefe((app.DATA_DIR / "athlete.json").exists(),
               "athlete.json liegt im Volume — sonst hätte die App kein Profil")
        zweiter = app._init_data_dir()
        pruefe(zweiter["seeded"] == [],
               "zweiter Start seedet NICHT nochmal (überschreibt keine Änderungen)")
        # Kernversprechen: eine Änderung im Volume übersteht einen Neustart.
        (app.DATA_DIR / "sleep_history.json").write_text('[{"date":"2026-07-26"}]',
                                                         encoding="utf-8")
        app._init_data_dir()
        pruefe('2026-07-26' in (app.DATA_DIR / "sleep_history.json").read_text(encoding="utf-8"),
               "geschriebene Daten überleben einen Neustart")
    finally:
        app.DATA_DIR = original_dir
        _shutil.rmtree(tmp, ignore_errors=True)

    pruefe(app.DATA_DIR == original_dir, "DATA_DIR nach dem Test zurückgesetzt")
    version = await app.api_version()
    pruefe("storage" in version and "persistent" in version["storage"],
           "/api/version zeigt, ob der Zustand persistent liegt")
    pruefe("DATA_DIR" in inspect.getsource(app._init_data_dir),
           "DATA_DIR ist per ENV steuerbar (lokal unverändert)")

    print("\n=== MCP über HTTP (v2.7.6) ===")
    pruefe("MCP_TOKEN" in _MCP and "compare_digest" in _MCP,
           "HTTP-Modus prüft einen Bearer-Token zeitkonstant")
    pruefe("mindestens 32 Zeichen" in _MCP,
           "zu kurzer oder fehlender Token verhindert den Start")
    pruefe('"/health"' in _MCP,
           "/health bleibt offen für den Railway-Healthcheck")
    pruefe('transport="stdio"' in _MCP and "streamable_http_app" in _MCP,
           "beide Betriebsarten teilen sich dieselben Tools")
    pruefe((_WURZEL / "Dockerfile.mcp").exists(),
           "eigenes Dockerfile — das App-Image bleibt unangetastet")
    pruefe("requirements-mcp.txt" in (_WURZEL / "Dockerfile.mcp").read_text(encoding="utf-8"),
           "Dockerfile.mcp installiert NICHT die App-Requirements")

    print(f"\n{'=' * 44}")
    if fehler:
        print(f"FEHLGESCHLAGEN — {len(fehler)} Problem(e)")
        return 1
    print("Verdrahtung geprüft, alles grün.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
