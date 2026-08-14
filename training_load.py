"""Belastungskennzahlen aus der TSS-Historie — Performance Management Chart.

Der TrainingPeaks-MCP liefert kein fertiges CTL/ATL/TSB, aber jedes
abgeschlossene Workout trägt einen TSS-Ist-Wert. Daraus lassen sich die Kennzahlen
mit den Standardformeln exakt nachrechnen:

    CTL(heute) = CTL(gestern) + (TSS(heute) - CTL(gestern)) / 42
    ATL(heute) = ATL(gestern) + (TSS(heute) - ATL(gestern)) / 7
    TSB(heute) = CTL(gestern) - ATL(gestern)

Bewusst kein Agent: das ist Arithmetik mit einer definierten Antwort. Ein
Modell könnte hier nur Zahlen halluzinieren.
"""
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CTL_TAGE = 42   # Fitness, langfristig
ATL_TAGE = 7    # Ermüdung, kurzfristig

# Länge des PMC-Fensters. CTL startet bei 0 und läuft sich erst ein, deshalb
# muss der Aufrufer **genauso viele Tage Historie mitliefern** wie hier
# iteriert wird — sonst zählen die fehlenden Tage als TSS 0 und drücken CTL
# nach unten (v2.7.13: 42 Tage Daten gegen 90 Tage Fenster = CTL 59 statt 89).
# 89 statt 90, weil der TP-MCP Zeiträume über 90 Tage ablehnt.
PMC_TAGE = 89


