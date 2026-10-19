"""Tests für energiebilanz.py — reine Funktionen, keine Netzwerkzugriffe.

Eigenständig lauffähig: python3 -m tests.test_energiebilanz
Die Zahlen stammen aus den echten TP-Antworten vom 13.–18.10.2026.
"""
import sys

from energiebilanz import (aufnahme_pro_tag, rmr_pro_tag, bilanz,
                           notiz_text, notiz_titel)

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
check("Notiz-Titel ohne Datum (kein Ziel erreicht)", notiz_titel(bilanz("2026-10-14", 3000.0, 1932.8, 1069.0, 500)) == "Energiebilanz")
check("Notiz-Titel kennzeichnet, sobald das Defizit über 500 kcal liegt",
      notiz_titel(bilanz("2026-10-13", 2455.0, 2700.0, 1069.0, 500, "Atemanalyse")) == "Energiebilanz ✔ Ziel erreicht")
check("Notiz-Titel ohne Kennzeichen bei Überschuss",
      notiz_titel(bilanz("2026-10-14", 3328.13, 1445.7, 531.0, 500)) == "Energiebilanz")

b = bilanz("2026-10-13", 2455.0, 2700.0, 1069.0, 500, "Atemanalyse")
text = notiz_text(b)
check("gemessener Grundumsatz wird in der Notiz als Atemanalyse ausgewiesen",
      "Grundumsatz (Atemanalyse): 2700 kcal" in text)
check("gemessener Grundumsatz gibt einen Saldo mit dem Wert, nicht der TP-Schätzung",
      b["saldo"] == 2455 - (2700 + 1069))
b = bilanz("2026-10-13", 2455.0, 1932.8, 1069.0, 500)
check("TP-Grundumsatz bleibt ohne Herkunftsangabe in der Notiz", "(Atemanalyse)" not in notiz_text(b))

print(f"\n{ok} Prüfungen bestanden.")
