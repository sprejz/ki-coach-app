"""Ernährungsregeln nach Dauer.

Reine Tabellenlogik — deterministisch, kostenlos, auditierbar. Bewusst kein
Agent: die Regeln stehen exakt in athlete.json, ein Modell könnte hier nur
Mengen erfinden. Wird von app.py (Monolith-Pfad) und vom Orchestrator genutzt.
"""
from typing import Optional

# Die Sportart-Zuordnung liegt hier, weil nutrition.py ein Blattmodul ohne
# eigene Abhängigkeiten ist: orchestrator.py und app.py brauchen dieselbe
# Normalform, und eine zweite Kopie würde früher oder später auseinanderlaufen
# (genau der Fehler aus v2.7.15).
_SPORT_MAP = {
    "swim": "Schwimmen", "schwimm": "Schwimmen", "pool": "Schwimmen",
    "bike": "Rad", "rad": "Rad", "cycl": "Rad", "zwift": "Rad",
    "run": "Laufen", "lauf": "Laufen",
    "strength": "Kraft", "kraft": "Kraft",
}


def normalize_sport(sport: str) -> str:
    s = (sport or "").lower()
    for needle, name in _SPORT_MAP.items():
        if needle in s:
            return name
    return "Sonstiges"


def carbs_per_hour(nutrition: dict, sport: Optional[str] = None) -> int:
    """Kohlenhydrate pro Stunde — sportartabhängig.

    Beim Laufen ist die Magenverträglichkeit deutlich geringer als auf dem
    Rad: dieselbe Menge, die auf der Rolle problemlos durchgeht, führt im Lauf
    zu Magen-Darm-Problemen. Die Rate pro Sportart steht in athlete.json unter
    `carbs_per_hour_by_sport`; ohne Eintrag gilt die Basisrate.
    """
    basis = int(nutrition.get("carbs_per_hour_g", 90))
    if not sport:
        return basis
    pro_sport = nutrition.get("carbs_per_hour_by_sport") or {}
    return int(pro_sport.get(normalize_sport(sport), basis))


def _regel_fuer(duration_min: int, nutrition: dict) -> Optional[dict]:
    """Die Regel, deren Dauerfenster diese Einheit trifft."""
    for rule in nutrition.get("rules", []):
        lo = rule.get("duration_min_min", 0)
        hi = rule.get("duration_max_min")
        if duration_min >= lo and (hi is None or duration_min < hi):
            return rule
    return None


def _rund5(wert: float) -> int:
    """Auf 5 g runden — Küchenwaagen-Genauigkeit, keine Scheingenauigkeit."""
    return int(round(wert / 5) * 5)


def mix_totals(duration_min: Optional[int], nutrition: dict,
               sport: Optional[str] = None, is_hot: bool = False) -> Optional[dict]:
    """Absolute Mengen für die **ganze** Einheit, zum Selbstanmischen.

    Die Regeln nennen nur Raten pro Stunde. Wer sein Getränk selbst mischt,
    braucht aber die Gesamtmenge pro Flasche — und die Aufteilung des
    Mischverhältnisses auf die beiden Zucker.
    """
    if not duration_min or duration_min <= 0:
        return None
    # Nur wo die Regel überhaupt Carbs während der Einheit vorsieht. Diese
    # Prüfung steht hier und nicht beim Aufrufer, sonst bekommt die nächste
    # neue Aufrufstelle wieder eine Mischanleitung für 20 Minuten Stabi.
    regel = _regel_fuer(duration_min, nutrition)
    if not (regel and regel.get("carbs_during")):
        return None
    stunden = duration_min / 60
    carbs = carbs_per_hour(nutrition, sport) * stunden

    ratio = nutrition.get("mix_ratio") or {}
    anteil_m = float(ratio.get("maltodextrin", 0))
    anteil_f = float(ratio.get("fruchtzucker", 0))
    summe = anteil_m + anteil_f

    salz_pro_h = nutrition.get("salt_heat_per_hour" if is_hot else "salt_per_hour", 1)
    fluid_pro_h = nutrition.get("fluid_heat_per_hour_ml" if is_hot else "fluid_per_hour_ml", 600)

    # Erst die Gesamtmenge runden, dann aufteilen — und den zweiten Zucker als
    # Rest rechnen, damit die beiden Teile exakt die Summe ergeben. Zweimal
    # unabhängig zu runden ergäbe 165 + 80 = 250 auf dem Zettel.
    carbs_g = _rund5(carbs)
    malto = _rund5(carbs_g * anteil_m / summe) if summe else None

    return {
        "dauer_min": int(duration_min),
        "carbs_g": carbs_g,
        "carbs_pro_h": carbs_per_hour(nutrition, sport),
        "fluid_pro_h": int(fluid_pro_h),
        # Der Maltodextrin-Anteil als Bruch, damit die Flaschen-Rezeptur ihn
        # nicht aus den gerundeten Gesamtmengen zurückrechnen muss.
        "malto_anteil": (anteil_m / summe) if summe else None,
        # Ohne mix_ratio in athlete.json bleibt die Aufteilung leer, statt sie
        # aus dem Freitext von `mix` zu raten.
        "maltodextrin_g": malto,
        "fruchtzucker_g": (carbs_g - malto) if malto is not None else None,
        "saltstick": max(1, round(float(salz_pro_h) * stunden)),
        "fluid_ml": int(round(float(fluid_pro_h) * stunden / 50) * 50),
        "is_hot": bool(is_hot),
    }


