"""MCP-Server für den KI Coach — macht den Coach in Claude Desktop und Claude Code abfragbar.

Zwei Betriebsarten, **dieselben Tools**:

- **stdio** (Default) — läuft lokal auf dem Mac. Keine offene Fläche, kein Token.
- **streamable-http** (`MCP_TRANSPORT=http`) — eigener Railway-Service, aus dem
  Internet erreichbar. **Erfordert `MCP_TOKEN`**, sonst startet der Server nicht:
  ohne Token hätte jeder Zugriff auf die Gesundheitsdaten und könnte über
  `coach_frage` den Anthropic-Key verbrennen.

Läuft absichtlich **nicht** in app.py mit: `mcp` verlangt ein neueres `starlette`,
als `fastapi 0.111` erlaubt. Ein gemeinsames Image würde einen FastAPI-Sprung in
der App erzwingen, die morgens um 6 über echtes Training entscheidet. Eigener
Service heißt: die App wird nicht angefasst, und Abschalten ist ein Klick.

Zwei Sorten Tools:
  - **Datentools** (`training`, `belastung`, `erholung`, `wetter`, `profil`,
    `einheiten_historie`) liefern Rohdaten. Darüber denkt das Modell in Claude
    Desktop/Code selbst nach — das ist ein stärkeres Modell als das Haiku hinter
    dem App-Chat.
  - **`coach_frage`** fragt den Coach der App selbst. Der antwortet mit dem
    getunten Sportmediziner-Prompt aus translations.py, dafür über Haiku.

Start lokal (stdio):
    python coach_mcp.py

Start als Web-Service:
    MCP_TRANSPORT=http MCP_TOKEN=<geheim> PORT=8000 python coach_mcp.py

Einrichten: siehe CLAUDE.md → MCP-Server.
"""
import json
import os
import secrets
import sys

import httpx
from mcp.server.fastmcp import FastMCP

COACH_URL = os.environ.get(
    "COACH_URL", "https://ki-coach-app-production.up.railway.app"
).rstrip("/")
TIMEOUT = float(os.environ.get("COACH_MCP_TIMEOUT", "60"))

# stateless_http: jeder Request steht für sich. Hinter dem Railway-Proxy ist das
# robuster als serverseitige Sessions, und die Tools brauchen keinen Zustand.
mcp = FastMCP("ki-coach", stateless_http=True)


