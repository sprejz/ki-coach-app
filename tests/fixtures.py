"""Testfälle für die Coach-Agents.

Jeder Fall ist ein realistisches Szenario mit einer Erwartung, die sich
überprüfen lässt, ohne den ganzen Check zu fahren.
"""

WETTER_HITZE = {
    "description": "Sonnig", "temp_min": 19.0, "temp_max": 31.0, "rain_prob": 5,
    "is_thunderstorm": False, "is_rain": False, "is_hot": True, "is_cold": False,
    "hourly": [{"hour": h, "temp": t, "rain": 0} for h, t in
               [(6, 19), (8, 23), (10, 27), (12, 30), (14, 31), (16, 30), (18, 26), (20, 22)]],
}

WETTER_GEWITTER = {
    "description": "Gewitter", "temp_min": 17.0, "temp_max": 24.0, "rain_prob": 85,
    "is_thunderstorm": True, "is_rain": True, "is_hot": False, "is_cold": False,
    "hourly": [{"hour": h, "temp": 22, "rain": 80} for h in range(6, 21, 2)],
}

WETTER_MILD = {
    "description": "Teils bewölkt", "temp_min": 13.0, "temp_max": 21.0, "rain_prob": 10,
    "is_thunderstorm": False, "is_rain": False, "is_hot": False, "is_cold": False,
    "hourly": [{"hour": h, "temp": 18, "rain": 5} for h in range(6, 21, 2)],
}

KOERPER_GESUND = {
    "waden": 0, "knie": 0, "achilles_l": 0, "achilles_r": 0,
    "muedigkeit": 2, "muskelkater": ["keine"], "symptome": "keine",
    "fieber": None, "blutdruck_sys": None, "blutdruck_dia": None, "medikamente": None,
}

KOERPER_ACHILLES = {
    "waden": 4, "knie": 1, "achilles_l": 1, "achilles_r": 5,
    "muedigkeit": 3, "muskelkater": ["Beine leicht"], "symptome": "keine",
    "fieber": None, "blutdruck_sys": None, "blutdruck_dia": None, "medikamente": None,
}

KOERPER_KRANK = {
    "waden": 1, "knie": 1, "achilles_l": 0, "achilles_r": 0,
    "muedigkeit": 4, "muskelkater": ["keine"], "symptome": "neu mittel",
}

# Symptome-Pille sagt "keine" — beweist, dass Fieber allein (ohne Pille) den
# Allgemeinmediziner-Override auslöst.
KOERPER_FIEBER = {
    "waden": 0, "knie": 0, "achilles_l": 0, "achilles_r": 0,
    "muedigkeit": 2, "muskelkater": ["keine"], "symptome": "keine",
    "fieber": 38.9,
}

FAKE_FUELING_HITZE = {"relevant": True, "hinweis": "Bei dieser Hitze früher mit dem Trinken beginnen."}
FAKE_FUELING_LEER = {"relevant": False, "hinweis": ""}

SLEEP_AUFFAELLIG = {
    "hrv": 26.0, "wach_bpm": 62.0, "schlaf_bpm": 70.0, "atmung": 17.9, "effizienz": 79.0,
    "flags": ["HRV niedrig (26ms ≤ 29ms)", "WachBPM erhöht (62 ≥ 60)"],
}

TP_LAUF_INTERVALL = [{
    "id": "1", "sport": "Run", "title": "Schwellenlauf 4×8min",
    "duration_min": 60, "tss": 75, "start_time": "2026-07-26T06:30:00",
    "description": "Einlaufen: 15 min locker (6:30/km)\n4×8 min @ 5:20/km, 2 min Trabpause\nAuslaufen: 10 min",
}]

TP_TAG_MIT_DREI = [
    {"id": "1", "sport": "Swim", "title": "Technik 1500m", "duration_min": 45, "tss": 35,
     "description": "Einschwimmen 300m\n10×100m Technik\nAusschwimmen 200m"},
    {"id": "2", "sport": "Bike", "title": "GA1 Rad", "duration_min": 120, "tss": 85,
     "description": "2h Z2, 117-130 bpm, gleichmäßig"},
    {"id": "3", "sport": "Run", "title": "Koppellauf 20min", "duration_min": 20, "tss": 20,
     "description": "20 min direkt nach dem Rad, Z2"},
]


# ── Belastungslagen für den Periodisierer ────────────────────────────────────
# Gerechnet mit training_load.compute_pmc, nicht von Hand gesetzt.

LOAD_AUFBAU = {          # harter Block, TSB tief, Ramp im Rahmen
    "ctl": 78.4, "atl": 96.2, "tsb": -17.8, "ramp_7d": 3.1,
    "ctl_vor_28d": 68.0, "tss_7d": 690, "tss_28d": 2340, "tage_mit_daten": 24,
    "verlauf": [],
}
LOAD_UEBERLASTET = {     # Ramp Rate zu hoch, TSB sehr tief
    "ctl": 84.1, "atl": 118.7, "tsb": -34.6, "ramp_7d": 9.4,
    "ctl_vor_28d": 58.0, "tss_7d": 890, "tss_28d": 2980, "tage_mit_daten": 27,
    "verlauf": [],
}
LOAD_TAPER = {           # Umfang runter, Frische kommt
    "ctl": 71.2, "atl": 52.0, "tsb": 19.2, "ramp_7d": -4.8,
    "ctl_vor_28d": 82.0, "tss_7d": 310, "tss_28d": 1780, "tage_mit_daten": 21,
    "verlauf": [],
}
LOAD_DUENN = {           # kaum Daten — Kennzahlen unbrauchbar
    "ctl": 12.3, "atl": 18.1, "tsb": -5.8, "ramp_7d": 1.2,
    "ctl_vor_28d": 4.0, "tss_7d": 140, "tss_28d": 260, "tage_mit_daten": 3,
    "verlauf": [],
}

