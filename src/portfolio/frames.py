from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path


class FrameExtractionError(RuntimeError):
    pass


def _duration(source_url: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FrameExtractionError("FFprobe não foi encontrado no computador.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", source_url],
        capture_output=True, text=True, timeout=90,
    )
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrameExtractionError("Não foi possível identificar a duração do vídeo.") from exc
    if duration <= 0:
        raise FrameExtractionError("A duração do vídeo é inválida.")
    return duration


def extract_frames(source_url: str, work_dir: Path, count: int = 8) -> tuple[list[dict], float]:
    """Extrai JPEGs pequenos e distribuídos sem baixar/transcodificar a aula inteira."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FrameExtractionError("FFmpeg não foi encontrado no computador.")
    count = max(4, min(16, int(count)))
    duration = _duration(source_url)
    work_dir.mkdir(parents=True, exist_ok=True)
    timestamps = [duration * (0.04 + 0.92 * i / max(count - 1, 1)) for i in range(count)]
    frames: list[dict] = []
    for index, timestamp in enumerate(timestamps, 1):
        target = work_dir / f"frame_{index:02d}.jpg"
        command = [
            ffmpeg, "-y", "-ss", f"{timestamp:.3f}", "-i", source_url,
            "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "5", str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and target.exists() and target.stat().st_size > 1000:
            frames.append({
                "timestamp": round(timestamp, 1), "mime_type": "image/jpeg",
                "data": base64.b64encode(target.read_bytes()).decode("ascii"),
            })
        target.unlink(missing_ok=True)
    if len(frames) < max(3, count // 2):
        raise FrameExtractionError(f"Somente {len(frames)} frame(s) válido(s) foram extraídos.")
    return frames, duration
