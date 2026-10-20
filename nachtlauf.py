"""Nächtlicher Lauf um 23:00 Berlin: Wetter-Backfill + Energiebilanz-Notiz.

Läuft als Railway-Cron-Service (gleiches Image, Start: `python nachtlauf.py`,
Cron `0 21 * * *` in UTC). Der Cron ist bewusst nur EIN Trigger:
- Sommerzeit: 21:00 UTC = 23:00 Berlin → sofort starten.
- Winterzeit: 21:00 UTC = 22:00 Berlin → bis 23:00 Berlin warten.
- Verspätete Starts (bis 23:59 Berlin oder später) laufen trotzdem sofort,
  statt wie beim GitHub-Cron ersatzlos zu verfallen.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
ZIEL_STUNDE = 23
# Mehr als so viel Vorlauf vor 23 Uhr gilt als Fehlstart (z. B. Cron zu früh) → nichts tun.
MAX_WARTEN = timedelta(hours=2)
BASIS_URL = "https://ki-coach-app-production.up.railway.app"


def wartezeit(jetzt: datetime) -> float:
    """Sekunden bis 23:00 Berlin (0 wenn schon nach 23:00). Negativ = zu früh für heute."""
    ziel = jetzt.replace(hour=ZIEL_STUNDE, minute=0, second=0, microsecond=0)
    return (ziel - jetzt).total_seconds()


def post(pfad: str, timeout: int) -> dict:
    """POST gegen die App. Wirft bei HTTP- oder Netzfehlern, damit Railway den Lauf rot zeigt."""
    req = urllib.request.Request(BASIS_URL + pfad, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def main() -> int:
    jetzt = datetime.now(BERLIN)
    warte = wartezeit(jetzt)
    # Nach 23 Uhr (warte < 0) läuft er sofort: verspäteter Cron, lieber spät als gar nicht.
    if warte > MAX_WARTEN.total_seconds():
        print(f"Berlin ist {jetzt:%H:%M}, zu früh für den Nachtlauf. Nichts zu tun.")
        return 0
    if warte > 0:
        print(f"Berlin ist {jetzt:%H:%M}, warte {int(warte)} s bis 23:00.")
        time.sleep(warte)

    tag = datetime.now(BERLIN).date().isoformat()
    print(f"Nachtlauf für {tag} startet.")
    fehler = []

    try:
        print("Backfill:", post("/api/admin/backfill-weather?days=3", timeout=280))
    except Exception as e:
        fehler.append(f"Backfill: {e}")

    try:
        print("Energiebilanz:", post(f"/api/energiebilanz/notiz?day={tag}", timeout=120))
    except Exception as e:
        fehler.append(f"Energiebilanz: {e}")

    for f in fehler:
        print("FEHLER", f, file=sys.stderr)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