def bottle_split(totals: dict, bottle_ml: Optional[int]) -> Optional[dict]:
    """Rezeptur für **eine volle Flasche** plus die Anzahl, die die Einheit braucht.

    Bezugspunkt ist die **Konzentration**, nicht die Gesamtmenge: der Athlet
    füllt immer dieselbe Flasche, also muss in jede dieselbe Menge — und die
    Dauer bestimmt nur, wie viele davon er anrührt. (Die erste Fassung hat die
    Gesamtmenge auf Flaschen verteilt und daraus krumme Teilfüllungen wie
    „3 × 680 ml" gemacht, die niemand so anrührt.)

    Damit hängt die Rezeptur pro Flasche nur von Sportart und Hitze ab — beides
    steckt bereits in `totals` — und ist über alle Einheiten hinweg dieselbe.

    Saltstick bleibt bewusst draußen: das sind Kapseln, die separat genommen
    und nicht in der Flasche aufgelöst werden.
    """
    if not bottle_ml or bottle_ml <= 0 or not totals or not totals.get("fluid_ml"):
        return None
    bottle_ml = int(bottle_ml)
    # Aus den **Stundenraten**, nicht aus den gerundeten Gesamtmengen: sonst
    # käme je nach Dauer mal 140, mal 145 g pro Flasche heraus und die
    # Rezeptur wäre nicht mehr dieselbe.
    if totals.get("carbs_pro_h") and totals.get("fluid_pro_h"):
        konzentration = totals["carbs_pro_h"] / totals["fluid_pro_h"]
    else:
        konzentration = totals["carbs_g"] / totals["fluid_ml"]
    carbs = _rund5(konzentration * bottle_ml)
    # Verhältnis aus der bereits berechneten Aufteilung, nicht erneut aus
    # mix_ratio — sonst gäbe es zwei Wahrheiten über dieselbe Zahl.
    anteil = totals.get("malto_anteil")
    if anteil is None and totals.get("maltodextrin_g") and totals.get("carbs_g"):
        anteil = totals["maltodextrin_g"] / totals["carbs_g"]
    malto = _rund5(carbs * anteil) if anteil else None

    voll, rest_ml = divmod(int(totals["fluid_ml"]), bottle_ml)
    return {
        "groesse_ml": bottle_ml,
        # Pro voller Flasche:
        "carbs_g": carbs,
        "maltodextrin_g": malto,
        "fruchtzucker_g": (carbs - malto) if malto is not None else None,
        # Bedarf der Einheit:
        "voll": voll,
        "rest_ml": int(round(rest_ml / 50) * 50),
        "rest_carbs_g": _rund5(konzentration * rest_ml),
    }


def format_mix(totals: dict) -> str:
    """Eine Zeile für Karte und TP-Beschreibung."""
    h, m = divmod(totals["dauer_min"], 60)
    dauer = f"{h}:{m:02d} h" if h else f"{m} min"
    if totals["maltodextrin_g"] and totals["fruchtzucker_g"]:
        mischung = (f"{totals['maltodextrin_g']} g Maltodextrin + "
                    f"{totals['fruchtzucker_g']} g Fruchtzucker")
    else:
        mischung = f"{totals['carbs_g']} g Carbs"
    return (f"🥤 Selbst anrühren für {dauer}: {mischung} "
            f"({totals['carbs_g']} g Carbs) · {totals['saltstick']} Saltstick · "
            f"{totals['fluid_ml']} ml")


def nutrition_for_duration(duration_min: Optional[int], nutrition: dict,
                           sport: Optional[str] = None, is_hot: bool = False) -> str:
    """Findet die passende Ernährungsregel für eine Einheit dieser Dauer."""
    if not duration_min:
        return ""
    rule = _regel_fuer(duration_min, nutrition)
    if not rule:
        return ""
    parts = []
    if rule.get("before"):
        parts.append(f"Vorher: {rule['before']}")
    if rule.get("during"):
        during = rule["during"]
        # Sportartabhängige Rate: der Regeltext nennt die Basisrate, beim
        # Laufen gilt eine niedrigere.
        rate = carbs_per_hour(nutrition, sport)
        basis = int(nutrition.get("carbs_per_hour_g", 90))
        if rule.get("carbs_during") and rate != basis:
            during = during.replace(f"{basis}g Carbs/h", f"{rate}g Carbs/h")
        parts.append(f"Während: {during}")
    if rule.get("after"):
        parts.append(f"Nachher: {rule['after']}")
    text = " | ".join(parts)
    # mix_totals prüft selbst, ob die Regel Carbs während der Einheit vorsieht.
    totals = mix_totals(duration_min, nutrition, sport, is_hot)
    return f"{text} | {format_mix(totals)}" if totals else text