WOCHE_MIT_SCHLUESSELEINHEIT = [
    {"datum": "2026-07-26", "wochentag": "Sonntag", "ist_heute": True,
     "einheiten": [{"sport": "Run", "titel": "Schwellenlauf 4×8min",
                    "dauer_min": 60, "tss": 75}], "tss_summe": 75},
    {"datum": "2026-07-27", "wochentag": "Montag", "ist_heute": False,
     "einheiten": [], "tss_summe": 0},
    {"datum": "2026-07-28", "wochentag": "Dienstag", "ist_heute": False,
     "einheiten": [{"sport": "Swim", "titel": "Technik", "dauer_min": 45, "tss": 35}],
     "tss_summe": 35},
    {"datum": "2026-07-29", "wochentag": "Mittwoch", "ist_heute": False,
     "einheiten": [{"sport": "Bike", "titel": "GA1", "dauer_min": 90, "tss": 65}],
     "tss_summe": 65},
    {"datum": "2026-07-30", "wochentag": "Donnerstag", "ist_heute": False,
     "einheiten": [], "tss_summe": 0},
    {"datum": "2026-07-31", "wochentag": "Freitag", "ist_heute": False,
     "einheiten": [{"sport": "Run", "titel": "Lockerer Dauerlauf",
                    "dauer_min": 40, "tss": 35}], "tss_summe": 35},
    {"datum": "2026-08-01", "wochentag": "Samstag", "ist_heute": False,
     "einheiten": [{"sport": "Bike", "titel": "Lange Ausfahrt 4h",
                    "dauer_min": 240, "tss": 180}], "tss_summe": 180},
]

A_RACE_MALBORK = {"name": "Castle Triathlon Malbork", "date": "2026-09-06",
                  "priority": "A", "goal_total": "10:50"}

BLOCK_FAELLE = [
    {
        "name": "aufbau_43_tage_vor_a_rennen",
        "load": LOAD_AUFBAU, "woche": WOCHE_MIT_SCHLUESSELEINHEIT, "tage_bis_a": 43,
        "erwartung": {
            "phase": ["aufbau", "spitze"],
            "heute_rolle": ["schluesseleinheit"],
            "spielraum": ["halten", "ausbauen"],
            "warnung_leer": True,
        },
    },
    {
        "name": "ueberlastet_ramp_9_tsb_minus35",
        "load": LOAD_UEBERLASTET, "woche": WOCHE_MIT_SCHLUESSELEINHEIT, "tage_bis_a": 43,
        "erwartung": {
            "belastungsurteil": ["ueberlastet", "grenzwertig"],
            "spielraum": ["zuruecknehmen"],
            "warnung_leer": False,
        },
    },
    {
        "name": "taper_10_tage_vor_a_rennen",
        "load": LOAD_TAPER, "woche": WOCHE_MIT_SCHLUESSELEINHEIT, "tage_bis_a": 10,
        "erwartung": {
            "phase": ["taper", "wettkampfwoche"],
            "spielraum": ["halten", "zuruecknehmen"],
        },
    },
    {
        "name": "duenne_datenlage",
        "load": LOAD_DUENN, "woche": WOCHE_MIT_SCHLUESSELEINHEIT, "tage_bis_a": 43,
        "erwartung": {
            # Bei 3 Tagen Daten darf er keine Überlastung diagnostizieren
            "belastungsurteil": ["zu_wenig", "im_rahmen"],
        },
    },
]


CASES = [
    {
        "name": "gesund_mild_intervall",
        "koerper": KOERPER_GESUND, "weather": WETTER_MILD, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            "laufen_urteil": ["frei"],
            "badges_erlaubt": ["GO"],
        },
    },
    {
        "name": "achilles_rechts_5_von_10",
        "koerper": KOERPER_ACHILLES, "weather": WETTER_MILD, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            # Achilles 5/10 plus Waden 4/10 → Laufen darf nicht 'frei' sein
            "laufen_urteil": ["stop", "kein_tempo", "reduziert"],
            "badges_erlaubt": ["MOD", "SKIP"],
        },
    },
    {
        "name": "gewitter_streicht_outdoor",
        "koerper": KOERPER_GESUND, "weather": WETTER_GEWITTER, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            "wetter_gesamtlage": ["outdoor_gestrichen", "anpassen"],
            "laufen_empfehlung": ["indoor_wechsel", "gestrichen"],
            "badges_erlaubt": ["MOD", "SKIP"],
        },
    },
    {
        "name": "hitze_31_grad_drei_einheiten",
        "koerper": KOERPER_GESUND, "weather": WETTER_HITZE, "tp": TP_TAG_MIT_DREI,
        "sleep": None,
        "erwartung": {
            "wetter_gesamtlage": ["anpassen"],
            # Hallenbad/Schwimmen ist laut Prompt ausdrücklich nicht hitzebetroffen
            "schwimmen_empfehlung": ["outdoor_ok"],
            "laufen_empfehlung": ["zeitfenster", "indoor_wechsel"],
        },
    },
    {
        "name": "krank_neu_mittel_streicht_alles",
        "koerper": KOERPER_KRANK, "weather": WETTER_MILD, "tp": TP_TAG_MIT_DREI,
        "sleep": SLEEP_AUFFAELLIG,
        "erwartung": {
            "allgemein_gesamturteil": ["pause"],
            "badges_erlaubt": ["SKIP"],
        },
    },
    {
        "name": "fieber_allein_ohne_symptome_pause",
        "koerper": KOERPER_FIEBER, "weather": WETTER_MILD, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            "allgemein_gesamturteil": ["pause"],
            "badges_erlaubt": ["SKIP"],
        },
    },
]
