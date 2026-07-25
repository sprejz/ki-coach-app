"""Belastungskennzahlen aus der TSS-Historie — Performance Management Chart.

Der TrainingPeaks-MCP liefert kein fertiges CTL/ATL/TSB, aber jedes
abgeschlossene Workout trägt `tssActual`. Daraus lassen sich die Kennzahlen
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


def tss_pro_tag(workouts: list) -> dict:
    """Summiert TSS je Datum. Ist-Werte haben Vorrang vor Planwerten."""
    pro_tag: dict = {}
    for w in workouts or []:
        tag = (w.get("workoutDay") or w.get("date") or w.get("_day") or "")[:10]
        if not tag:
            continue
        tss = w.get("tssActual") or w.get("tss") or w.get("tssPlanned") or 0
        try:
            tss = float(tss)
        except (TypeError, ValueError):
            continue
        if tss > 0:
            pro_tag[tag] = pro_tag.get(tag, 0.0) + tss
    return pro_tag


def compute_pmc(tss_pro_tag_: dict, bis: Optional[date] = None, tage: int = 90) -> dict:
    """Rechnet CTL, ATL und TSB bis zum Stichtag hoch.

    Startet bei 0 und iteriert Tag für Tag — Tage ohne Training zählen als
    TSS 0 und lassen die Werte korrekt abklingen.
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
        tag = (w.get("workoutDay") or w.get("date") or w.get("_day") or "")[:10]
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
