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

import agents.architect as architect  # noqa: E402
import agents.head_coach as head_coach  # noqa: E402
import agents.medic as medic  # noqa: E402
import agents.weather as weather  # noqa: E402
import app  # noqa: E402
import orchestrator  # noqa: E402

fehler = []
mitschrieb = {}


def pruefe(bedingung, text):
    print(f"  {'ok   ' if bedingung else 'FEHLT'} {text}")
    if not bedingung:
        fehler.append(text)


FAKE_MEDIC = {
    "gesamturteil": "eingeschraenkt", "leitsymptom": "Achilles rechts 5/10",
    "sportarten": [{"sport": "Laufen", "urteil": "stop", "grund": "Achilles rechts 5/10"}],
    "alternativen": ["Aquajogging"], "erholung": "HRV im Rahmen",
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
    "beschreibung": "40 min ganz locker (6:30–7:05/km)\nHITZE: 750ml/h",
    "dauer_min": 40, "tp_struktur": None, "distanz_m": None,
}


def attrappe(name, antwort):
    def _run(**kwargs):
        mitschrieb.setdefault(name, []).append(kwargs)
        mitschrieb[name + "_last"] = kwargs
        return antwort
    return _run


medic.run = attrappe("medic", FAKE_MEDIC)
weather.run = attrappe("weather", FAKE_WETTER)
head_coach.run = attrappe("head_coach", FAKE_COACH)
architect.run = attrappe("architect", FAKE_ARCHITEKT)
# Der Orchestrator hat die Module beim Import gebunden — Attrappen nachziehen.
orchestrator.medic, orchestrator.weather = medic, weather
orchestrator.head_coach, orchestrator.architect = head_coach, architect


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
                            "goal_total": "10:50"}]},
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

    print("\n=== Architekt läuft nur für MOD ===")
    pruefe(len(mitschrieb.get("architect", [])) == 1,
           "Genau ein Architekt-Aufruf bei 1× MOD + 1× GO")
    a = mitschrieb["architect_last"]
    pruefe(a["auftrag"]["anpassung"]["dauer_min"] == 40, "Architekt bekommt die Zieldauer 40")
    pruefe(a["auftrag"]["begruendung"] == "Achilles rechts 5/10", "Architekt bekommt die Begründung")
    pruefe(a["workout"]["title"] == "Schwellenlauf", "Architekt bekommt das RICHTIGE Workout (Index-Zuordnung)")
    pruefe("31.0 °C" in a["wetter_zeile"], "Architekt bekommt die Wetterzeile")

    lauf, rad = ergebnis["sportarten"]
    pruefe(lauf["beschreibung"].startswith("40 min ganz locker"), "MOD nutzt den Architekten-Text")
    pruefe(rad["beschreibung"] == "2h Z2, 117-130 bpm", "GO übernimmt das Original ZEICHENGENAU")
    pruefe(lauf["ernaehrung"] == "Während: Wasser reicht", "MOD: Ernährung nach neuer Dauer (40 min)")
    pruefe(rad["ernaehrung"] == "Während: 90g Carbs/h", "GO: Ernährung nach Originaldauer (120 min)")

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
    pruefe(h["a_race"] and h["a_race"]["name"] == "Malbork", "Chefcoach bekommt das A-Rennen")
    pruefe("achilles_r" not in str(h.get("koerper", "")), "Chefcoach sieht KEINE Rohwerte mehr")

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

    print(f"\n{'=' * 44}")
    if fehler:
        print(f"FEHLGESCHLAGEN — {len(fehler)} Problem(e)")
        return 1
    print("Verdrahtung geprüft, alles grün.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
