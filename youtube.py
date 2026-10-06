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


def fetch_transcript(video_id: str, languages: tuple = ("de", "en")) -> str:
    api = _client()
    try:
        transcript = api.fetch(video_id, languages=list(languages))
    except Exception:
        # Bevorzugte Sprachen nicht vorhanden — lieber irgendein Transkript
        # als gar keins.
        try:
            verfuegbar = api.list(video_id)
            erstes = next(iter(verfuegbar))
            transcript = erstes.fetch()
        except Exception as e:
            raise YoutubeError(
                f"Kein Transkript verfügbar ({type(e).__name__}: {e})"
            ) from e
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
    api = _client()
    try:
        transcript = api.fetch(video_id, languages=list(languages))
    except Exception:
        try:
            verfuegbar = api.list(video_id)
            erstes = next(iter(verfuegbar))
            transcript = erstes.fetch()
        except Exception as e:
            raise YoutubeError(
                f"Kein Transkript verfügbar ({type(e).__name__}: {e})"
            ) from e

    if not transcript:
        raise YoutubeError("Transkript ist leer")

    # Segmente: start (in Sekunden), Text
    segments = []
    for schnipsel in transcript:
        start_s = int(schnipsel.get("start", 0))
        text = schnipsel.get("text", "").strip()
        if text:
            segments.append((start_s, text))

    if not segments:
        raise YoutubeError("Transkript hat keine verwertbaren Segmente")

    titel = fetch_title(video_id) or ""
    return segments, titel


def fetch_transcript_and_title(video_id: str) -> tuple[str, Optional[str], bool]:
    """Rückgabe: (transkript_text, titel_oder_None, wurde_gekuerzt).

    Alte Schnittstelle für Rückwärtskompatibilität (v2.9.2).
    """
    text = fetch_transcript(video_id)
    text, gekuerzt = _kuerzen(text)
    titel = fetch_title(video_id)
    return text, titel, gekuerzt
