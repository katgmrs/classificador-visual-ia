from __future__ import annotations

import argparse
import asyncio
import json

from src.portfolio.config import Settings
from src.portfolio.database import Database
from src.portfolio.orchestrator import AsyncVideoPipeline
from src.portfolio.run_logging import RunLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline resiliente de vídeos Cetrus")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run", action="store_true", help="Processa pendentes e retoma interrompidos")
    action.add_argument("--status", action="store_true", help="Exibe o progresso persistido")
    action.add_argument("--retry-errors", action="store_true", help="Move erros para pending e reprocessa")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    database = Database(settings.data_dir / "portfolio.db")
    if args.status:
        print(json.dumps(database.pipeline_counts(), ensure_ascii=False, indent=2))
        return 0
    if args.retry_errors:
        print(f"{database.retry_errors()} vídeo(s) movido(s) para pending.")
    logger = RunLogger(settings.data_dir / "logs")
    counts = asyncio.run(AsyncVideoPipeline(database, settings, logger).run_pending())
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"Log: {logger.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
