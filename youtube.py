"""YouTube-Transkript-Abruf für den Recherche-Agenten (v2.9.2).

Kein eigener MCP-Service, direkte Nutzung von `youtube-transcript-api` — analog
zu `strava.py`s direkten httpx-Calls für Strava.

**YouTube blockiert Transkript-Abrufe von Cloud-Server-IPs (Railway, AWS, GCP, …)
zuverlässig anhand der ASN, schon beim ersten Aufruf** — kein Retry-Problem,
sondern ein IP-Klassen-Problem. Der einzige belastbare Fix ist ein
residentieller Rotating-Proxy; ein Datacenter-Proxy hätte dieselbe Blockade.
Diese Datei erwartet dafür einen **Webshare-„Residential"-Plan** (ausdrücklich
nicht „Proxy Server"/Datacenter, nicht „Static Residential") über
`WEBSHARE_PROXY_USERNAME`/`WEBSHARE_PROXY_PASSWORD`. Fehlen die beiden ENV-Vars,
wirft `_client()` `YoutubeNotConfigured` — ein klarer Fehler statt eines
kryptischen Abbruchs mitten im Abruf, dasselbe Muster wie bei fehlendem
`TP_MCP_URL`/`STRAVA_CLIENT_ID`.
"""
import logging
import os
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

logger = logging.getLogger(__name__)

# Kostendeckel für den anschließenden Claude-Call — analog zu "maximal 5
# Erkenntnisse" in research.md. Ein 3h-Podcast-Transkript wäre sonst sowohl
# teuer als auch jenseits dessen, was ein Agent noch sinnvoll auswerten kann.
_MAX_TRANSCRIPT_CHARS = 60_000


class YoutubeError(Exception):
    """Transkript ließ sich nicht beschaffen — Video ohne Untertitel, gesperrt,
    von YouTube blockierte Anfrage, o.ä."""


class YoutubeNotConfigured(YoutubeError):
    """WEBSHARE_PROXY_USERNAME/PASSWORD fehlen."""


