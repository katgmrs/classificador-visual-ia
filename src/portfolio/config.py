from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    video_dir: Path
    max_concurrency: int
    provider: str
    model: str
    api_key: str
    ollama_url: str
    jw_site_id: str
    jw_delivery_token: str
    frame_count: int
    transcribe: bool
    whisper_model: str
    max_retries: int
    input_cost_per_million: float
    output_cost_per_million: float

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        if env_file:
            load_dotenv(env_file, override=False)
        provider = os.getenv("AI_PROVIDER", "OpenAI")
        key_name = {
            "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY",
            "claude": "ANTHROPIC_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        }.get(provider.casefold(), "OPENAI_API_KEY")
        return cls(
            data_dir=Path(os.getenv("CETRUS_DATA_DIR", "./data")),
            video_dir=Path(os.getenv("VIDEO_DIR", "./videos")),
            max_concurrency=max(1, int(os.getenv("MAX_CONCURRENCY", "10"))),
            provider=provider,
            model=os.getenv("AI_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")),
            api_key=os.getenv(key_name, ""),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
            jw_site_id=os.getenv("JW_SITE_ID", "XdfUPSCL"),
            jw_delivery_token=os.getenv("JW_DELIVERY_TOKEN", ""),
            frame_count=max(4, min(16, int(os.getenv("FRAME_COUNT", "8")))),
            transcribe=os.getenv("TRANSCRIBE", "false").casefold() in {"1", "true", "yes", "sim"},
            whisper_model=os.getenv("WHISPER_MODEL", "small"),
            max_retries=max(1, int(os.getenv("MAX_RETRIES", "3"))),
            input_cost_per_million=float(os.getenv("INPUT_COST_PER_MILLION", "0")),
            output_cost_per_million=float(os.getenv("OUTPUT_COST_PER_MILLION", "0")),
        )
