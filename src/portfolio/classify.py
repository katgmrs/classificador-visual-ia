from __future__ import annotations

import base64
from pathlib import Path

import requests

from .config import Settings


# ==========================================================================
# ÁREA DE CUSTOMIZAÇÃO
# Cole abaixo o seu system prompt e suas regras de decisão.
# A função não contém lógica de classificação do projeto: ela apenas envia
# o prompt e o frame para a API e devolve a resposta do modelo.
# ==========================================================================
CUSTOM_SYSTEM_PROMPT = """
[COLE AQUI O SEU SYSTEM PROMPT DE CLASSIFICAÇÃO]
""".strip()
# ========================== FIM DA CUSTOMIZAÇÃO ===========================


class ClassificationPromptNotConfigured(RuntimeError):
    pass


def classify_frame(frame_path: str | Path, settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    if CUSTOM_SYSTEM_PROMPT.startswith("[COLE AQUI"):
        raise ClassificationPromptNotConfigured(
            "Configure CUSTOM_SYSTEM_PROMPT em src/portfolio/classify.py antes de classificar."
        )
    path = Path(frame_path)
    image = base64.b64encode(path.read_bytes()).decode("ascii")
    if settings.provider.casefold() != "openai":
        raise RuntimeError("O ponto customizável classify_frame está preparado inicialmente para OpenAI.")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        json={"model": settings.model, "input": [{"role": "system", "content": CUSTOM_SYSTEM_PROMPT}, {
            "role": "user", "content": [
                {"type": "input_text", "text": "Classifique este frame conforme o system prompt."},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image}"},
            ],
        }]}, timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text") or "".join(
        part.get("text", "") for item in payload.get("output", [])
        for part in item.get("content", []) if part.get("type") == "output_text"
    )
    usage = payload.get("usage") or {}
    return {
        "classification": text.strip(),
        "tokens_used": int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
