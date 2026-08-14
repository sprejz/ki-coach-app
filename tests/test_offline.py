"""Offline-Prüfungen: kein API-Call, keine Kosten.

Prüft, dass die Schemas für Structured Outputs zulässig sind und dass die
User-Messages die relevanten Werte tatsächlich enthalten.

    .venv/bin/python -m tests.test_offline
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta  # noqa: E402

from agents import (  # noqa: E402
    allgemeinmedic, analyst, architect, architect_bike, architect_run, architect_swim, chat, fueling,
    head_coach, medic, periodizer, weather,
)
import orchestrator  # noqa: E402
from orchestrator import _baue_einheit, normalize_sport  # noqa: E402
from tests import fixtures as fx  # noqa: E402
from training_load import (  # noqa: E402
    PMC_TAGE, compute_pmc, letzte_einheiten, tage_bis, tss_pro_tag, wochenstruktur,
)
from translations import TRANSLATIONS  # noqa: E402
import strava  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    if bedingung:
        print(f"  ok    {text}")
    else:
        print(f"  FEHLT {text}")
        fehler.append(text)


def validiere_schema(schema, pfad="root"):
    """Structured Outputs verlangen additionalProperties:false und required für
    alle Properties; numerische/String-Constraints sind nicht erlaubt."""
    verboten = {"minimum", "maximum", "multipleOf", "minLength", "maxLength",
                "minItems", "maxItems", "pattern"}
    if not isinstance(schema, dict):
        return
    for key in verboten & set(schema):
        fehler.append(f"{pfad}: nicht unterstütztes Constraint '{key}'")
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            fehler.append(f"{pfad}: additionalProperties muss false sein")
        fehlend = set(props) - set(schema.get("required", []))
        if fehlend:
            fehler.append(f"{pfad}: nicht in required: {sorted(fehlend)}")
        for name, sub in props.items():
            validiere_schema(sub, f"{pfad}.{name}")
    if "items" in schema:
        validiere_schema(schema["items"], f"{pfad}[]")
    for variante in schema.get("anyOf", []):
        validiere_schema(variante, f"{pfad}|anyOf")


print("\n=== Belastungsmathematik (training_load.py) ===")
HEUTE = date(2026, 7, 25)

konstant = compute_pmc({(HEUTE - timedelta(days=i)).isoformat(): 70.0
                        for i in range(120)}, bis=HEUTE)
pruefe(abs(konstant["atl"] - 70.0) < 0.5,
       f"Dauerbelastung 70 TSS/Tag → ATL konvergiert gegen 70 (ist {konstant['atl']})")
pruefe(konstant["ctl"] < konstant["atl"],
       "CTL bleibt bei steigender Last unter ATL (42d träger als 7d)")
pruefe(konstant["tsb"] < 0, f"Dauerbelastung → TSB negativ (ist {konstant['tsb']})")

taper = compute_pmc({(HEUTE - timedelta(days=i)).isoformat(): (0.0 if i < 21 else 70.0)
                     for i in range(120)}, bis=HEUTE)
pruefe(taper["tsb"] > 25, f"3 Wochen Pause → TSB deutlich positiv (ist {taper['tsb']})")
pruefe(taper["atl"] < 5, f"3 Wochen Pause → ATL fast null (ist {taper['atl']})")
pruefe(taper["ctl"] < konstant["ctl"], "Pause baut CTL ab")

leer = compute_pmc({}, bis=HEUTE)
pruefe(leer["ctl"] == 0.0 and leer["tsb"] == 0.0, "Keine Daten → alle Werte 0, kein Absturz")
pruefe(leer["tage_mit_daten"] == 0, "Keine Daten → tage_mit_daten = 0")

# Feldnamen wie der TP-MCP sie liefert: snake_case, Dauern in Stunden. Die
# alte Fassung dieses Tests nutzte die camelCase-Namen der TP-eigenen API und
# hat den Bug damit mitgetragen statt ihn zu finden (v2.7.13).
roh = [{"date": "2026-07-24T00:00:00", "sport": "Run", "title": "Intervalle",
        "tss_actual": 60, "tss": 60, "tss_planned": 999, "duration_actual": 1.5},
       {"date": "2026-07-24", "sport": "Bike", "title": "Rollentraining", "tss": 40},
       {"date": "2026-07-23", "sport": "Swim", "title": "Technik",
        "tss_actual": None, "tss": None, "tss_planned": 50},
       {"date": "", "tss_actual": 100}]
pt = tss_pro_tag(roh)
pruefe(pt.get("2026-07-24") == 100.0, "TSS wird pro Tag summiert (60 + 40)")
pruefe(pt.get("2026-07-23") == 50.0, "Ohne Ist-Wert zählt der Planwert")
pruefe("" not in pt and len(pt) == 2, "Einträge ohne Datum werden verworfen")

# Das PMC-Fenster muss so lang sein wie die Historie, die der Aufrufer holt —
# fehlende Tage sind von Ruhetagen nicht unterscheidbar und drücken CTL.
voll = compute_pmc({(HEUTE - timedelta(days=i)).isoformat(): 70.0
                    for i in range(PMC_TAGE + 1)}, bis=HEUTE)
knapp = compute_pmc({(HEUTE - timedelta(days=i)).isoformat(): 70.0
                     for i in range(42)}, bis=HEUTE)
pruefe(voll["ctl"] - knapp["ctl"] > 15,
       f"Zu kurze Historie unterschätzt CTL deutlich ({knapp['ctl']} statt {voll['ctl']}) — "
       "deshalb muss _fetch_training_load PMC_TAGE Tage holen")
pruefe("PMC_TAGE" in (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8"),
       "app.py holt die Historie über PMC_TAGE, nicht über eine eigene Zahl")

le = letzte_einheiten(roh, bis=date(2026, 7, 24), tage=3)
pruefe([t["datum"] for t in le] == ["2026-07-22", "2026-07-23", "2026-07-24"],
       "letzte_einheiten liefert lückenlos jeden Tag des Zeitraums")
pruefe(le[0]["einheiten"] == [] and le[0]["tss_summe"] == 0,
       "Ein Tag ohne Einheit ist als Ruhetag erkennbar (leere Liste, 0 TSS)")
pruefe(le[2]["tss_summe"] == 100 and len(le[2]["einheiten"]) == 2,
       "Beide Einheiten des 24.7. landen mit Summe 100 im Tag")
pruefe(le[2]["einheiten"][0]["titel"] == "Intervalle"
       and le[2]["einheiten"][0]["dauer_min"] == 90,
       "Titel bleibt erhalten, Dauer wird von Stunden in Minuten umgerechnet")

woche = wochenstruktur([{"_day": HEUTE.isoformat(), "sport": "Run", "title": "X", "tss": 75}],
                       ab=HEUTE)
pruefe(len(woche) == 7, "Wochenstruktur umfasst 7 Tage")
pruefe(woche[0]["ist_heute"] and not woche[1]["ist_heute"], "Nur der erste Tag ist 'heute'")
pruefe(woche[0]["tss_summe"] == 75, "TSS-Summe pro Tag stimmt")
pruefe(woche[3]["einheiten"] == [], "Tage ohne Einheiten bleiben leer")
pruefe(tage_bis("2026-09-06", ab=HEUTE) == 43, "Tage bis Malbork: 43")
pruefe(tage_bis("", ab=HEUTE) is None and tage_bis("kaputt", ab=HEUTE) is None,
       "Ungültiges Datum → None statt Absturz")

print("\n=== Schemas ===")
for name, schema in [("medic", medic.SCHEMA), ("allgemeinmedic", allgemeinmedic.SCHEMA),
                     ("weather", weather.SCHEMA), ("fueling", fueling.SCHEMA),
                     ("head_coach", head_coach.SCHEMA), ("architect", architect.SCHEMA),
                     ("periodizer", periodizer.SCHEMA), ("analyst", analyst.SCHEMA)]:
    vorher = len(fehler)
    validiere_schema(schema, name)
    pruefe(len(fehler) == vorher, f"{name}.SCHEMA ist gültig")

print("\n=== Arbeitsteilung Chefcoach / Architekt ===")
hc_sp = set(head_coach.SCHEMA["properties"]["sportarten"]["items"]["properties"])
pruefe("anpassung" in hc_sp, "Chefcoach liefert einen Auftrag (anpassung)")
pruefe(not {"beschreibung", "tp_struktur", "distanz_m", "ernaehrung"} & hc_sp,
       "Chefcoach formuliert NICHT mehr aus (keine beschreibung/tp_struktur/distanz_m/ernaehrung)")
arch_props = set(architect.SCHEMA["properties"])
pruefe({"beschreibung", "tp_struktur", "distanz_m", "dauer_min"} <= arch_props,
       "Architekt liefert Beschreibung, Struktur, Distanz und Dauer")


def frontend_vertrag(eintrag: dict) -> set:
    return set(eintrag) - {"_begruendung"}


print("\n=== Frontend-Vertrag (vom Orchestrator zusammengebaut) ===")
ATHLET = {"nutrition": {"rules": [
    {"duration_max_min": 60, "before": "Nüchtern", "during": "Wasser reicht"},
    {"duration_min_min": 90, "duration_max_min": 180, "during": "90g Carbs/h"},
]}}

go = asyncio.run(_baue_einheit(
    entscheidung={"sport": "Laufen", "badge": "GO", "details": "Läuft",
                  "begruendung": "", "anpassung": {}},
    workout={"sport": "Run", "description": "35 min locker (6:15–6:45/km)", "duration_min": 35},
    athlete=ATHLET, wetter_zeile="Sonnig", model="egal",
))
erwartet_sp = {"sport", "badge", "details", "beschreibung", "ernaehrung",
               "tp_struktur", "distanz_m"}
pruefe(erwartet_sp <= frontend_vertrag(go), f"Eintrag hat alle Felder für applyToTP: {sorted(erwartet_sp)}")
pruefe(go["beschreibung"] == "35 min locker (6:15–6:45/km)",
       "GO übernimmt die Original-Beschreibung ZEICHENGENAU (ohne Modell)")
pruefe(go["ernaehrung"] == "Vorher: Nüchtern | Während: Wasser reicht",
       "GO bekommt die Ernährung aus der Tabelle (35 min → erste Regel)")
pruefe(go["tp_struktur"] is None, "GO bekommt keine TP-Struktur")

skip = asyncio.run(_baue_einheit(
    entscheidung={"sport": "Laufen", "badge": "SKIP", "details": "Achilles",
                  "begruendung": "Achilles 5/10", "anpassung": {}},
    workout={"sport": "Run", "description": "4×8min @ 5:20", "duration_min": 60},
    athlete=ATHLET, wetter_zeile="Sonnig", model="egal",
))
pruefe(skip["beschreibung"] == "", "SKIP bekommt keine Beschreibung (ohne Modell)")
pruefe(skip["ernaehrung"] == "", "SKIP bekommt keine Ernährung")

print("\n=== Sportarten-Normalisierung ===")
for roh, soll in [("Run", "Laufen"), ("Bike", "Rad"), ("Swim", "Schwimmen"),
                  ("Zwift (KI)", "Rad"), ("Golf", "Sonstiges"), ("", "Sonstiges")]:
    pruefe(normalize_sport(roh) == soll, f"{roh!r} → {soll}")

print("\n=== User-Messages enthalten die Werte ===")
m_in = medic.build_input(koerper=fx.KOERPER_ACHILLES, sportarten=["Laufen"],
                         sleep=fx.SLEEP_AUFFAELLIG, baseline=None)
pruefe("Achillessehne rechts: 5/10" in m_in, "Mediziner sieht Achilles rechts 5/10")
pruefe("Waden: 4/10" in m_in, "Mediziner sieht Waden 4/10")
pruefe("HRV niedrig" in m_in, "Mediziner sieht die Schlaf-Flags")
pruefe("symptome" not in m_in.lower() and "krankheit" not in m_in.lower(),
       "Sportmediziner sieht KEINE Krankheitssymptome mehr (an den Allgemeinmediziner ausgelagert)")

am_in = allgemeinmedic.build_input(koerper=fx.KOERPER_FIEBER, sportarten=["Laufen"],
                                   chronische_befunde="Asthma", sleep=None, baseline=None)
pruefe("38.9" in am_in, "Allgemeinmediziner sieht die Fiebertemperatur")
pruefe("Asthma" in am_in, "Allgemeinmediziner sieht die chronischen Befunde")
pruefe("nicht gemessen" in am_in, "Fehlende Werte (Blutdruck) werden explizit als fehlend markiert, nicht erfunden")

f_in = fueling.build_input(basis="Während: 90g Carbs/h", sport="Laufen", dauer_min=120,
                           badge="GO", is_hot=True, temp_max=31, chronische_befunde="Reizdarm")
pruefe("90g Carbs/h" in f_in, "Fueling-Agent sieht die Tabellen-Basis")
pruefe("31" in f_in, "Fueling-Agent sieht die Temperatur")
pruefe("Reizdarm" in f_in, "Fueling-Agent sieht den chronischen Befund")
f_in_renntag = fueling.build_input(basis="Renntag-Protokoll", sport="Laufen", dauer_min=241,
                                   badge="GO", ist_renntag=True, rennname="Malbork")
pruefe("RENNTAG" in f_in_renntag and "Malbork" in f_in_renntag, "Fueling-Agent sieht den Renntag")

w_in = weather.build_input(weather=fx.WETTER_HITZE, sportarten=["Laufen", "Schwimmen"],
                           titel=["Schwellenlauf"], swim_min_c=15)
pruefe("31.0 °C" in w_in, "Wetter-Taktiker sieht 31 °C")
pruefe("Hitzetag" in w_in, "Wetter-Taktiker sieht das Hitze-Flag")
pruefe("14:00 | 31" in w_in, "Wetter-Taktiker sieht den Stundenverlauf")

hc_in = head_coach.build_input(
    athlete={"name": "Hendrik", "ftp_watt": 286, "weight_kg": 84,
             "run_threshold_pace": "5:20", "css_per_100m": "2:20",
             "nutrition": {"rules": [{"duration_min_min": 90, "during": "90g Carbs/h"}]}},
    a_race={"name": "Malbork", "date": "2026-09-06", "goal_total": "10:50"},
    medic={"sportarten": [{"sport": "Laufen", "urteil": "stop", "grund": "Achilles 5/10"}],
           "alternativen": ["Aquajogging"], "erholung": "HRV unter Baseline"},
    wetter={"gesamtlage": "anpassen", "hinweis": "31 °C",
            "sportarten": [{"sport": "Laufen", "empfehlung": "zeitfenster",
                            "anpassung": "Pace 5% langsamer", "zeitfenster": "vor 09:00"}],
            "versorgung": "750 ml/h"},
    allgemein={"gesamturteil": "frei", "leitbefund": "", "sportarten": [],
               "alternativen": [], "hinweis_chronisch": ""},
    tp_workouts=fx.TP_LAUF_INTERVALL, tag="Sonntag, 26.07.2026",
)
pruefe("**stop**" in hc_in, "Chefcoach sieht das medizinische stop-Urteil")
pruefe("Malbork" in hc_in, "Chefcoach sieht das A-Rennen")
pruefe("4×8 min @ 5:20/km" in hc_in, "Chefcoach sieht die Original-Beschreibung aus TP")
pruefe("Carbs" not in hc_in, "Chefcoach sieht KEINE Ernährungsregeln mehr (deterministisch)")
pruefe("Allgemeinmediziner" in hc_in, "Chefcoach sieht die Sektion des Allgemeinmediziners")

arch_in = architect.build_input(
    athlete={"ftp_watt": 286, "run_threshold_pace": "5:20", "css_per_100m": "2:20",
             "threshold_hr_bike": 145},
    workout=fx.TP_LAUF_INTERVALL[0],
    auftrag={"begruendung": "Hitze 31 °C",
             "anpassung": {"dauer_min": 45, "zone": "Z2", "kein_tempo": True,
                           "indoor": False, "sportwechsel": None,
                           "hinweis": "Start vor 09:00"}},
    wetter_zeile="Sonnig, 19–31 °C, Regen 5 %",
)
per_in = periodizer.build_input(
    load=fx.LOAD_UEBERLASTET, woche=fx.WOCHE_MIT_SCHLUESSELEINHEIT,
    a_race=fx.A_RACE_MALBORK, naechste_rennen=[fx.A_RACE_MALBORK], tage_bis_a=43,
)
pruefe("Ramp Rate (CTL-Zuwachs letzte 7 Tage): 9.4" in per_in, "Periodisierer sieht die Ramp Rate")
pruefe("TSB (Frische): -34.6" in per_in, "Periodisierer sieht den TSB")
pruefe("noch 43 Tage" in per_in, "Periodisierer sieht den Abstand zum A-Rennen")
pruefe("← HEUTE" in per_in, "Periodisierer erkennt, welcher Tag heute ist")
pruefe("Lange Ausfahrt 4h" in per_in, "Periodisierer sieht die ganze Woche, nicht nur heute")
pruefe("Tage mit Trainingsdaten im Zeitraum: 27" in per_in,
       "Periodisierer sieht die Datenlage (kann Belastbarkeit einschätzen)")

# v2.7.13: Ohne die absolvierten Einheiten und das letzte Rennen ordnete der
# Periodisierer einen Wettkampf als anonyme TSS-Zahl in einen Belastungsblock
# ein ("neun Tage Belastungsphase" zwei Tage nach dem Rennen).
per_nach_rennen = periodizer.build_input(
    load={**fx.LOAD_UEBERLASTET,
          "letzte_einheiten": [
              {"datum": "2026-07-23", "einheiten": [], "tss_summe": 0},
              {"datum": "2026-07-24", "tss_summe": 118, "einheiten": [
                  {"sport": "Swim", "titel": "Open Water Swimming",
                   "dauer_min": 39, "tss": 52, "distanz_km": 1.5},
                  {"sport": "Bike", "titel": "Radfahren",
                   "dauer_min": 63, "tss": 66, "distanz_km": 39.6}]},
          ],
          "letztes_rennen": {"name": "GEWOBA Bremen", "date": "2026-07-24",
                             "priority": "B", "tage_her": 2}},
    woche=fx.WOCHE_MIT_SCHLUESSELEINHEIT, a_race=fx.A_RACE_MALBORK,
    naechste_rennen=[fx.A_RACE_MALBORK], tage_bis_a=43,
)
pruefe("Open Water Swimming" in per_nach_rennen,
       "Periodisierer sieht die Titel der absolvierten Einheiten, nicht nur TSS")
pruefe("Ruhetag (0 TSS)" in per_nach_rennen,
       "Ruhetage sind ausgewiesen — Grundlage für 'X Tage ohne Erholung'")
pruefe("Letztes Rennen: GEWOBA Bremen" in per_nach_rennen and "vor 2 Tagen" in per_nach_rennen,
       "Periodisierer sieht das zurückliegende Rennen mit Abstand in Tagen")
pruefe("Tatsächlich absolviert" not in per_in,
       "Ohne Daten bleibt der Abschnitt weg statt leer dazustehen")
per_prompt = (Path(__file__).parent.parent / "agents/periodizer/periodizer.md").read_text(encoding="utf-8")
pruefe("Tatsächlich absolviert" in per_prompt and "Ruhetage ab" in per_prompt,
       "Der Prompt weist an, Ruhetage abzuzählen statt zu schätzen")

hc_mit_block = head_coach.build_input(
    athlete={"name": "H"}, a_race=fx.A_RACE_MALBORK,
    medic={"sportarten": []},
    wetter={"gesamtlage": "unkritisch", "sportarten": []},
    allgemein={"gesamturteil": "frei", "leitbefund": "", "sportarten": [],
               "alternativen": [], "hinweis_chronisch": ""},
    tp_workouts=[], tag="heute",
    block={"phase": "aufbau", "wochenintention": "Schwellenblock",
           "heute_rolle": "schluesseleinheit", "heute_begruendung": "einzige Intensität",
           "belastungsurteil": "grenzwertig", "spielraum": "zuruecknehmen",
           "hinweis": "Ramp 9.4", "warnung": "Ramp Rate über 7"},
)
pruefe("**schluesseleinheit**" in hc_mit_block, "Chefcoach sieht die Rolle des Tages")
pruefe("**zuruecknehmen**" in hc_mit_block, "Chefcoach sieht den Spielraum")
pruefe("WARNUNG: Ramp Rate über 7" in hc_mit_block, "Chefcoach sieht die Warnung")

hc_ohne_block = head_coach.build_input(
    athlete={"name": "H"}, a_race=None,
    medic={"sportarten": []},
    wetter={"gesamtlage": "unkritisch", "sportarten": []},
    allgemein={"gesamturteil": "frei", "leitbefund": "", "sportarten": [],
               "alternativen": [], "hinweis_chronisch": ""},
    tp_workouts=[], tag="heute", block=None,
)
pruefe("Periodisierer" not in hc_ohne_block,
       "Ohne Belastungsdaten steht nichts vom Periodisierer im Prompt")

print("\n=== Performance-Analyst ===")
FIT = {"dauer_min": 62, "distanz_km": 11.4, "avg_hr": 158, "max_hr": 172,
       "avg_pace_min_km": "5:26", "tss": 78,
       "laps": [{"t_min": 8, "avg_hr": 161, "pace": "5:18"},
                {"t_min": 8, "avg_hr": 166, "pace": "5:31"}]}
TP_IST = {"metrics": {"tss_actual": 78, "avg_hr": 158, "avg_power": 210, "avg_cadence": 88},
          "rpe": 7, "description": "4×8min @ 5:20"}
TP_NUR_PLAN = {"metrics": {"tss_planned": 75, "duration_planned": 1.0}, "description": "4×8min @ 5:20"}

pruefe(analyst.datenlage(FIT, TP_IST) == "fit", "FIT-Datei schlägt TP-Ist")
pruefe(analyst.datenlage(None, TP_IST) == "tp_ist", "Ohne FIT zählen die TP-Ist-Werte")
pruefe(analyst.datenlage(None, TP_NUR_PLAN) == "nur_plan", "Nur Plandaten werden erkannt")
pruefe(analyst.datenlage(None, None) == "nur_plan", "Gar keine Daten → nur_plan")

an_in = analyst.build_input(
    athlete={"ftp_watt": 286, "run_threshold_pace": "5:20", "css_per_100m": "2:20",
             "weight_kg": 84},
    a_race=fx.A_RACE_MALBORK, sport="Run", titel="Schwellenlauf", datum="2026-07-24",
    fit=FIT, tp=TP_IST, wetter={"description": "Sonnig", "avg_temp": 29.5,
                                "start_local": "07:00", "end_local": "08:02",
                                "temp_min": 27, "temp_max": 31, "precip_mm": 0},
    load=fx.LOAD_AUFBAU,
)
pruefe("Ø HF: 158 bpm" in an_in, "Analyst sieht die FIT-Herzfrequenz")
pruefe("5:18" in an_in and "5:31" in an_in, "Analyst sieht die einzelnen Splits")
pruefe("RPE (1–10): 7" in an_in, "Analyst sieht das RPE aus TP")
pruefe("Ø 29.5 °C" in an_in, "Analyst sieht das Wetter zur Trainingszeit")
pruefe("TSB -17.8" in an_in, "Analyst sieht die Belastungslage des Tages")
pruefe("Laufschwelle: 5:20 /km" in an_in, "Analyst sieht die Schwelle zum Vergleich")

an_plan = analyst.build_input(athlete={}, sport="Run", titel="Lauf", datum="2026-07-24",
                              fit=None, tp=TP_NUR_PLAN)
pruefe("NUR Plan-Daten" in an_plan, "Ohne Ist-Werte wird das im Prompt markiert")
pruefe("Bewerte die Einheit trotzdem" in an_plan,
       "Ohne Ist-Werte wird trotzdem eine Bewertung verlangt")

an_ernaehrung = analyst.build_input(athlete={}, sport="Run", titel="Lauf", datum="2026-07-24",
                                    fit=None, tp=None, ernaehrung_basis="Während: 90g Carbs/h")
pruefe("90g Carbs/h" in an_ernaehrung, "Analyst sieht die Ernährungsbasis für diese Dauer")
pruefe("ernaehrung_einschaetzung" in analyst.SCHEMA["properties"],
       "Analyst-Schema hat das Ernährungs-Einschätzungsfeld")

# Regression: echte tp_get_workout-Antwort (snake_case unter "metrics"),
# nicht die TP-eigenen camelCase-Namen — hat vor v2.7.9 dazu geführt, dass
# beim Analysten nur "description" ankam, keine einzige Zahl.
pruefe(analyst.datenlage(None, fx.TP_WORKOUT_STRUKTURIERT) == "tp_ist",
       "Echte TP-Antwort wird als tp_ist erkannt (avg_hr/avg_power/avg_cadence in 'metrics')")
an_echt = analyst.build_input(
    athlete={"ftp_watt": 286, "run_threshold_pace": "5:20", "css_per_100m": "2:20"},
    sport="Run", titel="3x16 min. LC", datum="2026-07-29",
    fit=None, tp=fx.TP_WORKOUT_STRUKTURIERT,
)
pruefe("TSS Ist: 64.2" in an_echt, "Analyst liest tss_actual aus 'metrics' (nicht mehr tssActual)")
pruefe("Ø HF Ist (bpm): 137" in an_echt, "Analyst liest avg_hr aus 'metrics'")
pruefe("Dauer Ist (min): 62.0" in an_echt, "duration_actual (Stunden) wird in Minuten umgerechnet")
pruefe("RPE (1–10): 5" in an_echt, "RPE kommt von der Top-Level 'rpe', nicht aus 'metrics'")
pruefe("Geplante Struktur" in an_echt, "Strukturierte Zielvorgabe wird gerendert")
pruefe("4× Wiederholung" in an_echt, "Wiederholungsblock wird mit Anzahl gerendert")
pruefe("Hard: 1 min @" in an_echt, "Harter Schritt zeigt Dauer und Ziel-Pace")
pruefe("5:04" in an_echt or "5:05" in an_echt, "Prozent-Ziel wird in eine konkrete Pace umgerechnet (100-105% von 5:20)")
pruefe("Warm up: 5 min" in an_echt and "Cool Down: 5 min" in an_echt,
       "Einfache (nicht wiederholte) Schritte werden ebenfalls gerendert")

print("\n=== Coach-Chat ===")
ctx = chat.build_context(
    athlete={"name": "Hendrik", "ftp_watt": 286, "weight_kg": 84},
    a_race=fx.A_RACE_MALBORK, tage_bis_a=43,
    tp_tage=["heute (2026-07-25): Run | Schwellenlauf | 60 min"],
    wetter_heute={"description": "Sonnig", "temp_min": 19, "temp_max": 31, "rain_prob": 5},
    wetter_morgen={"description": "Bedeckt", "temp_min": 15, "temp_max": 22, "rain_prob": 40},
    load=fx.LOAD_AUFBAU, heute_str="Samstag, 25.07.2026",
)
pruefe("noch 43 Tage" in ctx, "Chat kennt den Abstand zum A-Rennen")
pruefe("TSB -17.8" in ctx, "Chat kennt die Belastungslage")
pruefe("Schwellenlauf" in ctx, "Chat kennt den TP-Plan")
pruefe("heute: Sonnig, 19–31 °C" in ctx, "Chat kennt das Wetter heute")
pruefe("morgen: Bedeckt" in ctx, "Chat kennt das Wetter morgen — der alte Pfad konnte das nie")

ctx_leer = chat.build_context(athlete={"name": "H"}, a_race=None, tage_bis_a=None)
pruefe("Keine Wetterdaten verfügbar" in ctx_leer, "Ohne Wetter wird das explizit gesagt")
pruefe("keine Einheiten geplant" in ctx_leer, "Ohne TP-Plan wird das explizit gesagt")
pruefe("CTL" not in ctx_leer, "Ohne Belastungsdaten steht keine erfundene Kennzahl drin")

ctx_ernaehrung = chat.build_context(
    athlete={"name": "H", "chronische_befunde": "Reizdarm",
            "nutrition": {"mix": "Malto+Fructose", "carbs_per_hour_g": 90,
                          "rules": [{"duration_min_min": 60, "duration_max_min": 180,
                                     "during": "90g Carbs/h"}]}},
    a_race=None, tage_bis_a=None,
)
pruefe("90 g/h" in ctx_ernaehrung, "Chat kennt die Carbs-Rate")
pruefe("90g Carbs/h" in ctx_ernaehrung, "Chat kennt die Tabellenzeile für die passende Dauer")
pruefe("Reizdarm" in ctx_ernaehrung, "Chat kennt die chronischen Befunde (bisher fehlte das im Agent-Pfad)")

pruefe("Zieldauer: 45 min" in arch_in, "Architekt bekommt die Zieldauer")
pruefe("Kein Tempo" in arch_in, "Architekt bekommt die Tempo-Sperre")
pruefe("Start vor 09:00" in arch_in, "Architekt bekommt den Zusatzhinweis")
pruefe("4×8 min @ 5:20/km" in arch_in, "Architekt bekommt das Original als Vorlage")
pruefe("286 W" in arch_in, "Architekt bekommt die Schwellenwerte")

print("\n=== Strava-Integration (strava.py) ===")
STRAVA_LAUF = {
    "id": 111, "sport_type": "Run", "start_date_local": "2026-07-26T07:00:00",
    "moving_time": 3600, "distance": 10000.0,
    "average_heartrate": 152, "max_heartrate": 168, "average_cadence": 86,
}
STRAVA_LAPS_LAUF = [
    {"elapsed_time": 600, "distance": 2000.0, "average_heartrate": 148, "average_speed": 2000 / 600},
    {"elapsed_time": 660, "distance": 2000.0, "average_heartrate": 155, "average_speed": 2000 / 660},
]
fit_shape = strava._activity_to_fit_shape(STRAVA_LAUF, STRAVA_LAPS_LAUF)
pruefe(fit_shape.get("dauer_min") == 60.0, "Strava-Lauf: Dauer aus moving_time (60 min)")
pruefe(fit_shape.get("distanz_km") == 10.0, "Strava-Lauf: Distanz aus distance (10 km)")
pruefe(fit_shape.get("avg_hr") == 152 and fit_shape.get("max_hr") == 168,
       "Strava-Lauf: Herzfrequenz übernommen")
pruefe(fit_shape.get("avg_kadenz") == 86, "Strava-Lauf: Kadenz übernommen")
pruefe(fit_shape.get("avg_pace_min_km") == "6:00", "Strava-Lauf: Pace aus distance/moving_time (10km/60min)")
pruefe("avg_power_w" not in fit_shape, "Strava-Lauf ohne Leistungsmesser erfindet kein avg_power_w")
pruefe(len(fit_shape.get("laps", [])) == 2, "Strava-Lauf: beide Laps übernommen")
pruefe(fit_shape["laps"][0]["pace"] == "5:00", "Lap 1: Pace korrekt berechnet (2km/10min)")
pruefe(fit_shape["laps"][0]["km"] == 2.0 and fit_shape["laps"][0]["t_min"] == 10.0,
       "Lap 1: Distanz und Dauer korrekt umgerechnet")

STRAVA_RAD = {
    "id": 222, "sport_type": "Ride", "start_date_local": "2026-07-26T09:00:00",
    "moving_time": 7200, "distance": 60000.0,
    "average_watts": 180.4, "max_watts": 420, "weighted_average_watts": 195,
    "average_heartrate": 140, "max_heartrate": 165, "kilojoules": 1296.0,
}
rad_shape = strava._activity_to_fit_shape(STRAVA_RAD, [])
pruefe(rad_shape.get("avg_power_w") == 180, "Strava-Rad: Ø Leistung übernommen (gerundet)")
pruefe(rad_shape.get("max_power_w") == 420, "Strava-Rad: Max-Leistung übernommen")
pruefe(rad_shape.get("normalized_power_w") == 195, "Strava-Rad: NP aus weighted_average_watts")
pruefe(rad_shape.get("total_work_kj") == 1296.0, "Strava-Rad: Arbeit aus kilojoules übernommen")
pruefe("laps" not in rad_shape, "Ohne Laps wird keine leere Liste erfunden")

KANDIDATEN_TAG = [
    {"id": 1, "sport_type": "Run", "start_date_local": "2026-07-26T07:00:00",
     "moving_time": 3600, "distance": 10000},
    {"id": 2, "sport_type": "Ride", "start_date_local": "2026-07-26T17:00:00",
     "moving_time": 5400, "distance": 40000},
]
pruefe(strava.match_activity(KANDIDATEN_TAG, "Run")["id"] == 1,
       "match_activity filtert nach Sportart-Gruppe (Run)")
pruefe(strava.match_activity(KANDIDATEN_TAG, "Bike")["id"] == 2,
       "match_activity mappt TP 'Bike' auf Stravas 'Ride'")
pruefe(strava.match_activity([], "Run") is None, "match_activity ohne Kandidaten liefert None")

KANDIDATEN_ZWEI_LAEUFE = [
    {"id": 10, "sport_type": "Run", "start_date_local": "2026-07-26T06:30:00",
     "moving_time": 1200, "distance": 3000},
    {"id": 11, "sport_type": "Run", "start_date_local": "2026-07-26T17:00:00",
     "moving_time": 3600, "distance": 10000},
]
pruefe(strava.match_activity(KANDIDATEN_ZWEI_LAEUFE, "Run", "2026-07-26T06:35:00")["id"] == 10,
       "match_activity wählt bei Zeithinweis die zeitlich nächste Aktivität")
pruefe(strava.match_activity(KANDIDATEN_ZWEI_LAEUFE, "Run", "")["id"] == 11,
       "match_activity wählt ohne Zeithinweis die längste Aktivität")

# Realer Fall: TP kennt bei diesem Account praktisch nie eine Startzeit, aber
# zwei Bike-Einheiten am selben Tag (Hin-/Rückfahrt) sind nur über die
# geplante Dauer zu unterscheiden — "längste Aktivität" allein würde beide
# TP-Einträge auf dieselbe Strava-Fahrt matchen.
KANDIDATEN_ZWEI_RADFAHRTEN = [
    {"id": 20, "sport_type": "Ride", "start_date_local": "2026-07-26T11:10:00",
     "moving_time": 3334, "distance": 17342},   # Hinfahrt, ~56 min
    {"id": 21, "sport_type": "Ride", "start_date_local": "2026-07-26T14:33:00",
     "moving_time": 4315, "distance": 19754},   # Rückfahrt, ~72 min
]
pruefe(strava.match_activity(KANDIDATEN_ZWEI_RADFAHRTEN, "Bike", "", dauer_hint_min=55)["id"] == 20,
       "match_activity nutzt die geplante Dauer als Tie-Breaker ohne Zeithinweis (Hinfahrt)")
pruefe(strava.match_activity(KANDIDATEN_ZWEI_RADFAHRTEN, "Bike", "", dauer_hint_min=72)["id"] == 21,
       "...und erkennt die zweite, längere Einheit desselben Tages korrekt (Rückfahrt)")
pruefe(strava.match_activity(KANDIDATEN_ZWEI_RADFAHRTEN, "Bike") is not None,
       "Ganz ohne Zeit- oder Dauerhinweis fällt es auf die längste Aktivität zurück, statt leer zu laufen")

print("\n=== Workout-Architekt: eigener Prompt je Modul (v2.7.13) ===")
# Jeder Agent hat seit v2.7.13 seinen Prompt als eigene .md-Datei im eigenen
# Ordner statt zentral unter prompts/de/ — der Architekt lädt _prompt_fuer_sport()
# nicht mehr zur Laufzeit zusammen (die alte Kern+Zusatz-Verkettung war seit
# v2.7.12 ohnehin toter Code, weil der Orchestrator Laufen/Rad/Schwimmen längst
# an die eigenen Disziplin-Agenten dispatcht).
_WURZEL = Path(__file__).parent.parent
kraft_prompt = architect.load_prompt("architect", path=architect._PROMPT_PATH)
pruefe("GRUNDREGEL" in kraft_prompt and "TP-STRUKTUR" in kraft_prompt,
       "architect.md (Kraft/Sonstiges-Fallback) enthält den generischen Kern-Prompt")
pruefe(not hasattr(architect, "_prompt_fuer_sport"),
       "Der tote Sport-Verkettungscode (_prompt_fuer_sport) ist entfernt, kein Wiederaufleben")

for _mod, _ordner, _zusatz_marker, _zusatz_beleg in (
    (architect_run, "run", "Lauf-spezifisch", "Kadenz"),
    (architect_bike, "bike", "Rad-spezifisch", "rpm"),
    (architect_swim, "swim", "Schwimm-spezifisch", "CSS"),
):
    pruefe(_mod.SCHEMA is architect.SCHEMA,
           f"architect_{_ordner}.SCHEMA ist dasselbe Objekt wie der generische Fallback (keine Drift)")
    pruefe(_mod.build_input is architect.build_input,
           f"architect_{_ordner}.build_input ist dieselbe Funktion wie der generische Fallback")
    _prompt_datei = _WURZEL / "agents" / f"architect_{_ordner}" / f"architect_{_ordner}.md"
    pruefe(_prompt_datei.exists(), f"architect_{_ordner}.md liegt im eigenen Agent-Ordner")
    _prompt_text = _prompt_datei.read_text(encoding="utf-8")
    pruefe("GRUNDREGEL" in _prompt_text and "TP-STRUKTUR" in _prompt_text,
           f"architect_{_ordner}.md enthält den vollständigen generischen Kern-Prompt")
    pruefe(_zusatz_marker in _prompt_text and _zusatz_beleg in _prompt_text,
           f"architect_{_ordner}.md enthält den {_ordner}-spezifischen Zusatz")
    _geladen = _mod.load_prompt(_mod.SPORT, path=_prompt_datei)
    pruefe(_geladen == _prompt_text.strip(),
           f"architect_{_ordner}.load_prompt(path=...) liefert exakt den Dateiinhalt")

print("\n=== Alle Agenten laden ihren Prompt aus dem eigenen Ordner (v2.7.13) ===")
for _agentmodul, _ordner, _dateiname, _marker in (
    (medic, "medic", "medic.md", None),
    (allgemeinmedic, "allgemeinmedic", "allgemeinmedic.md", None),
    (weather, "weather", "weather.md", None),
    (periodizer, "periodizer", "periodizer.md", None),
    (head_coach, "head_coach", "head_coach.md", None),
    (chat, "chat", "chat.md", None),
    (fueling, "fueling", "fueling.md", None),
    (analyst, "analyst", "analyst.md", None),
):
    _erwartete_datei = _WURZEL / "agents" / _ordner / _dateiname
    pruefe(_erwartete_datei.exists(), f"{_ordner}/{_dateiname} liegt im eigenen Agent-Ordner")
    pruefe(_agentmodul._PROMPT_PATH == _erwartete_datei,
           f"{_ordner}._PROMPT_PATH zeigt auf die eigene .md-Datei")
pruefe(not (_WURZEL / "prompts").exists(),
       "prompts/de/ existiert nicht mehr — alle Prompts sind in ihre Agent-Ordner umgezogen")

pruefe(orchestrator._ARCHITECT_BY_SPORT.get("Laufen") is architect_run.run,
       "Orchestrator dispatcht 'Laufen' an architect_run")
pruefe(orchestrator._ARCHITECT_BY_SPORT.get("Rad") is architect_bike.run,
       "Orchestrator dispatcht 'Rad' an architect_bike")
pruefe(orchestrator._ARCHITECT_BY_SPORT.get("Schwimmen") is architect_swim.run,
       "Orchestrator dispatcht 'Schwimmen' an architect_swim")
pruefe(orchestrator._ARCHITECT_BY_SPORT.get("Kraft") is None
       and orchestrator._ARCHITECT_BY_SPORT.get("Sonstiges") is None,
       "Kraft/Sonstiges haben KEINEN Dispatch-Eintrag — fallen im Orchestrator auf architect.run zurück")

# --- Agenten-Namen-Registry (translations.py) ---
_ERWARTETE_AGENTEN_SCHLUESSEL = [
    "medic", "allgemein", "wetter", "block", "chefcoach",
    "architect", "architect_run", "architect_bike", "architect_swim",
    "fueling", "analyst",
]
for _sprache in ("de", "en"):
    _registry = TRANSLATIONS[_sprache].get("agenten", {})
    for _schluessel in _ERWARTETE_AGENTEN_SCHLUESSEL:
        _eintrag = _registry.get(_schluessel, {})
        pruefe(bool(_eintrag.get("name")) and bool(_eintrag.get("rolle")),
               f"agenten['{_schluessel}'] hat name+rolle ({_sprache})")

print(f"\n{'=' * 40}")
if fehler:
    print(f"FEHLGESCHLAGEN — {len(fehler)} Problem(e):")
    for f in fehler:
        print(f"  - {f}")
    sys.exit(1)
print("Alle Offline-Prüfungen bestanden.")
