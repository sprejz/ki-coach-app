"""Orchestrator für den Coach-Ablauf.

Der Kontrollfluss liegt hier, nicht bei den Agents — die Agents reden nicht
miteinander, sie liefern typisierte Urteile an den Orchestrator zurück.

    Allgemeinmediziner ┐
    Mediziner          ┤
    Wetter             ├─(parallel)─→ Chefcoach ─→ Architekt (nur MOD, parallel) ─→ Vertrag
    Periodisierer      ┘                              └─→ Ernährungsberater (nur mit Grund, pro Einheit)

Sagt der Allgemeinmediziner `gesamturteil: pause`, wird das hart im Code
durchgesetzt: Chefcoach und Architekt werden übersprungen, jede geplante
Sportart wird deterministisch auf SKIP gesetzt. Diese Regel ist zu
sicherheitskritisch (Herzmuskelentzündungsrisiko), um sie allein der
Prompt-Disziplin eines Modells zu überlassen.

Deterministisch, ohne Modell:
  - GO-Einheiten übernehmen die Original-Beschreibung unverändert
  - SKIP-Einheiten brauchen keine Beschreibung
  - Ernährung kommt aus der Tabelle in athlete.json, nach fertiger Dauer
  - CTL/ATL/TSB werden in training_load.py ausgerechnet, nicht geschätzt
  - Schlaf-Flags, Baseline, Wetterschwellen, tp_apply liegen ohnehin in Code
  - Allgemeinmediziner-Pause → All-SKIP, siehe oben

Der Ernährungsberater (`agents/fueling/fueling.py`) läuft pro Einheit NUR bei Hitze/
Kälte, chronischen Befunden, Renntag oder Dauer ≥90min — sonst bleibt die
Ernährung der reine Tabellenstring, ohne Modell-Call. Er ergänzt einen
Kontextsatz, erfindet aber nie eigene Mengen. Ein Fehler dort wird lokal
abgefangen, nicht an den Monolith-Fallback durchgereicht — ein fehlender
Zusatzsatz darf nicht den ganzen Check kosten.
"""
import asyncio
import logging
from typing import Callable, Optional

from agents import (
    allgemeinmedic, architect, architect_bike, architect_run, architect_swim, fueling, head_coach, medic,
    periodizer, weather,
)
from agents.base import HAIKU
# normalize_sport lebt in nutrition.py (Blattmodul), damit app.py dieselbe
# Zuordnung nutzen kann, ohne den Agent-Pfad zu importieren. Der Re-Export
# hier haelt orchestrator.normalize_sport als Aufrufweg erhalten.
from nutrition import normalize_sport, nutrition_for_duration  # noqa: F401

logger = logging.getLogger(__name__)

# Sport-Agenten für Lauf/Rad/Schwimm (agents/architect_run, _bike, _swim);
# Kraft/Sonstiges fallen auf den generischen agents/architect zurück.
_ARCHITECT_BY_SPORT = {
    "Laufen": architect_run.run,
    "Rad": architect_bike.run,
    "Schwimmen": architect_swim.run,
}

# Derselbe Schlüssel wie in translations.py → T["agenten"], damit das Frontend
# den Namen nicht aus der Sportart erraten muss.
_ARCHITECT_KEY_BY_SPORT = {
    "Laufen": "architect_run",
    "Rad": "architect_bike",
    "Schwimmen": "architect_swim",
}


# Stufen, die `run_check` über den progress-Callback meldet. Der Orchestrator
# kennt bewusst keine UI-Texte — er liefert Schlüssel, das Frontend die Worte.
STUFEN = ("spezialisten", "chefcoach", "architekt")


def _wetter_zeile(w: dict) -> str:
    return (f"{w.get('description', '?')}, "
            f"{w.get('temp_min', '?')}–{w.get('temp_max', '?')} °C, "
            f"Regen {w.get('rain_prob', 0)} %")