def extract_video_id(url: str) -> Optional[str]:
    """youtube.com/watch?v=…, youtu.be/…, /shorts/…, /embed/…, /live/… — sonst None."""
    url = (url or "").strip()
    if not url:
        return None
    try:
        teile = urlparse(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    host = (teile.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        video_id = teile.path.lstrip("/").split("/")[0]
        return video_id or None
    if "youtube.com" in host:
        if teile.path == "/watch":
            treffer = parse_qs(teile.query).get("v")
            return treffer[0] if treffer else None
        gefunden = re.match(r"^/(shorts|embed|live)/([^/?]+)", teile.path)
        if gefunden:
            return gefunden.group(2)
    return None


def _client() -> YouTubeTranscriptApi:
    user = os.environ.get("WEBSHARE_PROXY_USERNAME", "").strip()
    pw = os.environ.get("WEBSHARE_PROXY_PASSWORD", "").strip()
    if not user or not pw:
        raise YoutubeNotConfigured(
            "Video-Transkript nicht konfiguriert — WEBSHARE_PROXY_USERNAME/"
            "WEBSHARE_PROXY_PASSWORD fehlen (Webshare-Residential-Plan nötig, "
            "siehe CLAUDE.md)."
        )
    return YouTubeTranscriptApi(
        proxy_config=WebshareProxyConfig(proxy_username=user, proxy_password=pw)
    )


def _kuerzen(text: str) -> tuple[str, bool]:
    """Reine Funktion, ohne Netzwerk testbar."""
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        return text[:_MAX_TRANSCRIPT_CHARS], True
    return text, False


def fetch_title(video_id: str) -> Optional[str]:
    """oEmbed — öffentlich, ungeprüft, kein Proxy nötig (kein Scraping-Ziel wie
    die Transkript-API). Best effort: der Titel ist nur ein Anzeigedetail, ein
    Fehler hier darf den Abruf nie blockieren."""
    try:
        r = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=8.0,
        )
        if r.status_code == 200:
            return r.json().get("title")
    except Exception as e:
        logger.warning("youtube: Titel-Abruf für %s fehlgeschlagen: %s", video_id, e)
    return None


_KLARTEXT = {
    "IpBlocked": "YouTube blockt die Proxy-IP (Webshare-Kontingent erschöpft oder gesperrt)",
    "RequestBlocked": "YouTube blockt die Anfrage (Proxy-IP)",
    "TooManyRequests": "YouTube meldet zu viele Anfragen (429) — Proxy-IP gedrosselt",
    "TranscriptsDisabled": "Für dieses Video sind keine Untertitel aktiviert",
    "NoTranscriptFound": "Kein Transkript in den verfügbaren Sprachen",
    "VideoUnavailable": "Video nicht verfügbar (privat, gelöscht oder regional gesperrt)",
}


def _erklaere(e: Exception) -> str:
    """Kurze, lesbare Fehlerzeile. Die Bibliotheksmeldungen sind mehrere Absätze
    lang, der eigentliche Grund steht mittendrin — deshalb Klartext für die
    bekannten Typen, sonst Typ + erste Zeile. Volltext: Debugfunktion."""
    typ = type(e).__name__
    return _KLARTEXT.get(typ) or f"{typ}: {str(e).strip().splitlines()[0][:200]}"


def _hole_transcript(api, video_id: str, languages: tuple = ("de", "en")):
    """Bevorzugte Sprachen, sonst irgendein Transkript — lieber irgendeins als gar keins.

    Schlägt beides fehl, zählt der Grund des ersten Versuchs (der ist die
    eigentliche Ursache; der zweite Versuch scheitert meist am selben Grund).
    """
    try:
        return api.fetch(video_id, languages=list(languages))
    except Exception as e_erst:
        try:
            erstes = next(iter(api.list(video_id)))
            return erstes.fetch()
        except Exception as e_zweit:
            grund = _erklaere(e_erst)
            if type(e_zweit) is not type(e_erst):
                grund += f" (Ausweichversuch: {_erklaere(e_zweit)})"
            raise YoutubeError(f"Kein Transkript verfügbar — {grund}") from e_erst


def _segmente(transcript) -> list[tuple[int, str]]:
    """FetchedTranscriptSnippet (Dataclass: .text, .start) → [(start_s, text)]."""
    segments = []
    for schnipsel in transcript:
        text = (schnipsel.text or "").strip()
        if text:
            segments.append((int(schnipsel.start), text))
    return segments


def fetch_transcript(video_id: str, languages: tuple = ("de", "en")) -> str:
    transcript = _hole_transcript(_client(), video_id, languages)
    text = " ".join(schnipsel.text for schnipsel in transcript).strip()
    if not text:
        raise YoutubeError("Transkript ist leer")
    return text


def fetch_transcript_segments(video_id: str, languages: tuple = ("de", "en")) -> tuple[list, str]:
    """
    Transkript als Segmente mit Zeitstempeln für RAG.

    Return: ([(start_s, text), ...], titel_oder_"")

    **NICHT gekürzt** — die volle Länge wird zurückgegeben.
    Chunking und Längenkontrolle macht wissensbasis.py.
    """
    transcript = _hole_transcript(_client(), video_id, languages)
    if not transcript:
        raise YoutubeError("Transkript ist leer")

    segments = _segmente(transcript)
    if not segments:
        raise YoutubeError("Transkript hat keine verwertbaren Segmente")

    titel = fetch_title(video_id) or ""
    return segments, titel


def diagnose(url: str) -> dict:
    """Schrittweise Prüfung der gesamten YouTube-Kette (v2.10.4, Debugfunktion).

    Jeder Schritt meldet Ergebnis oder die vollständige Fehlermeldung inkl.
    Exception-Typ — genau das, was die Endpoints sonst still verschlucken. Der
    Proxy-Benutzername/das Passwort werden nie ausgegeben, nur ob sie gesetzt sind.
    Ein Schritt, der fehlschlägt, bricht die übrigen nicht ab.
    """
    import importlib.metadata

    schritte: list[dict] = []

    def schritt(name: str, fn):
        try:
            ergebnis = fn()
            schritte.append({"schritt": name, "ok": True, "ergebnis": ergebnis})
            return ergebnis
        except Exception as e:
            schritte.append({
                "schritt": name, "ok": False,
                "fehler_typ": type(e).__name__, "fehler": str(e),
            })
            return None

    def _video_id() -> str:
        vid = extract_video_id(url)
        if not vid:
            raise ValueError("keine video_id in der URL erkannt")
        return vid

    video_id = schritt("video_id", _video_id)
    schritt("bibliothek", lambda: importlib.metadata.version("youtube-transcript-api"))
    schritt("proxy_env", lambda: {
        "WEBSHARE_PROXY_USERNAME_gesetzt": bool(os.environ.get("WEBSHARE_PROXY_USERNAME", "").strip()),
        "WEBSHARE_PROXY_PASSWORD_gesetzt": bool(os.environ.get("WEBSHARE_PROXY_PASSWORD", "").strip()),
    })
    client = {}

    def _client_check() -> str:
        client["api"] = _client()  # wirft YoutubeNotConfigured ohne ENV
        return "ok"

    schritt("client", _client_check)
    api = client.get("api")
    if not video_id or api is None:
        return _diagnose_bericht(url, video_id, schritte)

    schritt("titel_oembed", lambda: fetch_title(video_id))
    schritt("liste_verfuegbar", lambda: [
        {"sprache": t.language_code, "generiert": t.is_generated, "name": t.language}
        for t in api.list(video_id)
    ])

    geladen = {}  # erstes erfolgreich geladenes Transkript für den Segment-Test

    def _fetch_bevorzugt() -> dict:
        geladen.setdefault("t", api.fetch(video_id, languages=["de", "en"]))
        return _snippet_info(geladen["t"])

    def _fetch_irgendein() -> dict:
        t = next(iter(api.list(video_id))).fetch()
        geladen.setdefault("t", t)
        return _snippet_info(t)

    schritt("fetch_de_en", _fetch_bevorzugt)
    schritt("fetch_irgendein", _fetch_irgendein)

    def _segmente_test() -> dict:
        if "t" not in geladen:
            raise ValueError("kein Transkript geladen, Schritt übersprungen")
        segs = _segmente(geladen["t"])
        return {"anzahl": len(segs), "erstes": segs[0] if segs else None}

    schritt("segmente_parsen", _segmente_test)
    return _diagnose_bericht(url, video_id, schritte)


def _snippet_info(transcript) -> dict:
    snippets = list(transcript)
    return {
        "sprache": transcript.language_code,
        "generiert": transcript.is_generated,
        "snippets": len(snippets),
        "zeichen": sum(len(s.text) for s in snippets),
        "erste_zeile": snippets[0].text[:120] if snippets else None,
    }


_BLOCK_FEHLER = {"IpBlocked", "RequestBlocked", "TooManyRequests"}


def _diagnose_bericht(url: str, video_id, schritte: list) -> dict:
    # Häufigster Fall laut Projektgeschichte: YouTube blockt die Proxy-IPs.
    # Der Hinweis ersetzt nicht die Rohdaten, er sagt nur, wo man zuerst schaut.
    blockiert = any(s.get("fehler_typ") in _BLOCK_FEHLER for s in schritte)
    return {
        "url": url,
        "video_id": video_id,
        "ok": all(s["ok"] for s in schritte),
        "hinweis": ("YouTube blockt die Proxy-IPs (Webshare-Kontingent erschöpft oder gesperrt). "
                    "Abwarten oder bezahlten Residential-Plan prüfen.") if blockiert else None,
        "schritte": schritte,
    }


def fetch_transcript_and_title(video_id: str) -> tuple[str, Optional[str], bool]:
    """Rückgabe: (transkript_text, titel_oder_None, wurde_gekuerzt).

    Alte Schnittstelle für Rückwärtskompatibilität (v2.9.2).
    """
    text = fetch_transcript(video_id)
    text, gekuerzt = _kuerzen(text)
    titel = fetch_title(video_id)
    return text, titel, gekuerzt
