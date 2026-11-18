"""Gesetzliche Feiertage in Brandenburg, berechnet statt nachgeschlagen.

Blattmodul ohne I/O. Ostern wird über den Gauß-/Butcher-Algorithmus bestimmt,
alle beweglichen Feiertage ergeben sich als Abstand zu Ostern. Titel und
Beschreibung stehen hier und nur hier; `app.py` schreibt sie in den TP-Kalender.
"""
from datetime import date, timedelta
from typing import NamedTuple


class Feiertag(NamedTuple):
    datum: date
    titel: str
    beschreibung: str


def ostersonntag(jahr: int) -> date:
    """Gregorianisches Osterdatum (Anonymous-Gregorian-Algorithmus, Meeus/Jones/Butcher)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def feiertage_brandenburg(jahr: int) -> list[Feiertag]:
    """Alle Feiertage in Brandenburg für ein Jahr, chronologisch sortiert.

    Ostersonntag und Pfingstsonntag sind keine Werktage-Feiertage, werden hier aber
    mit aufgenommen, weil sie im Kalender trotzdem als freie Tage zählen.
    """
    ostern = ostersonntag(jahr)
    tage = [
        Feiertag(date(jahr, 1, 1), "✨ Neujahr", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(ostern - timedelta(days=2), "✝ Karfreitag", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(ostern, "✿ Ostersonntag", "Feiertag Brandenburg"),
        Feiertag(ostern + timedelta(days=1), "☘ Ostermontag", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(date(jahr, 5, 1), "✊ Tag der Arbeit", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(ostern + timedelta(days=39), "☁ Christi Himmelfahrt", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(ostern + timedelta(days=49), "★ Pfingstsonntag", "Feiertag Brandenburg"),
        Feiertag(ostern + timedelta(days=50), "★ Pfingstmontag", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(date(jahr, 10, 3), "⚑ Tag der Deutschen Einheit", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(date(jahr, 10, 31), "✎ Reformationstag", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(date(jahr, 12, 25), "❄ 1. Weihnachtstag", "Gesetzlicher Feiertag Brandenburg"),
        Feiertag(date(jahr, 12, 26), "✶ 2. Weihnachtstag", "Gesetzlicher Feiertag Brandenburg"),
    ]
    return sorted(tage, key=lambda f: f.datum)
