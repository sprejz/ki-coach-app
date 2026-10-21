"""Tests für energiebilanz.py — reine Funktionen, keine Netzwerkzugriffe.

Eigenständig lauffähig: python3 -m tests.test_energiebilanz
Die Zahlen stammen aus den echten TP-Antworten vom 13.–18.10.2026.
"""
import sys

from energiebilanz import (aufnahme_pro_tag, rmr_pro_tag, bilanz,
                           notiz_text, notiz_titel, notiz_aktion)

NUTRITION = {"nutrition": [
    {"nutritionDate": "2026-10-13T00:00:00", "calories": 2455.0},
    {"nutritionDate": "2026-10-14T00:00:00", "calories": 3328.13},
    {"nutritionDate": "2026-10-17T00:00:00", "calories": 3473.3},
]}

METRICS = {"metrics": [
    {"timeStamp": "2026-10-13T00:00:00", "details": [
        {"label": "Sleep Hours", "value": 5.8},
        {"label": "RMR", "value": 1932.8},
    ]},
    {"timeStamp": "2026-10-17T00:00:00", "details": [
        {"label": "Steps", "value": 192},
        {"label": "RMR", "value": 888.8},
    ]},
]}

ok = 0


def check(name, bedingung):
    global ok
    if not bedingung:
        print(f"FEHLER  {name}")
        sys.exit(1)
    ok += 1
    print(f"  ok    {name}")


print("=== Aufnahme und Grundumsatz aus TP ===")
a = aufnahme_pro_tag(NUTRITION)
check("Aufnahme je Tag aus nutritionDate", a["2026-10-13"] == 2455.0)
check("Tage ohne Eintrag fehlen statt 0 zu sein", "2026-10-15" not in a)
r = rmr_pro_tag(METRICS)
check("RMR wird aus dem Feld 'RMR' gelesen, nicht aus Schlaf oder Schritten",
      r["2026-10-13"] == 1932.8)
check("Unvollständiger RMR bleibt als Wert erhalten (Bewertung passiert später)",
      r["2026-10-17"] == 888.8)

print("\n=== Saldo ===")
b = bilanz("2026-10-13", 2455.0, 1932.8, 1069.0, 500)
check("Verbrauch = Grundumsatz + Training", b["verbrauch"] == 3002)
check("Saldo = Aufnahme − Verbrauch (negativ = Defizit)", b["saldo"] == -547)
check("Ziel 500 erreicht bei Saldo −547", b["ziel_erreicht"] is True)
check("keine Hinweise bei vollständigem Tag", b["hinweise"] == [])

b = bilanz("2026-10-14", 3328.13, 1445.7, 531.0, 500)
check("Überschuss ist positiv", b["saldo"] > 0)
check("Ziel nicht erreicht bei Überschuss", b["ziel_erreicht"] is False)

print("\n=== Lücken werden benannt, nicht geraten ===")
b = bilanz("2026-10-17", 3473.3, 888.8, 1474.0, 500)
check("unvollständiger Grundumsatz: kein Saldo", b["saldo"] is None)
check("unvollständiger Grundumsatz: Hinweis steht da",
      "Grundumsatz unvollständig" in b["hinweise"])
b = bilanz("2026-10-13", 2455.0, 1932.8, None, 500)
check("Training unbekannt (Strava aus): kein Saldo", b["saldo"] is None)
check("Training unbekannt: Hinweis steht da",
      "Training nicht ermittelbar" in b["hinweise"])
b = bilanz("2026-10-13", 2455.0, 1932.8, 0.0, 500)
check("Training 0 heißt kein Training, nicht unbekannt", b["saldo"] is not None)
b = bilanz("2026-10-13", None, 1932.8, 0.0, 500)
check("ohne Aufnahme kein Saldo, aber Verbrauch steht da",
      b["saldo"] is None and b["verbrauch"] == 1933)

print("\n=== Notiz ===")
b = bilanz("2026-10-13", 2455.0, 1932.8, 1069.0, 500)
text = notiz_text(b)
check("Notiz nennt Aufnahme, Verbrauch und Saldo",
      "Aufnahme: 2455 kcal" in text and "Saldo: −547 kcal (Ziel: −500 kcal)" in text)
