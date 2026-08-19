import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.portfolio.config import Settings
from src.portfolio.database import Database
from src.portfolio.retry import with_backoff
from src.portfolio.run_logging import RunLogger


class ResilientPipelineTests(unittest.TestCase):
    def test_database_persists_required_pipeline_fields_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "portfolio.db")
            database.import_rows([{
                "record_id": "record-1", "lesson_name": "Aula",
                "jwplayer_id": "Ab12Cd34", "keywords": "",
            }], "source.xlsx")
            database.update_pipeline(
                "Ab12Cd34", status="classifying", url_path="https://example/video.mp4",
                transcricao="texto", tokens_usados=123, custo_estimado=0.01,
            )
            item = database.pipeline_items(("classifying",))[0]
            self.assertEqual(item["status"], "classifying")
            self.assertEqual(item["tokens_usados"], 123)
            self.assertEqual(database.pipeline_counts()["classifying"], 1)

    def test_retry_errors_only_moves_failed_items(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "portfolio.db")
            database.import_rows([{
                "record_id": "record-1", "lesson_name": "Aula",
                "jwplayer_id": "Ab12Cd34", "keywords": "",
            }], "source.xlsx")
            database.update_pipeline("Ab12Cd34", status="error", erro_msg="falha")
            self.assertEqual(database.retry_errors(), 1)
            self.assertEqual(database.pipeline_counts()["pending"], 1)

    def test_exponential_retry_stops_after_success(self):
        calls = []

        async def operation():
            calls.append(1)
            if len(calls) < 3:
                raise TimeoutError("timeout")
            return "ok"

        with patch("src.portfolio.retry.asyncio.sleep", return_value=None):
            result = asyncio.run(with_backoff(operation, attempts=3, base_delay=0))
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_settings_and_jsonl_logging(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "CETRUS_DATA_DIR": directory, "MAX_CONCURRENCY": "7", "AI_PROVIDER": "OpenAI",
        }, clear=False):
            settings = Settings.from_env(None)
            self.assertEqual(settings.max_concurrency, 7)
            logger = RunLogger(Path(directory) / "logs")
            logger.log("stage_finished", video_id="Ab12Cd34", stage="classifying", duration_seconds=1.2)
            record = json.loads(logger.path.read_text(encoding="utf-8"))
            self.assertEqual(record["video_id"], "Ab12Cd34")


if __name__ == "__main__":
    unittest.main()
