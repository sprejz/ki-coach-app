"""Live-Test der drei Agents gegen die Fixtures. Kostet echte API-Token.

Braucht ANTHROPIC_API_KEY — entweder in der Umgebung oder in einer lokalen
.env-Datei im Projektverzeichnis (ANTHROPIC_API_KEY=sk-ant-...).

    .venv/bin/python -m tests.test_live              # alle Fälle
    .venv/bin/python -m tests.test_live achilles     # nur passende Fälle
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env laden, bevor irgendein Agent-Modul den Key liest
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for zeile in _env.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#") and "=" in zeile:
            k, _, v = zeile.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY fehlt.\n")
    print("Lege eine .env im Projektverzeichnis an (steht in .gitignore):")
    print("    echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env\n")
    print("Den Key findest du in Railway unter Variables.")
    sys.exit(2)

from agents.base import USAGE, AgentError, kosten  # noqa: E402
from orchestrator import run_check  # noqa: E402
from tests import fixtures as fx  # noqa: E402

ATHLET = {
    "name": "Hendrik", "weight_kg": 84, "ftp_watt": 286,
    "run_threshold_pace": "5:20", "css_per_100m": "2:20",
    "swim_outdoor_min_celsius": 15,
    "nutrition": {
        "mix": "Maltodextrin 19 + Fruchtzucker 2:1",
        "carbs_per_hour_g": 90, "fluid_per_hour_ml": 600,
        "fluid_heat_per_hour_ml": 750, "salt_per_hour": 1, "salt_heat_per_hour": 2,
        "rules": [
            {"duration_max_min": 60, "before": "Nüchtern oder kleines Frühstück",
             "during": "Wasser reicht", "after": "Normale Mahlzeit binnen 1h"},
            {"duration_min_min": 60, "duration_max_min": 90,
             "before": "Leichtes Frühstück 2h vorher", "during": "Wasser reicht",
             "after": "Mahlzeit binnen 1h"},
            {"duration_min_min": 90, "duration_max_min": 180,
             "before": "KH-reiches Frühstück 2h vorher",
             "during": "90g Carbs/h + 1 Saltstick/h",
             "after": "25g Protein + Carbs binnen 30 min"},
        ],
    },
}
A_RACE = {"name": "Castle Triathlon Malbork", "date": "2026-09-06", "goal_total": "10:50"}

GRUEN, ROT, GELB, GRAU, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def kuerze(text: str, n: int = 300) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + " …"


async def lauf_fall(fall: dict) -> dict:
    name = fall["name"]
    print(f"\n{'═' * 72}\n{name}\n{'═' * 72}")

    t0 = time.monotonic()
    hc = await run_check(
        athlete=ATHLET, a_race=A_RACE, baseline=None,
        koerper=fall["koerper"], weather_data=fall["weather"],
        tp_workouts=fall["tp"], sleep=fall.get("sleep"),
        tag="Sonntag, 26.07.2026",
    )
    dauer = time.monotonic() - t0
    med = hc["_agents"]["medic"]
    wet = hc["_agents"]["wetter"]

    print(f"\n{GRAU}── Sportmediziner{RESET}")
    print(f"   Gesamturteil: {med['gesamturteil']}")
    if med.get("leitsymptom"):
        print(f"   Leitsymptom:  {med['leitsymptom']}")
    for s in med["sportarten"]:
        print(f"   {s['sport']:<11} {s['urteil']:<11} {kuerze(s['grund'], 150)}")
    if med.get("alternativen"):
        print(f"   Alternativen: {', '.join(med['alternativen'])}")

    print(f"\n{GRAU}── Wetter-Taktiker{RESET}")
    print(f"   Gesamtlage: {wet['gesamtlage']}")
    print(f"   Hinweis:    {kuerze(wet['hinweis'], 150)}")
    for s in wet["sportarten"]:
        extra = " ".join(x for x in [s.get("anpassung", ""), s.get("zeitfenster", "")] if x)
        print(f"   {s['sport']:<11} {s['empfehlung']:<15} {kuerze(extra, 130)}")

    print(f"\n{GRAU}── Chefcoach + Architekt ({dauer:.1f}s gesamt){RESET}")
    print(f"   Status: {hc['status']} — {hc['status_text']}")
    for s in hc["sportarten"]:
        farbe = {"GO": GRUEN, "MOD": GELB, "SKIP": ROT}.get(s["badge"], "")
        quelle = "Architekt" if s["badge"] == "MOD" else "Original übernommen"
        print(f"\n   {farbe}[{s['badge']}]{RESET} {s['sport']}  {GRAU}({quelle}){RESET}")
        print(f"      Hinweis:      {kuerze(s['details'], 200)}")
        if s.get("_begruendung"):
            print(f"      Begründung:   {kuerze(s['_begruendung'], 160)}")
        if s["beschreibung"]:
            print(f"      Beschreibung: {kuerze(s['beschreibung'], 300)}")
        if s.get("ernaehrung"):
            print(f"      Ernährung:    {kuerze(s['ernaehrung'], 140)}")
        if s.get("tp_struktur"):
            n = len(s["tp_struktur"].get("steps", []))
            print(f"      TP-Struktur:  {n} Blöcke ({s['tp_struktur'].get('primaryIntensityMetric')})")
        if s.get("distanz_m"):
            print(f"      Distanz:      {s['distanz_m']} m")
    print(f"\n   Prep: {kuerze(hc['prep'], 200)}")

    # Erwartungen prüfen
    e = fall["erwartung"]
    probleme = []

    def hol(liste, sport, feld):
        return next((x[feld] for x in liste if x["sport"] == sport), None)

    if "medic_gesamturteil" in e and med["gesamturteil"] not in e["medic_gesamturteil"]:
        probleme.append(f"medic.gesamturteil={med['gesamturteil']}, erwartet {e['medic_gesamturteil']}")
    if "wetter_gesamtlage" in e and wet["gesamtlage"] not in e["wetter_gesamtlage"]:
        probleme.append(f"wetter.gesamtlage={wet['gesamtlage']}, erwartet {e['wetter_gesamtlage']}")
    for sport, key in [("Laufen", "laufen_urteil")]:
        if key in e:
            u = hol(med["sportarten"], sport, "urteil")
            if u not in e[key]:
                probleme.append(f"medic[{sport}]={u}, erwartet {e[key]}")
    for sport, key in [("Laufen", "laufen_empfehlung"), ("Schwimmen", "schwimmen_empfehlung")]:
        if key in e:
            u = hol(wet["sportarten"], sport, "empfehlung")
            if u not in e[key]:
                probleme.append(f"wetter[{sport}]={u}, erwartet {e[key]}")
    if "badges_erlaubt" in e:
        schlecht = [s["badge"] for s in hc["sportarten"] if s["badge"] not in e["badges_erlaubt"]]
        if schlecht:
            probleme.append(f"badges {schlecht} nicht in {e['badges_erlaubt']}")

    if probleme:
        print(f"\n   {ROT}✗ Erwartung verletzt:{RESET}")
        for p in probleme:
            print(f"     - {p}")
    else:
        print(f"\n   {GRUEN}✓ Alle Erwartungen erfüllt{RESET}")

    return {"name": name, "probleme": probleme,
            "dauer": dauer, "badges": [s["badge"] for s in hc["sportarten"]]}


async def main():
    filter_ = sys.argv[1].lower() if len(sys.argv) > 1 else None
    faelle = [c for c in fx.CASES if not filter_ or filter_ in c["name"]]
    if not faelle:
        print(f"Kein Fall passt zu {filter_!r}. Verfügbar: {[c['name'] for c in fx.CASES]}")
        return 2

    print(f"Live-Test: {len(faelle)} Fall/Fälle, Modell Haiku 4.5")
    ergebnisse = []
    for fall in faelle:
        try:
            ergebnisse.append(await lauf_fall(fall))
        except AgentError as err:
            print(f"\n   {ROT}✗ Agent-Fehler: {err}{RESET}")
            ergebnisse.append({"name": fall["name"], "probleme": [str(err)],
                               "dauer": 0, "badges": []})

    print(f"\n{'═' * 72}\nZusammenfassung\n{'═' * 72}")
    for r in ergebnisse:
        marke = f"{GRUEN}✓{RESET}" if not r["probleme"] else f"{ROT}✗{RESET}"
        badges = "/".join(r["badges"]) or "—"
        print(f" {marke} {r['name']:<34} {r['dauer']:>5.1f}s  {badges}")

    tok_in = sum(u["in"] for u in USAGE)
    tok_out = sum(u["out"] for u in USAGE)
    print(f"\n {len(USAGE)} Agent-Aufrufe · {tok_in:,} in / {tok_out:,} out Token")
    print(f" Kosten: ${kosten():.4f} gesamt, ${kosten() / len(ergebnisse):.4f} pro Check")

    fehlgeschlagen = [r for r in ergebnisse if r["probleme"]]
    if fehlgeschlagen:
        print(f"\n {ROT}{len(fehlgeschlagen)} von {len(ergebnisse)} Fällen verletzen Erwartungen.{RESET}")
        return 1
    print(f"\n {GRUEN}Alle {len(ergebnisse)} Fälle bestanden.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