async def _baue_einheit(*, entscheidung: dict, workout: Optional[dict], athlete: dict,
                        wetter_zeile: str, model: str, weather_data: Optional[dict] = None,
                        a_race: Optional[dict] = None, tage_bis_a: Optional[int] = None) -> dict:
    """Baut einen Eintrag im Frontend-Vertrag aus Entscheidung + Original-Workout."""
    badge = entscheidung.get("badge", "GO")
    # Der Chefcoach formuliert die Sportart frei — "Run", "Lauf", "Laufen (LIT)"
    # oder mit angehängtem Leerzeichen sind alle möglich, das Schema lässt jeden
    # String zu. Für Dispatch und Agentenkontext zählt deshalb nur die
    # normalisierte Form; angezeigt wird weiter, was der Chefcoach geschrieben
    # hat (sonst würde aus "Golf" ein "Sonstiges" auf der Karte).
    sport_label = entscheidung.get("sport", "")
    sport = normalize_sport(sport_label)
    workout = workout or {}
    orig_desc = (workout.get("description") or "").strip()
    dauer = workout.get("duration_min")
    beschreibung, tp_struktur, distanz_m = orig_desc, None, None

    architekt_key = None
    if badge == "MOD":
        # Nur hier läuft der Architekt. Lauf/Rad/Schwimm haben eigene
        # Disziplin-Agenten, alles andere (Kraft/Sonstiges) den Fallback.
        architekt_key = _ARCHITECT_KEY_BY_SPORT.get(sport, "architect")
        architekt_fn = _ARCHITECT_BY_SPORT.get(sport, architect.run)
        gebaut = await asyncio.to_thread(
            architekt_fn, athlete=athlete, workout=workout,
            auftrag={"begruendung": entscheidung.get("begruendung", ""),
                     "anpassung": entscheidung.get("anpassung", {})},
            wetter_zeile=wetter_zeile, sport=sport, model=model,
        )
        beschreibung = gebaut["beschreibung"]
        tp_struktur = gebaut.get("tp_struktur")
        distanz_m = gebaut.get("distanz_m")
        dauer = max(20, int(gebaut.get("dauer_min") or dauer or 20))
    elif badge == "SKIP":
        beschreibung = ""

    # Ernährung deterministisch aus der fertigen Dauer — kein Modell.
    # Sportart und Hitze gehen mit ein: beim Laufen liegt die verträgliche
    # Carb-Rate niedriger als auf dem Rad, bei Hitze steigen Salz und Menge.
    #
    # Auch bei SKIP (v2.7.20): über den "Trotzdem"-Button kann die Einheit
    # doch stattfinden, und dann braucht sie die Mengen. Grundlage ist die
    # geplante Originaldauer — genau die würde er dann absolvieren. Der
    # Ernährungsberater bleibt für SKIP trotzdem außen vor (siehe unten): ein
    # Modell-Call für eine gestrichene Einheit wäre der Kostendisziplin nach
    # nicht zu rechtfertigen.
    ernaehrung = nutrition_for_duration(
        dauer, athlete.get("nutrition", {}), sport=sport,
        is_hot=bool((weather_data or {}).get("is_hot")),
    )

    # Kontextsensitive Ergänzung — läuft NUR mit einem Grund, kein Modell ohne
    # Anlass (gleiche Disziplin wie beim Periodisierer: kein Call ohne
    # belastbaren Input). Die Basiszahlen oben bleiben davon unberührt.
    wd = weather_data or {}
    is_hot, is_cold = bool(wd.get("is_hot")), bool(wd.get("is_cold"))
    # "keine"/"keine bekannt" sind die im Profil üblichen Platzhalter für
    # "nichts hinterlegt" — als truthy-String würden sie sonst jeden Tag
    # einen Claude-Call auslösen, ohne dass es einen echten Grund gibt.
    _roh_chronisch = (athlete.get("chronische_befunde") or "").strip().lower()
    chronisch = athlete.get("chronische_befunde") if _roh_chronisch not in (
        "", "keine", "keine bekannt", "nichts", "-", "none"
    ) else None
    ist_renntag = tage_bis_a == 0
    lang = bool(dauer) and dauer >= 90
    ernaehrung_von_berater = False
    if badge in ("GO", "MOD") and ernaehrung and (is_hot or is_cold or chronisch or lang or ist_renntag):
        try:
            zusatz = await asyncio.to_thread(
                fueling.run, basis=ernaehrung, sport=sport, dauer_min=dauer, badge=badge,
                is_hot=is_hot, is_cold=is_cold, temp_max=wd.get("temp_max"),
                chronische_befunde=chronisch, ist_renntag=ist_renntag,
                rennname=(a_race or {}).get("name"), model=model,
            )
            if zusatz.get("relevant") and zusatz.get("hinweis"):
                ernaehrung = f"{ernaehrung} — {zusatz['hinweis']}"
                ernaehrung_von_berater = True
        except Exception as e:
            # Ein fehlender Zusatzsatz darf nie den ganzen Check auf den
            # Monolith umleiten — anders als bei medic/weather/architect.
            logger.warning("fueling-Agent fehlgeschlagen, Basis-Ernährung bleibt bestehen: %s", e)

    # Der Chefcoach schreibt oft die TP-Sportart hin ("Bike", "Run"). Die drei
    # Disziplinen plus Kraft werden deshalb angezeigt wie im Rest der App;
    # alles, was normalize_sport nicht kennt ("Golf", "Brick"), bleibt
    # wortwörtlich stehen, statt zu "Sonstiges" zu verarmen.
    anzeige = sport if sport != "Sonstiges" else (sport_label or sport)
    return {
        "sport": anzeige,
        # Wer die Einheit ausformuliert hat, sagt der Orchestrator explizit.
        # Bis v2.7.14 riet das Frontend es sich aus `sport` zusammen und lag
        # bei jeder Abweichung vom Wort "Laufen"/"Rad"/"Schwimmen" daneben —
        # und schrieb im Monolith-Pfad sogar einen Architekten hin, der gar
        # nicht gelaufen war. None heißt: kein Architekt beteiligt.
        "architekt": architekt_key,
        "badge": badge,
        "details": entscheidung.get("details", ""),
        "beschreibung": beschreibung,
        "ernaehrung": ernaehrung,
        "ernaehrung_von_berater": ernaehrung_von_berater,
        "tp_struktur": tp_struktur,
        "distanz_m": distanz_m,
        "_begruendung": entscheidung.get("begruendung", ""),
    }