check("Notiz enthält kein Zeichen außerhalb der BMP (TP lehnt das ab)",
      all(ord(c) <= 0xFFFF for c in text))
check("Notiz-Titel ohne Datum (ohne Vergleich mit dem Ziel)", notiz_titel(bilanz("2026-10-14", None, 1932.8, 1069.0, 500)) == "Energiebilanz")
check("Notiz-Titel kennzeichnet, sobald das Defizit über 500 kcal liegt",
      notiz_titel(bilanz("2026-10-13", 2455.0, 2700.0, 1069.0, 500, "Atemanalyse")) == "Energiebilanz ⚡ Ziel erreicht")
check("Notiz-Titel mit ⚠, wenn das Ziel nicht erreicht wurde",
      notiz_titel(bilanz("2026-10-14", 3328.13, 1445.7, 531.0, 500)) == "Energiebilanz ⚠ Ziel nicht erreicht")
check("Notiz-Titel ohne Kennzeichen ohne Ziel-Vergleich (keine Daten)",
      notiz_titel(bilanz("2026-10-14", None, 1445.7, 531.0, 500)) == "Energiebilanz")

b = bilanz("2026-10-13", 2455.0, 2700.0, 1069.0, 500, "Atemanalyse")
text = notiz_text(b)
check("Notiz zeigt keine Grundumsatz-Zeile mehr",
      "Grundumsatz" not in text)
check("gemessener Grundumsatz gibt einen Saldo mit dem Wert, nicht der TP-Schätzung",
      b["saldo"] == 2455 - (2700 + 1069))
b = bilanz("2026-10-13", 2455.0, 1932.8, 1069.0, 500)
check("Notiz enthält auch mit TP-Grundumsatz keine Grundumsatz-Zeile", "Grundumsatz" not in notiz_text(b))

print("\n=== Bestehende Notiz wird aktualisiert, nicht stehen gelassen ===")
frueh = {"id": 98939749, "title": "Energiebilanz",
         "description": "Aufnahme: unbekannt\\nTraining: 0 kcal"}
check("keine Notiz → anlegen", notiz_aktion([], "Energiebilanz", "x") == ("create", None))
check("fremde Notiz mit dem Wort nur im Text bleibt außen vor",
      notiz_aktion([{"id": 1, "title": "Sonstiges", "description": "Energiebilanz kommt später"}],
                   "Energiebilanz", "x") == ("create", None))
check("frühe Notiz mit anderem Inhalt → aktualisieren",
      notiz_aktion([frueh], "Energiebilanz ⚡ Ziel erreicht", "Aufnahme: 2789 kcal") == ("update", "98939749"))
check("identische Notiz → unverändert, kein Schreibzugriff",
      notiz_aktion([{"id": 5, "title": "Energiebilanz", "description": "gleich"}],
                   "Energiebilanz", "gleich") == ("unchanged", "5"))
check("Notiz mit gesetzter Kennzeichen-Titel wird als eigene erkannt",
      notiz_aktion([{"id": 7, "title": "Energiebilanz ⚠ Ziel nicht erreicht", "description": "alt"}],
                   "Energiebilanz", "neu") == ("update", "7"))

print("\n=== Wetter-Notizen nutzen denselben Abgleich mit eigenem Präfix ===")
check("Wetter-Notiz wird über Präfix 'Wetter' gefunden, Energiebilanz-Notiz nicht",
      notiz_aktion([{"id": 9, "title": "Energiebilanz", "description": "x"}],
                   "Wetter 6–15 °C", "y", praefix="Wetter") == ("create", None))
check("bestehende Wetter-Notiz mit anderem Inhalt → aktualisieren",
      notiz_aktion([{"id": 11, "title": "Wetter 5–12 °C", "description": "alt"}],
                   "Wetter 6–15 °C", "neu", praefix="Wetter") == ("update", "11"))

print(f"\n{ok} Prüfungen bestanden.")