async def _get(pfad: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{COACH_URL}{pfad}", params=params or None)
    r.raise_for_status()
    return r.json()


async def _post(pfad: str, daten: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{COACH_URL}{pfad}", json=daten)
    r.raise_for_status()
    return r.json()


def _tag_normalisieren(tag: str) -> str:
    """Die App kennt nur today/tomorrow — deutsche Eingaben darauf abbilden."""
    t = (tag or "today").strip().lower()
    if t in ("morgen", "tomorrow"):
        return "tomorrow"
    if t in ("heute", "today", ""):
        return "today"
    raise ValueError(
        f"'{tag}' nicht unterstützt — die App liefert nur 'heute' oder 'morgen'. "
        "Für weiter entfernte Tage nutze coach_frage, der Chat erkennt Wochentage "
        "bis 30 Tage voraus."
    )


@mcp.tool()
async def training(tag: str = "heute") -> str:
    """Den geplanten TrainingPeaks-Trainingsplan abrufen.

    Nutze dies, wenn nach dem Training, dem Plan oder den Einheiten für heute
    oder morgen gefragt wird. Liefert Sportart, Titel, Dauer, TSS und
    Beschreibung je Einheit.

    Args:
        tag: "heute" oder "morgen".
    """
    daten = await _get("/api/tp/workouts", day=_tag_normalisieren(tag))
    if not daten.get("available"):
        return "TrainingPeaks ist nicht angebunden (TP_MCP_URL fehlt in Railway)."
    if daten.get("loading"):
        return ("Die TrainingPeaks-Daten werden gerade nachgeladen und sind in "
                "etwa einer Minute da. Bitte gleich nochmal fragen.")
    if not daten.get("workouts"):
        return f"Für {daten.get('date')} ist keine Einheit geplant (Ruhetag)."
    return json.dumps(daten, ensure_ascii=False, indent=2)


@mcp.tool()
async def belastung() -> str:
    """Die aktuelle Belastungslage abrufen: CTL, ATL, TSB, Ramp Rate, Wochenstruktur.

    Nutze dies für Fragen zu Form, Frische, Müdigkeit, Trainingsumfang, ob eine
    harte Einheit sinnvoll ist, oder zum Abstand zum A-Rennen. Die Werte sind
    deterministisch aus 42 Tagen TSS-Historie gerechnet, nicht geschätzt.

    Auslegung: TSB deutlich negativ = ermüdet, um 0 = ausgeglichen, positiv =
    frisch/formgeladen. Ramp Rate über etwa 8 CTL/Woche gilt als riskant.
    """
    daten = await _get("/api/load")
    if not daten.get("available"):
        return ("Keine Belastungsdaten — TrainingPeaks liefert keine TSS-Historie "
                "(TP_MCP_URL fehlt oder der MCP ist nicht erreichbar).")
    return json.dumps(daten, ensure_ascii=False, indent=2)


@mcp.tool()
async def erholung() -> str:
    """Den Erholungszustand abrufen: AutoSleep-Verlauf der letzten Nächte plus Baseline.

    Nutze dies für Fragen zu Erholung, HRV, Ruhepuls, Schlafqualität oder ob der
    Körper bereit ist.

    Wichtig bei der Auslegung: **Schlafdauer ist bei diesem Athleten bewusst kein
    Entscheidungsfaktor** — kurze Nächte sind normal. Maßgeblich sind HRV-Trend
    und WachBPM. Die Baseline nennt je Marker den Median und die Flag-Grenze.
    """
    verlauf, baseline = await _get("/api/sleep/history"), await _get("/api/baseline")
    return json.dumps({"verlauf": verlauf, "baseline": baseline},
                      ensure_ascii=False, indent=2)


@mcp.tool()
async def wetter(tag: str = "heute") -> str:
    """Die Wetterprognose für den Trainingsort abrufen, inklusive stündlicher Regenprognose.

    Nutze dies für Fragen zu Wetter, Outdoor vs. Indoor, Zwift, Freiwasser oder
    dem besten Zeitfenster.

    Args:
        tag: "heute" oder "morgen".
    """
    daten = await _get("/api/weather", day=_tag_normalisieren(tag))
    return json.dumps(daten, ensure_ascii=False, indent=2)


@mcp.tool()
async def profil() -> str:
    """Das Athletenprofil und die anstehenden Rennen abrufen.

    Nutze dies für Schwellenwerte (FTP, Laufschwelle, CSS), HF- und Pace-Zonen,
    Gewicht, Ernährungsregeln, Renntermine und Zielzeiten. Ohne diese Werte
    lassen sich Trainingsvorgaben nicht sinnvoll einordnen.
    """
    return json.dumps(await _get("/api/athlete"), ensure_ascii=False, indent=2)


@mcp.tool()
async def einheiten_historie(tage: int = 5) -> str:
    """Die abgeschlossenen Einheiten der letzten Tage mit Ist-Werten abrufen.

    Nutze dies für Fragen danach, wie das Training gelaufen ist, was schon
    absolviert wurde, oder zum Vergleich Plan gegen Ist.

    Args:
        tage: Anzahl Tage rückwärts (1 bis 30).
    """
    tage = max(1, min(30, int(tage)))
    daten = await _get("/api/tp/workouts/history", days=tage)
    return json.dumps(daten, ensure_ascii=False, indent=2)


@mcp.tool()
async def coach_frage(frage: str) -> str:
    """Den Coach der App selbst fragen — mit dem getunten Sportmediziner-Prompt.

    Nutze dies, wenn ein Urteil aus der Coaching-Logik der App gewünscht ist:
    Go/No-Go-Einschätzungen, sportmedizinisches Reasoning zu Knie, Achillessehne
    oder Waden, oder Anpassungen einer Einheit. Der Coach hat Athletenprofil,
    Trainingsplan, Wetter und Belastungslage schon im Kontext.

    Für reine Datenfragen sind die anderen Tools besser: sie liefern die
    Rohdaten, über die du selbst genauer nachdenken kannst als das kleinere
    Modell hinter diesem Chat.

    Args:
        frage: Die Frage an den Coach. Da jeder Aufruf für sich steht, gehört
            nötiger Gesprächskontext mit in den Text.
    """
    antwort = await _post("/api/coach/chat", {"message": frage, "history": []})
    reply = antwort.get("reply", "")
    pfad = antwort.get("_pipeline")
    return f"{reply}\n\n---\n(Coach-Engine: {pfad})" if pfad else reply


@mcp.tool()
async def app_status() -> str:
    """Version und Zustand der Coach-App prüfen.

    Nutze dies, wenn eine Antwort unerwartet aussieht oder ein Tool fehlschlägt.
    Zeigt, ob die Agent-Pipeline aktiv ist oder die App auf den alten
    Monolith-Prompt zurückgefallen ist.
    """
    daten = await _get("/api/version")
    return json.dumps({"url": COACH_URL, **daten}, ensure_ascii=False, indent=2)


def _bearer(scope) -> str:
    for key, value in scope.get("headers") or []:
        if key == b"authorization":
            roh = value.decode("latin-1").strip()
            return roh[7:].strip() if roh[:7].lower() == "bearer " else ""
    return ""


async def _antwort(send, status: int, text: str) -> None:
    body = text.encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def build_http_app(token: str):
    """Streamable-HTTP-App mit Bearer-Token davor.

    Bewusst rohes ASGI statt Starlette-Middleware: unabhängig von der
    starlette-Version, die `mcp` gerade mitbringt. `/health` bleibt offen, damit
    der Railway-Healthcheck ohne Token durchkommt — er verrät nichts.
    """
    inner = mcp.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)          # lifespan, websocket
            return
        if scope.get("path", "").rstrip("/") == "/health":
            await _antwort(send, 200, "ok")
            return
        # compare_digest: kein Timing-Seitenkanal beim Token-Vergleich.
        if not secrets.compare_digest(_bearer(scope), token):
            await _antwort(send, 401, "Unauthorized — Bearer-Token fehlt oder falsch.")
            return
        await inner(scope, receive, send)

    return app


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("stdio", ""):
        print(f"ki-coach MCP (stdio) → {COACH_URL}", file=sys.stderr)
        mcp.run(transport="stdio")
        return
    if transport not in ("http", "streamable-http"):
        raise SystemExit(f"MCP_TRANSPORT='{transport}' unbekannt — 'stdio' oder 'http'.")

    token = os.environ.get("MCP_TOKEN", "").strip()
    if len(token) < 32:
        raise SystemExit(
            "MCP_TOKEN fehlt oder ist zu kurz (mindestens 32 Zeichen). Der Server "
            "wäre sonst öffentlich: Gesundheitsdaten lesbar und der Anthropic-Key "
            "über coach_frage nutzbar. Token erzeugen: python -c "
            "\"import secrets;print(secrets.token_urlsafe(32))\""
        )

    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"ki-coach MCP (http) auf :{port} → {COACH_URL}", file=sys.stderr)
    uvicorn.run(build_http_app(token), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
