from __future__ import annotations

import requests
import re

from .config import Settings


SUMMARY_SYSTEM_PROMPT = """Resuma em português, em 1 a 3 frases, o principal conteúdo do vídeo.
Destaque o tema e, quando aplicável, o procedimento, a técnica ou o conceito apresentado.
Use linguagem simples, objetiva e padronizada. Não invente informações."""


def summarize_video(classification: str, transcript: str, title: str,
                    settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    if settings.provider.casefold() != "openai":
        raise RuntimeError("A CLI customizável está preparada inicialmente para OpenAI.")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        json={"model": settings.model, "input": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Título: {title}\nClassificação visual: {classification}\n"
                f"Transcrição: {transcript[:50000] or '[não utilizada]'}"
            )},
        ]}, timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text") or "".join(
        part.get("text", "") for item in payload.get("output", [])
        for part in item.get("content", []) if part.get("type") == "output_text"
    )
    usage = payload.get("usage") or {}
    normalized = " ".join(text.split())
    normalized = " ".join(re.split(r"(?<=[.!?])\s+", normalized)[:3]).strip()
    if normalized and normalized[-1] not in ".!?":
        normalized += "."
    return {
        "summary": normalized,
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
