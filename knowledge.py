"""Wissensdatenbank für die Recherche-Ergebnisse (v2.9.0).

Reine Blattlogik ohne File-I/O — Laden/Speichern von knowledge.json liegt in
app.py, genau wie bei load_athlete()/load_baseline().

Ein Fund wird erst wirksam (accepted_context liefert ihn), wenn er den Status
'akzeptiert' trägt. Das passiert auf zwei Wegen:
  - automatisch, wenn der Recherche-Agent selbst Konfidenz 'hoch' vergibt
    (AUTO_ACCEPT_KONFIDENZ) — eine deterministische Regel im Code, keine
    Zustimmung pro Fund. Bewusst so entschieden: mehrere unabhängige Studien
    oder eine Metaanalyse (das ist per Prompt-Definition, was 'hoch' bedeutet,
    siehe agents/research/research.md) sind ein tragfähigeres Fundament als
    eine Einzelstudie — das Risiko einer schlecht interpretierten Quelle bleibt
    dadurch begrenzt, ohne dass Hendrik jeden guten Fund einzeln bestätigen muss.
  - manuell im Profil-Tab, für alles mit Konfidenz 'mittel'/'niedrig'.
`entschieden_von` ('system'|'hendrik') hält fest, welcher Weg es war — sichtbar
im Profil-Tab, damit nie unklar ist, warum ein Fund schon wirksam ist.
"""
import uuid
from datetime import datetime, timezone

# Nur bei dieser Konfidenz übernimmt der Code selbst, ohne Zustimmung.
AUTO_ACCEPT_KONFIDENZ = "hoch"


def new_entry(*, thema: str, titel: str, aussage: str, quelle: str,
              konfidenz: str, betrifft: str) -> dict:
    """Baut einen neuen Fund. status startet bei 'vorschlag' — add_findings()
    entscheidet, ob er sofort automatisch akzeptiert wird."""
    return {
        "id": uuid.uuid4().hex[:10],
        "thema": thema,
        "titel": titel,
        "aussage": aussage,
        "quelle": quelle,
        "konfidenz": konfidenz,
        "betrifft": betrifft,
        "status": "vorschlag",
        "erstellt_am": datetime.now(timezone.utc).isoformat(),
        "entschieden_am": None,
        "entschieden_von": None,
    }


def _set_status(eintraege: list, entry_id: str, status: str, entschieden_von: str) -> bool:
    for e in eintraege:
        if e.get("id") == entry_id:
            e["status"] = status
            e["entschieden_am"] = datetime.now(timezone.utc).isoformat()
            e["entschieden_von"] = entschieden_von
            return True
    return False


def accept(eintraege: list, entry_id: str, *, entschieden_von: str = "hendrik") -> bool:
    """Markiert einen Fund als akzeptiert. False, wenn die id unbekannt ist."""
    return _set_status(eintraege, entry_id, "akzeptiert", entschieden_von)


def reject(eintraege: list, entry_id: str, *, entschieden_von: str = "hendrik") -> bool:
    """Wie accept(), status='abgelehnt'."""
    return _set_status(eintraege, entry_id, "abgelehnt", entschieden_von)


def add_findings(eintraege: list, *, thema: str, funde: list) -> list:
    """Baut aus den Roh-Funden eines Recherche-Laufs neue Einträge, hängt sie
    an `eintraege` an und wendet die Auto-Accept-Regel an. Gibt die neu
    angehängten Einträge zurück (nicht die ganze Liste)."""
    neue = []
    for fund in funde:
        eintrag = new_entry(
            thema=thema, titel=fund.get("titel", ""), aussage=fund.get("aussage", ""),
            quelle=fund.get("quelle", ""), konfidenz=fund.get("konfidenz", "niedrig"),
            betrifft=fund.get("betrifft", ""),
        )
        eintraege.append(eintrag)
        if eintrag["konfidenz"] == AUTO_ACCEPT_KONFIDENZ:
            accept(eintraege, eintrag["id"], entschieden_von="system")
        neue.append(eintrag)
    return neue


def accepted_context(eintraege: list) -> str:
    """Rendert alle akzeptierten Einträge als Markdown-Bulletliste für den
    Chefcoach-Prompt. Leerstring, wenn nichts akzeptiert ist — der Aufrufer
    kann das direkt als Wahrheitswert prüfen."""
    akzeptiert = [e for e in eintraege if e.get("status") == "akzeptiert"]
    if not akzeptiert:
        return ""
    zeilen = [
        f"- **{e.get('titel', '')}**: {e.get('aussage', '')} (Quelle: {e.get('quelle', '')})"
        for e in akzeptiert
    ]
    return "\n".join(zeilen)
