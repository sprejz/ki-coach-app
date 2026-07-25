"""Ernährungsregeln nach Dauer.

Reine Tabellenlogik — deterministisch, kostenlos, auditierbar. Bewusst kein
Agent: die Regeln stehen exakt in athlete.json, ein Modell könnte hier nur
Mengen erfinden. Wird von app.py (Monolith-Pfad) und vom Orchestrator genutzt.
"""
from typing import Optional


def nutrition_for_duration(duration_min: Optional[int], nutrition: dict) -> str:
    """Findet die passende Ernährungsregel für eine Einheit dieser Dauer."""
    if not duration_min:
        return ""
    for rule in nutrition.get("rules", []):
        lo = rule.get("duration_min_min", 0)
        hi = rule.get("duration_max_min")
        if duration_min >= lo and (hi is None or duration_min < hi):
            parts = []
            if rule.get("before"):
                parts.append(f"Vorher: {rule['before']}")
            if rule.get("during"):
                parts.append(f"Während: {rule['during']}")
            if rule.get("after"):
                parts.append(f"Nachher: {rule['after']}")
            return " | ".join(parts)
    return ""
