from __future__ import annotations

from .ai import analyze_with_ollama, analyze_with_openai
from .database import Database, utc_now
from .jwplayer import JWPlayerClient


def process_media(
    database: Database,
    jwplayer_id: str,
    lesson_name: str,
    site_id: str,
    delivery_token: str,
    provider: str,
    api_key: str = "",
    model: str = "",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict:
    database.update_analysis(jwplayer_id, status="Processando", error_message=None)
    try:
        client = JWPlayerClient(site_id, delivery_token)
        asset = client.playback(jwplayer_id)
        if not asset.transcript_url:
            raise RuntimeError(
                "A mídia não possui legenda/transcrição disponível no JW Player. "
                "Adicione uma faixa de legenda antes de processar."
            )
        transcript = client.download_transcript(asset.transcript_url)
        if len(transcript) < 40:
            raise RuntimeError("A transcrição encontrada é vazia ou curta demais para análise.")
        title = asset.title or lesson_name
        if provider == "OpenAI":
            if not api_key:
                raise RuntimeError("Informe a chave da OpenAI.")
            result = analyze_with_openai(api_key, model or "gpt-5-mini", title, transcript)
        else:
            result = analyze_with_ollama(ollama_url, model or "qwen2.5:7b", title, transcript)
        database.update_analysis(
            jwplayer_id,
            status="Concluído",
            ai_category=result["category"],
            final_category=result["category"],
            summary=result["summary"],
            confidence=result["confidence"],
            validation_status="Pendente",
            transcript=transcript,
            source_title=title,
            duration=asset.duration,
            analyzed_at=utc_now(),
            error_message=None,
        )
        return result
    except Exception as exc:
        database.update_analysis(jwplayer_id, status="Erro", error_message=str(exc))
        raise