async def run_check(
    *,
    athlete: dict,
    a_race: Optional[dict],
    baseline: Optional[dict],
    koerper: dict,
    weather_data: dict,
    tp_workouts: Optional[list] = None,
    sleep: Optional[dict] = None,
    wasser_temp=None,
    tag: str = "morgen",
    load: Optional[dict] = None,
    woche: Optional[list] = None,
    tage_bis_a: Optional[int] = None,
    model: str = HAIKU,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Führt den kompletten Check aus und liefert den Frontend-Vertrag.

    Der Aufrufer hängt nur noch `weather` und ggf. `sleep_flags` an.

    `progress` wird vor jeder Stufe mit einem Schlüssel aus STUFEN gerufen —
    der Check läuft 11–19 s, ohne Rückmeldung wäre das ein toter Spinner. Ein
    Fehler im Callback darf den Check nie kippen.
    """
    tp_workouts = tp_workouts or []

    def melde(stufe: str) -> None:
        if progress is None:
            return
        try:
            progress(stufe)
        except Exception as e:          # pragma: no cover — reine Anzeige
            logger.warning("progress-Callback fehlgeschlagen (%s): %s", stufe, e)

    sportarten = list(dict.fromkeys(
        normalize_sport(w.get("sport", "")) for w in tp_workouts
    )) or [normalize_sport(s) for s in koerper.get("geplante_einheiten", [])]
    sportarten = [s for s in dict.fromkeys(sportarten) if s]
    titel = [w.get("title", "") for w in tp_workouts if w.get("title")]
    wetter_zeile = _wetter_zeile(weather_data)

    # Stufe 1: die Spezialisten sind voneinander unabhängig → parallel.
    # asyncio.to_thread, weil das anthropic-SDK hier synchron aufgerufen wird.
    # Keyed statt positionsbasiert, damit der bedingte Periodisierer-Task das
    # Zuordnen der übrigen Ergebnisse nicht fragil verschiebt.
    melde("spezialisten")
    aufgaben = {
        "medic": asyncio.to_thread(
            medic.run, koerper=koerper, sportarten=sportarten,
            sleep=sleep, baseline=baseline, model=model,
        ),
        "weather": asyncio.to_thread(
            weather.run, weather=weather_data, sportarten=sportarten, titel=titel,
            swim_min_c=athlete.get("swim_outdoor_min_celsius", 15),
            wasser_temp=wasser_temp, tag=tag, model=model,
        ),
        # Läuft unconditional — Krankheit/Fieber sind immer relevant, anders
        # als der Periodisierer hat dieser Agent keine TP-Datenabhängigkeit.
        "allgemein": asyncio.to_thread(
            allgemeinmedic.run, koerper=koerper, sportarten=sportarten,
            chronische_befunde=athlete.get("chronische_befunde"),
            sleep=sleep, baseline=baseline, model=model,
        ),
    }
    # Der Periodisierer läuft nur mit Belastungsdaten — ohne TP-Historie hätte
    # er nichts zu beurteilen und würde Zahlen erfinden.
    mit_block = bool(load)
    if mit_block:
        aufgaben["block"] = asyncio.to_thread(
            periodizer.run, load=load, woche=woche or [], a_race=a_race,
            naechste_rennen=athlete.get("races"), tage_bis_a=tage_bis_a, model=model,
        )

    ergebnisse = dict(zip(aufgaben.keys(), await asyncio.gather(*aufgaben.values())))
    medic_result = ergebnisse["medic"]
    weather_result = ergebnisse["weather"]
    allgemein_result = ergebnisse["allgemein"]
    block_result = ergebnisse.get("block")

    logger.info(
        "orchestrator: medic=ok wetter=%s allgemein=%s block=%s sportarten=%s",
        weather_result.get("gesamtlage"), allgemein_result.get("gesamturteil"),
        f"{block_result.get('phase')}/{block_result.get('heute_rolle')}" if block_result else "—",
        sportarten,
    )

    # Sicherheitsregel: Krankheit/Fieber im Pause-Bereich überschreibt alles,
    # hart im Code statt per Prompt-Disziplin — Chefcoach/Architekt entfallen.
    if allgemein_result.get("gesamturteil") == "pause":
        melde("chefcoach")  # UI erwartet die Stufenfolge, auch ohne Modell-Call
        leitbefund = allgemein_result.get("leitbefund") or "ärztlicher Befund"
        grund_by_sport = {s.get("sport"): s.get("grund", "") for s in allgemein_result.get("sportarten", [])}
        ziel_sportarten = sportarten or [normalize_sport(w.get("sport", "")) for w in tp_workouts]
        ergebnisse_skip = await asyncio.gather(*[
            _baue_einheit(
                entscheidung={
                    "sport": s, "badge": "SKIP",
                    "details": f"Pause: {leitbefund}",
                    "begruendung": grund_by_sport.get(s, leitbefund),
                    "anpassung": {},
                },
                workout=tp_workouts[i] if i < len(tp_workouts) else None,
                athlete=athlete, wetter_zeile=wetter_zeile, model=model,
                weather_data=weather_data, a_race=a_race, tage_bis_a=tage_bis_a,
            )
            for i, s in enumerate(ziel_sportarten)
        ])
        logger.warning(
            "orchestrator: Allgemeinmediziner gesamturteil=pause — harter STOP, "
            "Chefcoach/Architekt übersprungen (%s)", leitbefund,
        )
        return {
            "status": "red",
            "status_text": f"Pause – {leitbefund}",
            "sportarten": list(ergebnisse_skip),
            "autosleep_summary": None,
            "wetter_hinweis": wetter_zeile,
            "prep": "Kein Training heute. Erhole dich, beobachte die Symptome, bei Verschlechterung ärztlich abklären.",
            "_agents": {"medic": medic_result, "wetter": weather_result, "block": block_result,
                        "allgemein": allgemein_result},
            "_chefcoach_ran": False,
        }

    # Stufe 2: der Chefcoach entscheidet — ohne auszuformulieren.
    melde("chefcoach")
    entscheidung = await asyncio.to_thread(
        head_coach.run,
        athlete=athlete, a_race=a_race, medic=medic_result, wetter=weather_result,
        allgemein=allgemein_result, tp_workouts=tp_workouts, tag=tag, block=block_result, model=model,
    )

    # Stufe 3: der Architekt formuliert die MOD-Einheiten aus — parallel.
    # Ohne MOD läuft hier kein Modell, dann ist die Stufe auch keine Meldung wert.
    einheiten = entscheidung.get("sportarten", [])
    if any(e.get("badge") == "MOD" for e in einheiten):
        melde("architekt")
    ergebnisse = await asyncio.gather(*[
        _baue_einheit(
            entscheidung=e,
            workout=tp_workouts[i] if i < len(tp_workouts) else None,
            athlete=athlete, wetter_zeile=wetter_zeile, model=model,
            weather_data=weather_data, a_race=a_race, tage_bis_a=tage_bis_a,
        )
        for i, e in enumerate(einheiten)
    ])

    n_mod = sum(1 for e in einheiten if e.get("badge") == "MOD")
    logger.info("orchestrator: %d Einheiten, davon %d über den Architekten",
                len(ergebnisse), n_mod)

    return {
        "status": entscheidung.get("status", "green"),
        "status_text": entscheidung.get("status_text", ""),
        "sportarten": list(ergebnisse),
        "autosleep_summary": entscheidung.get("autosleep_summary"),
        "wetter_hinweis": entscheidung.get("wetter_hinweis", ""),
        "prep": entscheidung.get("prep", ""),
        "_agents": {"medic": medic_result, "wetter": weather_result, "block": block_result,
                    "allgemein": allgemein_result},
        "_chefcoach_ran": True,
    }
