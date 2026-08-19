from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class TranscriptionError(RuntimeError):
    pass


def transcribe_hls(master_url: str, work_dir: Path, model_name: str = "small") -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscriptionError("FFmpeg não foi encontrado no servidor.")
    work_dir.mkdir(parents=True, exist_ok=True)
    audio_path = work_dir / "audio.wav"
    command = [
        ffmpeg, "-y", "-i", master_url, "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=7200)
    if result.returncode != 0 or not audio_path.exists():
        raise TranscriptionError("Não foi possível extrair o áudio: " + result.stderr[-500:])
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), language="pt", vad_filter=True, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        if len(text) < 40:
            raise TranscriptionError("A transcrição ficou vazia ou curta demais.")
        return text
    finally:
        audio_path.unlink(missing_ok=True)

