from __future__ import annotations

import json
import os
import re

import requests

from .categories import CATEGORIES, CATEGORY_NAMES


class AIError(RuntimeError):
    pass


def validate_ollama_model(base_url: str, model: str) -> None:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
    except requests.RequestException as exc:
        raise AIError("Ollama não está acessível. Inicie o Ollama ou escolha outro provedor.") from exc
    payload = _checked(response, "Ollama")
    installed = {
        str(item.get("name") or item.get("model") or "")
        for item in payload.get("models", [])
    }
    aliases = {model, model if ":" in model else f"{model}:latest"}
    if not installed.intersection(aliases):
        raise AIError(
            f"O modelo Ollama '{model}' não está instalado. "
            f"Execute 'ollama pull {model}' ou escolha Gemini, OpenAI ou Claude."
        )


def analysis_prompt(title: str, transcript: str = "", frame_times: list[float] | None = None) -> str:
    taxonomy = "\n".join(f"- {c.name}: {c.definition} Sinais: {c.signals}" for c in CATEGORIES)
    return f"""Você classifica e resume aulas médicas Cetrus a partir de frames distribuídos ao longo do vídeo. Analise o conjunto completo de imagens, e não um frame isolado. Use somente as evidências fornecidas.
Categorias permitidas:\n{taxonomy}

Regras obrigatórias de classificação:
- Teórica core: professor aparece em contexto de estúdio junto aos slides de aula.
- Teórica apenas slide: os frames exibem somente slides; o professor não aparece.
- Demonstrativo: há prática ou demonstração de exame/procedimento, com paciente, professor, equipamento ou tela de exame em uso.
- Teórica core + demonstrativo: frames de momentos diferentes comprovam tanto a parte teórica com professor/slides quanto a demonstração prática.
- Não identificado: as evidências são insuficientes ou não correspondem aos modelos anteriores.
- Não classifique como Demonstrativo apenas porque um slide contém uma imagem de exame; deve existir evidência de demonstração prática.
- No modo sem transcrição, não deduza características do áudio.

Título: {title}
Frames amostrados nos segundos: {frame_times or []}
Transcrição complementar: {transcript[:50000] or '[não utilizada no modo rápido]'}

Responda apenas JSON válido com: category, summary, confidence.
Regras obrigatórias do summary:
- escrever em português, em 1 a 3 frases completas e coerentes;
- concluir cada frase e cada ideia, sem interromper o texto por limite de caracteres;
- informar diretamente o principal conteúdo abordado no vídeo;
- destacar o tema e, quando houver evidência, o procedimento, a técnica ou o conceito apresentado;
- usar linguagem simples, objetiva e padronizada;
- aproveitar textos legíveis dos slides, o título e a transcrição complementar, quando disponível;
- não descrever a aparência dos frames, o processo de classificação ou a qualidade do áudio;
- não incluir interpretações complexas nem inventar assuntos ausentes.
confidence deve estar entre 0 e 1. Não invente tópicos ausentes."""


def _checked(response: requests.Response, provider: str) -> dict:
    if response.status_code >= 400:
        raise AIError(f"{provider}: {response.status_code} - {response.text[:240]}")
    try:
        return response.json()
    except ValueError as exc:
        raise AIError(f"{provider} devolveu uma resposta inválida.") from exc


def _openai_text(payload: dict) -> str:
    if payload.get("output_text"):
        return payload["output_text"]
    return "".join(
        part.get("text", "") for item in payload.get("output", [])
        for part in item.get("content", []) if part.get("type") == "output_text"
    )