def _tss(w: dict) -> float:
    """TSS eines Workouts. Ist-Wert vor Planwert.

    Der TP-MCP liefert snake_case (`tss_actual`/`tss`/`tss_planned`), nicht die
    camelCase-Namen der TP-eigenen API — derselbe Irrtum wie in agents/analyst
    vor v2.7.9.
    """
    for key in ("tss_actual", "tss", "tss_planned"):
        try:
            wert = float(w.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if wert > 0:
            return wert
    return 0.0


def _tag(w: dict) -> str:
    return (w.get("date") or w.get("_day") or "")[:10]


def _dauer_min(w: dict):
    """Dauer in Minuten. Der MCP liefert Stunden als Bruchzahl."""
    for key in ("duration_actual", "duration_planned"):
        try:
            stunden = float(w.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if stunden > 0:
            return round(stunden * 60)
    return None


def tss_pro_tag(workouts: list) -> dict:
    """Summiert TSS je Datum. Ist-Werte haben Vorrang vor Planwerten."""
    pro_tag: dict = {}
    for w in workouts or []:
        tag = _tag(w)
        if not tag:
            continue
        tss = _tss(w)
        if tss > 0:
            pro_tag[tag] = pro_tag.get(tag, 0.0) + tss
    return pro_tag


def letzte_einheiten(workouts: list, bis: Optional[date] = None, tage: int = 10) -> list:
    """Was in den letzten Tagen tatsächlich absolviert wurde — mit Titeln.

    Der Periodisierer sah bisher nur TSS-Zahlen pro Tag. Ein Wettkampf, ein
    Testlauf und ein zäher Grundlagentag mit gleichem TSS sind darin nicht zu
    unterscheiden — genau daran ist die Einordnung „neun Tage Belastungsblock"
    nach einem Rennen gescheitert (v2.7.13).
    """
    bis = bis or date.today()
    ab = bis - timedelta(days=tage - 1)
    nach_tag: dict = {}
    for w in workouts or []:
        tag = _tag(w)
        if tag and ab.isoformat() <= tag <= bis.isoformat():
            nach_tag.setdefault(tag, []).append(w)

    ergebnis = []
    for i in range(tage):
        d = (ab + timedelta(days=i)).isoformat()
        einheiten = nach_tag.get(d, [])
        ergebnis.append({
            "datum": d,
            "einheiten": [
                {"sport": e.get("sport") or "?", "titel": e.get("title") or "",
                 "dauer_min": _dauer_min(e), "tss": round(_tss(e)) or None,
                 "distanz_km": e.get("distance_actual_km") or e.get("distance_planned_km")}
                for e in einheiten
            ],
            "tss_summe": round(sum(_tss(e) for e in einheiten)),
        })
    return ergebnis


def compute_pmc(tss_pro_tag_: dict, bis: Optional[date] = None, tage: int = PMC_TAGE) -> dict:
    """Rechnet CTL, ATL und TSB bis zum Stichtag hoch.

    Startet bei 0 und iteriert Tag für Tag — Tage ohne Training zählen als
    TSS 0 und lassen die Werte korrekt abklingen. Deshalb muss `tss_pro_tag_`
    den **gesamten** Zeitraum abdecken: fehlende Tage sind von echten Ruhetagen
    nicht zu unterscheiden und drücken CTL nach unten (siehe PMC_TAGE).
    """
    bis = bis or date.today()
    start = bis - timedelta(days=tage)
    ctl = atl = 0.0
    verlauf = []

    tag = start
    while tag <= bis:
        # TSB ist der Stand von gestern — vor der heutigen Einheit.
        tsb = ctl - atl
        tss = float(tss_pro_tag_.get(tag.isoformat(), 0.0))
        ctl += (tss - ctl) / CTL_TAGE
        atl += (tss - atl) / ATL_TAGE
        verlauf.append({"datum": tag.isoformat(), "tss": tss,
                        "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)})
        tag += timedelta(days=1)

    heute = verlauf[-1]
    vor_7 = verlauf[-8] if len(verlauf) >= 8 else verlauf[0]
    vor_28 = verlauf[-29] if len(verlauf) >= 29 else verlauf[0]

    return {
        "ctl": heute["ctl"],
        "atl": heute["atl"],
        "tsb": heute["tsb"],
        # Ramp Rate: CTL-Zuwachs pro Woche. Über ~7 gilt als riskant.
        "ramp_7d": round(heute["ctl"] - vor_7["ctl"], 1),
        "ctl_vor_28d": vor_28["ctl"],
        "tss_7d": round(sum(v["tss"] for v in verlauf[-7:]), 0),
        "tss_28d": round(sum(v["tss"] for v in verlauf[-28:]), 0),
        "tage_mit_daten": sum(1 for v in verlauf if v["tss"] > 0),
        "verlauf": verlauf[-14:],
    }


def wochenstruktur(workouts: list, ab: Optional[date] = None, tage: int = 7) -> list:
    """Fasst die geplanten Einheiten der kommenden Tage zusammen."""
    ab = ab or date.today()
    nach_tag: dict = {}
    for w in workouts or []:
        tag = _tag(w)
        if tag:
            nach_tag.setdefault(tag, []).append(w)

    _WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                   "Freitag", "Samstag", "Sonntag"]
    ergebnis = []
    for i in range(tage):
        d = ab + timedelta(days=i)
        einheiten = nach_tag.get(d.isoformat(), [])
        ergebnis.append({
            "datum": d.isoformat(),
            "wochentag": _WOCHENTAGE[d.weekday()],
            "ist_heute": d == ab,
            "einheiten": [
                {"sport": e.get("sport", "?"), "titel": e.get("title", ""),
                 "dauer_min": e.get("duration_min"), "tss": e.get("tss")}
                for e in einheiten
            ],
            "tss_summe": round(sum(float(e.get("tss") or 0) for e in einheiten), 0),
        })
    return ergebnis


def tage_bis(ziel_datum: str, ab: Optional[date] = None) -> Optional[int]:
    """Tage bis zu einem Renndatum. None wenn kein oder ungültiges Datum."""
    if not ziel_datum:
        return None
    try:
        return (date.fromisoformat(ziel_datum[:10]) - (ab or date.today())).days
    except ValueError:
        return None
