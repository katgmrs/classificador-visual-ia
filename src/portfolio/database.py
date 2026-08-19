from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    total_rows INTEGER NOT NULL,
    new_rows INTEGER NOT NULL,
    updated_rows INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    record_id TEXT PRIMARY KEY,
    id TEXT,
    lesson_name TEXT NOT NULL,
    jwplayer_id TEXT NOT NULL,
    url_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    classificacao TEXT,
    transcricao TEXT,
    resumo TEXT,
    tokens_usados INTEGER NOT NULL DEFAULT 0,
    custo_estimado REAL NOT NULL DEFAULT 0,
    erro_msg TEXT,
    frames_json TEXT,
    criado_em TEXT,
    atualizado_em TEXT,
    keywords TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_jwplayer ON videos(jwplayer_id);

CREATE TABLE IF NOT EXISTS analyses (
    jwplayer_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'Pendente',
    ai_category TEXT,
    final_category TEXT,
    summary TEXT,
    confidence REAL,
    validation_status TEXT NOT NULL DEFAULT 'Pendente',
    transcript TEXT,
    source_title TEXT,
    duration REAL,
    error_message TEXT,
    analyzed_at TEXT,
    updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            # Uma queda/reinício não deve transformar falhas de sessão em falhas da mídia.
            connection.execute(
                """UPDATE analyses SET status='Pendente', error_message=NULL, updated_at=?
                   WHERE status='Processando'
                      OR error_message LIKE '%sessão JW Player%'
                      OR error_message LIKE '%navegador JW Player%'
                      OR error_message LIKE '%sessão expirou%'
                      OR error_message LIKE 'OpenAI:%'
                      OR error_message LIKE 'Gemini:%'
                      OR error_message LIKE 'Claude:%'
                      OR error_message LIKE 'Ollama:%'
                      OR (error_message LIKE '%127.0.0.1%'
                          AND error_message LIKE '%11434%'
                          AND error_message LIKE '%Read timed out%')""",
                (utc_now(),),
            )
            self._migrate_videos(connection)
            # Mantém a fila resiliente em sincronia com a análise recuperada acima.
            connection.execute(
                """UPDATE videos SET status='pending', erro_msg=NULL, atualizado_em=?
                   WHERE jwplayer_id IN (
                       SELECT jwplayer_id FROM analyses
                       WHERE status='Pendente' AND error_message IS NULL
                   ) AND status='error'""",
                (utc_now(),),
            )

    @staticmethod
    def _migrate_videos(connection: sqlite3.Connection) -> None:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(videos)")}
        additions = {
            "id": "TEXT", "url_path": "TEXT", "status": "TEXT NOT NULL DEFAULT 'pending'",
            "classificacao": "TEXT", "transcricao": "TEXT", "resumo": "TEXT",
            "tokens_usados": "INTEGER NOT NULL DEFAULT 0",
            "custo_estimado": "REAL NOT NULL DEFAULT 0", "erro_msg": "TEXT",
            "frames_json": "TEXT", "criado_em": "TEXT", "atualizado_em": "TEXT",
        }
        for column, definition in additions.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE videos ADD COLUMN {column} {definition}")
        now = utc_now()
        connection.execute(
            """UPDATE videos SET id=COALESCE(id, record_id),
               criado_em=COALESCE(criado_em, imported_at),
               atualizado_em=COALESCE(atualizado_em, updated_at),
               status=CASE
                 WHEN status IN ('pending','downloading','transcribing','classifying','summarizing','done','error') THEN status
                 ELSE 'pending' END"""
        )
        connection.execute(
            """UPDATE videos SET
               status=CASE a.status
                 WHEN 'Concluído' THEN 'done' WHEN 'Erro' THEN 'error'
                 WHEN 'Processando' THEN 'pending' ELSE videos.status END,
               classificacao=COALESCE(videos.classificacao, a.final_category),
               transcricao=COALESCE(videos.transcricao, a.transcript),
               resumo=COALESCE(videos.resumo, a.summary),
               erro_msg=COALESCE(videos.erro_msg, a.error_message), atualizado_em=?
               FROM analyses a WHERE a.jwplayer_id=videos.jwplayer_id""",
            (now,),
        )

    def import_rows(self, rows: list[dict], filename: str, *, replace: bool = False) -> dict:
        now = utc_now()
        created = updated = unchanged = 0
        with self.connect() as connection:
            if replace:
                # A nova planilha passa a ser o portfólio ativo.
                connection.execute("DELETE FROM videos")
                connection.execute("DELETE FROM analyses")
            for row in rows:
                current = connection.execute(
                    "SELECT lesson_name, jwplayer_id, keywords FROM videos WHERE record_id = ?",
                    (row["record_id"],),
                ).fetchone()
                values = (row["lesson_name"], row["jwplayer_id"], row["keywords"])
                if current is None:
                    connection.execute(
                        """INSERT INTO videos
                        (record_id, lesson_name, jwplayer_id, keywords, source_file, imported_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (row["record_id"], *values, filename, now, now),
                    )
                    connection.execute(
                        """UPDATE videos SET id=record_id, status='pending',
                           criado_em=imported_at, atualizado_em=updated_at WHERE record_id=?""",
                        (row["record_id"],),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO analyses (jwplayer_id, updated_at) VALUES (?, ?)",
                        (row["jwplayer_id"], now),
                    )
                    created += 1
                elif tuple(current) != values:
                    connection.execute(
                        """UPDATE videos SET lesson_name=?, jwplayer_id=?, keywords=?,
                        source_file=?, updated_at=? WHERE record_id=?""",
                        (*values, filename, now, row["record_id"]),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO analyses (jwplayer_id, updated_at) VALUES (?, ?)",
                        (row["jwplayer_id"], now),
                    )
                    updated += 1
                else:
                    unchanged += 1
            connection.execute(
                "INSERT INTO imports (filename, imported_at, total_rows, new_rows, updated_rows) VALUES (?, ?, ?, ?, ?)",
                (filename, now, len(rows), created, updated),
            )
        return {"total": len(rows), "new": created, "updated": updated, "unchanged": unchanged}

    def list_portfolio(self) -> list[dict]:
        query = """
        SELECT v.record_id, v.lesson_name, v.jwplayer_id, v.keywords,
               a.status, a.ai_category, a.final_category, a.summary,
               a.confidence, a.validation_status, a.analyzed_at, a.error_message
        FROM videos v LEFT JOIN analyses a ON a.jwplayer_id = v.jwplayer_id
        ORDER BY v.lesson_name COLLATE NOCASE
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query)]

    def unique_media(self, statuses: tuple[str, ...] | None = None) -> list[dict]:
        query = """
        SELECT v.jwplayer_id, MIN(v.lesson_name) lesson_name, COUNT(*) record_count,
               a.status, a.transcript, a.summary
        FROM videos v JOIN analyses a ON a.jwplayer_id = v.jwplayer_id
        """
        params: tuple = ()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE a.status IN ({placeholders})"
            params = statuses
        query += " GROUP BY v.jwplayer_id ORDER BY lesson_name COLLATE NOCASE"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, params)]

    def update_analysis(self, jwplayer_id: str, **values) -> None:
        allowed = {
            "status", "ai_category", "final_category", "summary", "confidence",
            "validation_status", "transcript", "source_title", "duration",
            "error_message", "analyzed_at",
        }
        clean = {key: value for key, value in values.items() if key in allowed}
        clean["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE analyses SET {assignments} WHERE jwplayer_id = ?",
                (*clean.values(), jwplayer_id),
            )
            pipeline_status = {
                "Pendente": "pending", "Processando": "downloading",
                "Concluído": "done", "Erro": "error",
            }.get(values.get("status"))
            mirrored = {
                "classificacao": values.get("final_category") or values.get("ai_category"),
                "transcricao": values.get("transcript"), "resumo": values.get("summary"),
                "erro_msg": values.get("error_message"),
            }
            if pipeline_status:
                mirrored["status"] = pipeline_status
            mirror_clean = {key: value for key, value in mirrored.items() if key == "erro_msg" or value is not None}
            mirror_clean["atualizado_em"] = utc_now()
            assignments = ", ".join(f"{key}=?" for key in mirror_clean)
            connection.execute(
                f"UPDATE videos SET {assignments} WHERE jwplayer_id=?",
                (*mirror_clean.values(), jwplayer_id),
            )

    def pipeline_items(self, statuses: tuple[str, ...] = ("pending",)) -> list[dict]:
        placeholders = ",".join("?" for _ in statuses)
        query = f"""
        SELECT jwplayer_id id, MIN(lesson_name) lesson_name, MIN(url_path) url_path,
               MIN(status) status, MIN(classificacao) classificacao,
               MIN(transcricao) transcricao, MIN(resumo) resumo,
               MAX(tokens_usados) tokens_usados, MAX(custo_estimado) custo_estimado,
               MIN(erro_msg) erro_msg, MIN(frames_json) frames_json
        FROM videos WHERE status IN ({placeholders})
        GROUP BY jwplayer_id ORDER BY lesson_name COLLATE NOCASE
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, statuses)]

    def update_pipeline(self, video_id: str, **values) -> None:
        allowed = {
            "url_path", "status", "classificacao", "transcricao", "resumo",
            "tokens_usados", "custo_estimado", "erro_msg", "frames_json",
        }
        clean = {key: value for key, value in values.items() if key in allowed}
        if "status" in clean and clean["status"] not in {
            "pending", "downloading", "transcribing", "classifying", "summarizing", "done", "error",
        }:
            raise ValueError(f"Status de pipeline inválido: {clean['status']}")
        clean["atualizado_em"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in clean)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE videos SET {assignments} WHERE jwplayer_id=? OR id=?",
                (*clean.values(), video_id, video_id),
            )

    def retry_errors(self) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE videos SET status='pending', erro_msg=NULL, atualizado_em=? WHERE status='error'",
                (utc_now(),),
            )
            return cursor.rowcount

    def pipeline_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(DISTINCT jwplayer_id) total FROM videos GROUP BY status"
            )
            counts = {status: 0 for status in (
                "pending", "downloading", "transcribing", "classifying", "summarizing", "done", "error",
            )}
            counts.update({row["status"]: row["total"] for row in rows})
            return counts

    def stats(self) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) records, COUNT(DISTINCT v.jwplayer_id) media,
                COALESCE(SUM(CASE WHEN a.status='Concluído' THEN 1 ELSE 0 END), 0) analyzed_records,
                COUNT(DISTINCT CASE WHEN a.status='Concluído' THEN v.jwplayer_id END) analyzed_media,
                COUNT(DISTINCT CASE WHEN a.validation_status='Validado' THEN v.jwplayer_id END) validated_media
                FROM videos v LEFT JOIN analyses a ON a.jwplayer_id=v.jwplayer_id"""
            ).fetchone()
            return dict(row)