def analyze_frames(provider: str, api_key: str, model: str, title: str,
                   frames: list[dict], transcript: str = "",
                   ollama_url: str = "http://127.0.0.1:11434") -> dict:
    prompt = analysis_prompt(title, transcript, [frame["timestamp"] for frame in frames])
    provider_key = provider.strip().casefold()
    if provider_key == "openai":
        content = [{"type": "input_text", "text": prompt}] + [
            {"type": "input_image", "image_url": f"data:{f['mime_type']};base64,{f['data']}"}
            for f in frames
        ]
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": [{"role": "user", "content": content}]}, timeout=240,
        )
        text = _openai_text(_checked(response, "OpenAI"))
    elif provider_key == "gemini":
        parts = [{"text": prompt}] + [
            {"inline_data": {"mime_type": f["mime_type"], "data": f["data"]}} for f in frames
        ]
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"role": "user", "parts": parts}],
                  "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
            timeout=240,
        )
        payload = _checked(response, "Gemini")
        text = "".join(
            part.get("text", "") for candidate in payload.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        )
    elif provider_key in {"claude", "anthropic"}:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image", "source": {"type": "base64", "media_type": f["mime_type"], "data": f["data"]}}
            for f in frames
        ]
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 700, "temperature": 0,
                  "messages": [{"role": "user", "content": content}]}, timeout=240,
        )
        payload = _checked(response, "Claude")
        text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
    elif provider_key == "ollama":
        ollama_timeout = max(60, int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "900")))

        def ollama_payload(selected_frames: list[dict]) -> dict:
            return {
                "model": model, "stream": False, "format": "json",
                "options": {"num_ctx": 8192, "temperature": 0},
                "messages": [{
                    "role": "user", "content": prompt,
                    "images": [f["data"] for f in selected_frames],
                }],
            }

        # Modelos visuais locais ficam muito lentos com 8+ imagens. Seleciona
        # quatro pontos distribuídos para manter a inferência dentro do prazo.
        if len(frames) > 4:
            indexes = [round(i * (len(frames) - 1) / 3) for i in range(4)]
            selected_frames = [frames[index] for index in indexes]
        else:
            selected_frames = frames
        try:
            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/chat",
                json=ollama_payload(selected_frames), timeout=ollama_timeout,
            )
        except requests.Timeout as exc:
            raise AIError(
                f"Ollama excedeu {ollama_timeout} segundos. Use um modelo visual menor "
                "ou escolha Gemini, OpenAI ou Claude."
            ) from exc
        # Alguns modelos visuais mantêm limite interno de 4096 mesmo quando
        # num_ctx é solicitado. Nesse caso, reduz a amostra sem parar o lote.
        if (
            response.status_code == 400
            and "exceeds the available context size" in response.text
            and len(selected_frames) > 2
        ):
            reduced_frames = selected_frames[::2]
            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/chat",
                json=ollama_payload(reduced_frames), timeout=ollama_timeout,
            )
        payload = _checked(response, "Ollama")
        text = payload.get("message", {}).get("content", "")
    else:
        raise AIError(f"Provedor de IA não suportado: {provider}")
    return parse_result(text)


def parse_result(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise AIError("A IA não devolveu JSON.")
    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIError("A IA devolveu JSON inválido.") from exc
    category = result.get("category")
    if category not in CATEGORY_NAMES:
        category = "Não identificado"
    summary = _normalize_summary(result.get("summary"))
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"category": category, "summary": summary, "confidence": confidence}


def _normalize_summary(value: object) -> str:
    summary = " ".join(str(value or "").split())
    if not summary:
        return "Conteúdo não identificado nos frames analisados."
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    summary = " ".join(sentences[:3]).strip()
    if summary and summary[-1] not in ".!?":
        summary += "."
    return summary


def analyze_with_openai(api_key: str, model: str, title: str, transcript: str) -> dict:
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": analysis_prompt(title, transcript), "temperature": 0},
        timeout=180,
    )
    if response.status_code >= 400:
        raise AIError(f"OpenAI: {response.status_code} - {response.text[:240]}")
    payload = response.json()
    text = _openai_text(payload)
    return parse_result(text)


def analyze_with_ollama(base_url: str, model: str, title: str, transcript: str) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={"model": model, "prompt": analysis_prompt(title, transcript), "stream": False, "format": "json"},
        timeout=300,
    )
    if response.status_code >= 400:
        raise AIError(f"Ollama: {response.status_code} - {response.text[:240]}")
    return parse_result(response.json().get("response", ""))
