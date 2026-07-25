"""Offline-Prüfungen: kein API-Call, keine Kosten.

Prüft, dass die Schemas für Structured Outputs zulässig sind und dass die
User-Messages die relevanten Werte tatsächlich enthalten.

    .venv/bin/python -m tests.test_offline
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import head_coach, medic, weather  # noqa: E402
from orchestrator import normalize_sport  # noqa: E402
from tests import fixtures as fx  # noqa: E402

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


print("\n=== Schemas ===")
for name, schema in [("medic", medic.SCHEMA), ("weather", weather.SCHEMA),
                     ("head_coach", head_coach.SCHEMA)]:
    vorher = len(fehler)
    validiere_schema(schema, name)
    pruefe(len(fehler) == vorher, f"{name}.SCHEMA ist gültig")

print("\n=== Frontend-Vertrag ===")
hc_props = set(head_coach.SCHEMA["properties"])
erwartet = {"status", "status_text", "sportarten", "autosleep_summary",
            "wetter_hinweis", "prep"}
pruefe(erwartet <= hc_props, f"Chefcoach liefert alle Felder, die index.html liest: {sorted(erwartet)}")

sp_props = set(head_coach.SCHEMA["properties"]["sportarten"]["items"]["properties"])
erwartet_sp = {"sport", "badge", "details", "beschreibung", "ernaehrung",
               "tp_struktur", "distanz_m"}
pruefe(erwartet_sp <= sp_props, f"Einheiten liefern alle Felder für applyToTP: {sorted(erwartet_sp)}")

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
    medic={"gesamturteil": "eingeschraenkt", "leitsymptom": "Achilles rechts 5/10",
           "sportarten": [{"sport": "Laufen", "urteil": "stop", "grund": "Achilles 5/10"}],
           "alternativen": ["Aquajogging"], "erholung": "HRV unter Baseline"},
    wetter={"gesamtlage": "anpassen", "hinweis": "31 °C",
            "sportarten": [{"sport": "Laufen", "empfehlung": "zeitfenster",
                            "anpassung": "Pace 5% langsamer", "zeitfenster": "vor 09:00"}],
            "versorgung": "750 ml/h"},
    tp_workouts=fx.TP_LAUF_INTERVALL, tag="Sonntag, 26.07.2026",
)
pruefe("**stop**" in hc_in, "Chefcoach sieht das medizinische stop-Urteil")
pruefe("Malbork" in hc_in, "Chefcoach sieht das A-Rennen")
pruefe("4×8 min @ 5:20/km" in hc_in, "Chefcoach sieht die Original-Beschreibung aus TP")
pruefe("90g Carbs/h" in hc_in, "Chefcoach sieht die Ernährungsregeln")

print(f"\n{'=' * 40}")
if fehler:
    print(f"FEHLGESCHLAGEN — {len(fehler)} Problem(e):")
    for f in fehler:
        print(f"  - {f}")
    sys.exit(1)
print("Alle Offline-Prüfungen bestanden.")
