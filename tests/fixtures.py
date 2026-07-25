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
}

KOERPER_ACHILLES = {
    "waden": 4, "knie": 1, "achilles_l": 1, "achilles_r": 5,
    "muedigkeit": 3, "muskelkater": ["Beine leicht"], "symptome": "keine",
}

KOERPER_KRANK = {
    "waden": 1, "knie": 1, "achilles_l": 0, "achilles_r": 0,
    "muedigkeit": 4, "muskelkater": ["keine"], "symptome": "neu mittel",
}

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


CASES = [
    {
        "name": "gesund_mild_intervall",
        "koerper": KOERPER_GESUND, "weather": WETTER_MILD, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            "medic_gesamturteil": ["frei"],
            "laufen_urteil": ["frei"],
            "badges_erlaubt": ["GO"],
        },
    },
    {
        "name": "achilles_rechts_5_von_10",
        "koerper": KOERPER_ACHILLES, "weather": WETTER_MILD, "tp": TP_LAUF_INTERVALL,
        "sleep": None,
        "erwartung": {
            "medic_gesamturteil": ["eingeschraenkt"],
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
            "medic_gesamturteil": ["frei"],
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
            "medic_gesamturteil": ["pause"],
            "badges_erlaubt": ["SKIP"],
        },
    },
]
