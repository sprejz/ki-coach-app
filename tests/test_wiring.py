"""Prüft die Verdrahtung der Agent-Pipeline in app.py — ohne API-Calls.

Die drei Agents werden durch Attrappen ersetzt, die die Eingaben mitschreiben.
Damit lässt sich prüfen, ob die Fragebogenwerte korrekt ankommen, ob der
Fallback greift und ob die Antwort die Form hat, die das Frontend erwartet.

    .venv/bin/python -m tests.test_wiring
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["COACH_AGENTS"] = "1"
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-fuer-test")

import agents.allgemeinmedic as allgemeinmedic  # noqa: E402
import agents.architect as architect  # noqa: E402
import agents.architect_bike as architect_bike  # noqa: E402
import agents.architect_run as architect_run  # noqa: E402
import agents.architect_swim as architect_swim  # noqa: E402
import agents.fueling as fueling  # noqa: E402
import agents.head_coach as head_coach  # noqa: E402
import agents.medic as medic  # noqa: E402
import agents.periodizer as periodizer  # noqa: E402
import agents.weather as weather  # noqa: E402
import app  # noqa: E402
import orchestrator  # noqa: E402
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


def attrappe(name, antwort):
    def _run(**kwargs):
        mitschrieb.setdefault(name, []).append(kwargs)
        mitschrieb[name + "_last"] = kwargs
        return antwort
    return _run


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
    import agents.analyst as analyst_mod
    import agents.chat as chat_mod
    pruefe(app.chat_agent is chat_mod, "app.py nutzt den Chat-Agent")
    pruefe(app.analyst is analyst_mod, "app.py nutzt den Analyst-Agent")
    pruefe(hasattr(app, "_run_analysis_job_agent"), "Analyse-Job über den Agent existiert")

    # Regression v2.7.1: tomorrow_str war im Monolith-Chatpfad nie definiert.
    # Der NameError landete im except und der Chat bekam immer
    # "Wetterdaten nicht verfügbar". Der Bezeichner muss zugewiesen werden,
    # bevor er im f-String auftaucht.
    import inspect
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
        pruefe(set(info["seeded"]) == {"athlete.json", "baseline.json", "sleep_history.json"},
               "leeres Volume wird mit allen Zustandsdateien geseedet")
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
