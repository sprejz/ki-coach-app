"""Tägliche Energiebilanz: Aufnahme (TP-Ernährung) gegen Verbrauch (Grundumsatz + Training).

Reine Funktionen ohne I/O — die Abfragen (TP-MCP, Strava) liegen in app.py bzw. strava.py.
Saldo = Aufnahme − Verbrauch. Negativ = Defizit.
"""
from typing import Optional

# Darunter ist der Grundumsatz-Wert vermutlich unvollständig (z. B. Uhr noch nicht
# synchronisiert). Am 17.10. stand dort 889 kcal bei nur 192 Schritten.
RMR_MIN_PLAUSIBEL = 1200


def aufnahme_pro_tag(nutrition: dict) -> dict:
    """{datum: kcal} aus der Antwort von tp_get_nutrition."""
    out: dict = {}
    for eintrag in (nutrition or {}).get("nutrition", []) or []:
        tag = (eintrag.get("nutritionDate") or "")[:10]
        kcal = eintrag.get("calories")
        if tag and kcal is not None:
            out[tag] = out.get(tag, 0.0) + float(kcal)
    return out


def rmr_pro_tag(metrics: dict) -> dict:
    """{datum: Grundumsatz-kcal} aus der Antwort von tp_get_metrics (Feld „RMR")."""
    out: dict = {}
    for m in (metrics or {}).get("metrics", []) or []:
        tag = (m.get("timeStamp") or "")[:10]
        for detail in m.get("details", []) or []:
            if detail.get("label") == "RMR" and detail.get("value") is not None:
                out[tag] = float(detail["value"])
    return out


def bilanz(tag: str, aufnahme: Optional[float], rmr: Optional[float],
           training: Optional[float], ziel_defizit: Optional[float],
           rmr_quelle: str = "TP") -> dict:
    """Ein Tag. `training` = None heißt: nicht ermittelbar (Strava nicht verbunden)
    — dann gibt es keinen Saldo, statt einen zu raten. 0 heißt: kein Training."""
    hinweise = []
    rmr_ok = rmr is not None and rmr >= RMR_MIN_PLAUSIBEL
    if aufnahme is None:
        hinweise.append("keine Aufnahme erfasst")
    if not rmr_ok:
        hinweise.append("Grundumsatz unvollständig")
    if training is None:
        hinweise.append("Training nicht ermittelbar")

    verbrauch = None
    saldo = None
    if rmr_ok and training is not None:
        verbrauch = rmr + training
        if aufnahme is not None:
            saldo = aufnahme - verbrauch

    ergebnis = {
        "datum": tag,
        "aufnahme": round(aufnahme) if aufnahme is not None else None,
        "grundumsatz": round(rmr) if rmr is not None else None,
        "training": round(training) if training is not None else None,
        "verbrauch": round(verbrauch) if verbrauch is not None else None,
        "saldo": round(saldo) if saldo is not None else None,
        "ziel_defizit": ziel_defizit,
        "rmr_quelle": rmr_quelle,
        "hinweise": hinweise,
    }
    if saldo is not None and ziel_defizit:
        ergebnis["ziel_erreicht"] = saldo <= -float(ziel_defizit)
    return ergebnis


def notiz_text(b: dict) -> str:
    """Kurztext für die TP-Notiz — bewusst ohne Emoji (TP kann keine Zeichen außerhalb der BMP)."""
    def kcal(v):
        return f"{v} kcal" if v is not None else "unbekannt"

    zeilen = [
        f"Aufnahme: {kcal(b['aufnahme'])}",
        f"Training: {kcal(b['training'])}",
        f"Verbrauch gesamt: {kcal(b['verbrauch'])}",
    ]
    if b["saldo"] is not None:
        vorzeichen = "+" if b["saldo"] > 0 else "−"
        zeile = f"Saldo: {vorzeichen}{abs(b['saldo'])} kcal"
        if b["ziel_defizit"]:
            zeile += f" (Ziel: −{b['ziel_defizit']} kcal)"
        zeilen.append(zeile)
    if b["hinweise"]:
        zeilen.append("Hinweis: " + ", ".join(b["hinweise"]))
    return "\n".join(zeilen)


def notiz_titel(b: dict) -> str:
    """Titel ohne Datum — das Notiz-Datum in TP reicht. Mit Kennzeichen, sobald
    das Defizit das Ziel erreicht (ziel_erreicht)."""
    if b.get("ziel_erreicht"):
        return "Energiebilanz ⚡ Ziel erreicht"
    return "Energiebilanz"
