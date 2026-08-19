from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path

from .classify import classify_frame
from .config import Settings
from .database import Database
from .frames import extract_frames
from .jwplayer import JWPlayerClient
from .retry import with_backoff
from .run_logging import RunLogger
from .summarize import summarize_video
from .transcription import transcribe_hls


ACTIVE_STATUSES = ("pending", "downloading", "transcribing", "classifying", "summarizing")


class AsyncVideoPipeline:
    def __init__(self, database: Database, settings: Settings, logger: RunLogger):
        self.database = database
        self.settings = settings
        self.logger = logger
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def run_pending(self) -> dict[str, int]:
        items = self.database.pipeline_items(ACTIVE_STATUSES)
        self.logger.log("run_started", total=len(items), concurrency=self.settings.max_concurrency)
        await asyncio.gather(*(self._guarded(item) for item in items))
        counts = self.database.pipeline_counts()
        self.logger.log("run_finished", counts=counts)
        return counts

    async def _guarded(self, item: dict) -> None:
        async with self.semaphore:
            await self._process(item)

    async def _stage(self, video_id: str, stage: str, operation):
        started = time.perf_counter()
        self.logger.log("stage_started", video_id=video_id, stage=stage)

        def retry_log(attempt: int, delay: float, exc: Exception) -> None:
            self.logger.log(
                "stage_retry", video_id=video_id, stage=stage, attempt=attempt,
                delay_seconds=round(delay, 3), error=str(exc),
            )

        try:
            result = await with_backoff(
                operation, attempts=self.settings.max_retries, on_retry=retry_log,
            )
        except Exception as exc:
            self.logger.log(
                "stage_error", video_id=video_id, stage=stage,
                duration_seconds=round(time.perf_counter() - started, 3), error=str(exc),
            )
            raise
        self.logger.log(
            "stage_finished", video_id=video_id, stage=stage,
            duration_seconds=round(time.perf_counter() - started, 3),
        )
        return result

    async def _process(self, item: dict) -> None:
        video_id = item["id"]
        try:
            state = item["status"]
            frames = self._existing_frames(item.get("frames_json"))
            source = item.get("url_path")

            if state in {"pending", "downloading"} or not source or not frames:
                self.database.update_pipeline(video_id, status="downloading", erro_msg=None)

                async def download_stage():
                    asset = await asyncio.to_thread(
                        JWPlayerClient(self.settings.jw_site_id, self.settings.jw_delivery_token).playback,
                        video_id,
                    )
                    if not asset.source_url:
                        raise RuntimeError("JW Player não retornou uma fonte de vídeo.")
                    extracted, _ = await asyncio.to_thread(
                        extract_frames, asset.source_url,
                        self.settings.data_dir / "artifacts" / video_id,
                        self.settings.frame_count,
                    )
                    paths = self._persist_frames(video_id, extracted)
                    return asset.source_url, paths

                source, frames = await self._stage(video_id, "downloading", download_stage)
                next_status = "transcribing" if self.settings.transcribe else "classifying"
                self.database.update_pipeline(
                    video_id, url_path=source, frames_json=json.dumps(frames), status=next_status,
                )
                state = next_status

            transcript = item.get("transcricao") or ""
            if state == "transcribing":
                async def transcription_stage():
                    return await asyncio.to_thread(
                        transcribe_hls, source, self.settings.data_dir / "artifacts" / video_id,
                        self.settings.whisper_model,
                    )
                transcript = await self._stage(video_id, "transcribing", transcription_stage)
                self.database.update_pipeline(video_id, transcricao=transcript, status="classifying")
                state = "classifying"

            classification = item.get("classificacao") or ""
            total_input = int(item.get("tokens_usados") or 0)
            total_output = 0
            existing_cost = float(item.get("custo_estimado") or 0)
            if state == "classifying":
                async def classification_stage():
                    results = []
                    for frame in frames:
                        results.append(await asyncio.to_thread(classify_frame, frame, self.settings))
                    return results
                results = await self._stage(video_id, "classifying", classification_stage)
                classification = json.dumps(
                    [result["classification"] for result in results], ensure_ascii=False,
                )
                total_input += sum(result.get("input_tokens", 0) for result in results)
                total_output += sum(result.get("output_tokens", 0) for result in results)
                self.database.update_pipeline(
                    video_id, classificacao=classification,
                    tokens_usados=total_input + total_output, status="summarizing",
                )
                state = "summarizing"

            if state == "summarizing":
                async def summary_stage():
                    return await asyncio.to_thread(
                        summarize_video, classification, transcript, item.get("lesson_name") or video_id,
                        self.settings,
                    )
                summary = await self._stage(video_id, "summarizing", summary_stage)
                total_input += summary.get("input_tokens", 0)
                total_output += summary.get("output_tokens", 0)
                cost = existing_cost + (
                    total_input * self.settings.input_cost_per_million
                    + total_output * self.settings.output_cost_per_million
                ) / 1_000_000
                self.database.update_pipeline(
                    video_id, resumo=summary["summary"], tokens_usados=total_input + total_output,
                    custo_estimado=cost, status="done", erro_msg=None,
                )
        except Exception as exc:
            self.database.update_pipeline(video_id, status="error", erro_msg=str(exc))
            self.logger.log("video_error", video_id=video_id, stage="pipeline", error=str(exc))

    def _persist_frames(self, video_id: str, frames: list[dict]) -> list[str]:
        directory = self.settings.data_dir / "artifacts" / video_id / "frames"
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for index, frame in enumerate(frames, 1):
            path = directory / f"frame_{index:02d}.jpg"
            path.write_bytes(base64.b64decode(frame["data"]))
            paths.append(str(path.resolve()))
        return paths

    @staticmethod
    def _existing_frames(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            paths = json.loads(value)
            return paths if paths and all(Path(path).exists() for path in paths) else []
        except (TypeError, json.JSONDecodeError):
            return []
