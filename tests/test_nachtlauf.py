"""Tests für nachtlauf.py — Zeitlogik, keine Netzwerkzugriffe.

Eigenständig lauffähig: python3 -m tests.test_nachtlauf
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from datetime import date
from nachtlauf import wartezeit, nachtlauf_tag, MAX_WARTEN, MAX_VERSPAETET

BERLIN = ZoneInfo("Europe/Berlin")
fehler = 0


def check(name, ok):
    global fehler
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        fehler += 1


# Sommerzeit: Cron um 21:00 UTC = 23:00 Berlin → sofort, Wartezeit 0
jetzt = datetime(2026, 7, 15, 23, 0, tzinfo=BERLIN)
check("Sommer 23:00 Berlin: keine Wartezeit", wartezeit(jetzt) == 0)

# Winterzeit: Cron um 21:00 UTC = 22:00 Berlin → eine Stunde warten
jetzt = datetime(2026, 12, 15, 22, 0, tzinfo=BERLIN)
check("Winter 22:00 Berlin: 3600 s warten", wartezeit(jetzt) == 3600)

# Verspätet nach 23 Uhr: negativ → sofort laufen
jetzt = datetime(2026, 10, 19, 23, 40, tzinfo=BERLIN)
check("Verspätet 23:40: negativ, läuft sofort", wartezeit(jetzt) < 0)

# Zu früh (19 Uhr): mehr als MAX_WARTEN → nichts tun
jetzt = datetime(2026, 10, 19, 19, 0, tzinfo=BERLIN)
check("19:00 Berlin: zu früh", wartezeit(jetzt) > MAX_WARTEN.total_seconds())

# Regression: GitHub-Cron kommt nach Mitternacht (01:45 Berlin am 24.10.). Der Lauf
# gehört zur Nacht vom 23.10. und muss sofort laufen, statt 21 h „zu früh" zu melden.
jetzt = datetime(2026, 10, 24, 1, 45, tzinfo=BERLIN)
check("01:45 Berlin am Folgetag: Nachtlauf läuft sofort", wartezeit(jetzt) < 0)
check("01:45 Berlin am Folgetag: gehört zur Nacht vom Vortag", nachtlauf_tag(jetzt) == date(2026, 10, 23))

# Tagsüber nach einem verspäteten Lauf: nichts tun
jetzt = datetime(2026, 10, 24, 10, 0, tzinfo=BERLIN)
check("10:00 Berlin: Nachtlauf des Vortags zu lange her", wartezeit(jetzt) < -MAX_VERSPAETET.total_seconds())

# Vormittags vor Mitternacht: Tag selbst ist die Nacht, die noch kommt
jetzt = datetime(2026, 10, 23, 12, 0, tzinfo=BERLIN)
check("12:00 Berlin: Nachtlauf-Tag ist heute", nachtlauf_tag(jetzt) == date(2026, 10, 23))

print(f"\n{'alle Tests grün' if not fehler else str(fehler) + ' Fehler'}")
sys.exit(1 if fehler else 0)
