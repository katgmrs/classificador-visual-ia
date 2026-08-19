from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass
class MediaAsset:
    media_id: str
    title: str
    duration: float | None
    source_url: str | None
    transcript_url: str | None
    thumbnail_track_url: str | None = None


class JWPlayerError(RuntimeError):
    pass


class JWPlayerClient:
    def __init__(self, site_id: str, token: str = "", timeout: int = 30):
        self.site_id = site_id.strip()
        self.token = token.strip()
        self.timeout = timeout

    def playback(self, media_id: str) -> MediaAsset:
        if len(self.site_id) != 8:
            raise JWPlayerError("Informe o Site ID de oito caracteres do JW Player.")
        url = f"https://cdn.jwplayer.com/v2/sites/{self.site_id}/media/{media_id}/playback.json"
        params = {"token": self.token} if self.token else None
        response = requests.get(url, params=params, timeout=self.timeout)
        if response.status_code in {401, 403}:
            raise JWPlayerError("A mídia é protegida. Informe um token de entrega válido.")
        if response.status_code == 404:
            raise JWPlayerError("Mídia não encontrada nessa propriedade JW Player.")
        response.raise_for_status()
        payload = response.json()
        item = (payload.get("playlist") or [payload])[0]
        sources = item.get("sources") or []
        tracks = item.get("tracks") or []
        mp4_sources = [
            s for s in sources
            if str(s.get("type", "")).lower() == "video/mp4" and s.get("file")
        ]
        mp4_sources.sort(key=lambda s: (int(s.get("width") or 99999), int(s.get("height") or 99999)))
        source = mp4_sources[0].get("file") if mp4_sources else None
        source = source or next((s.get("file") for s in sources if "mpegurl" in str(s.get("type", ""))), None)
        source = source or next((s.get("file") for s in sources if s.get("file")), None)
        transcript = next(
            (t.get("file") for t in tracks if t.get("file") and str(t.get("kind", "")).lower() in {"captions", "subtitles"}),
            None,
        )
        return MediaAsset(
            media_id=media_id,
            title=str(item.get("title") or media_id),
            duration=float(item["duration"]) if item.get("duration") is not None else None,
            source_url=source,
            transcript_url=transcript,
            thumbnail_track_url=next(
                (t.get("file") for t in tracks if t.get("file") and str(t.get("kind", "")).lower() == "thumbnails"),
                None,
            ),
        )

    def download_transcript(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        lines = []
        for line in response.text.replace("\ufeff", "").splitlines():
            clean = line.strip()
            if not clean or clean == "WEBVTT" or "-->" in clean or clean.isdigit() or clean.startswith("NOTE"):
                continue
            if clean not in lines[-1:]:
                lines.append(clean)
        return " ".join(lines)
