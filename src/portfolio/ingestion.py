from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd


REQUIRED = {"video": "lesson_name", "id": "record_id", "jwplayer id": "jwplayer_id"}
OPTIONAL = {"palavras-chave": "keywords", "palavras chave": "keywords", "keywords": "keywords"}
JW_ID = re.compile(r"^[A-Za-z0-9]{8}$")


class SpreadsheetValidationError(ValueError):
    pass


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lstrip("\ufeff"))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def read_spreadsheet(content: bytes, filename: str) -> tuple[list[dict], dict]:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix not in {"xlsx", "xls", "csv"}:
        raise SpreadsheetValidationError("Envie um arquivo .xlsx, .xls ou .csv.")
    try:
        if suffix == "csv":
            frame = pd.read_csv(io.BytesIO(content), sep=None, engine="python", dtype=str)
        else:
            frame = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as exc:
        raise SpreadsheetValidationError(f"Não foi possível ler a planilha: {exc}") from exc

    columns = {normalize_header(column): column for column in frame.columns}
    missing = [label for label in REQUIRED if label not in columns]
    if missing:
        raise SpreadsheetValidationError("Colunas obrigatórias ausentes: " + ", ".join(missing))

    rename = {columns[label]: target for label, target in REQUIRED.items()}
    for label, target in OPTIONAL.items():
        if label in columns:
            rename[columns[label]] = target
            break
    frame = frame.rename(columns=rename)
    if "keywords" not in frame:
        frame["keywords"] = ""
    frame = frame[["record_id", "lesson_name", "jwplayer_id", "keywords"]].fillna("")
    for column in frame.columns:
        frame[column] = frame[column].astype(str).str.strip()
    frame = frame[(frame != "").any(axis=1)]

    errors = []
    for number, row in enumerate(frame.to_dict("records"), start=2):
        if not row["record_id"]:
            errors.append(f"linha {number}: ID vazio")
        if not row["lesson_name"]:
            errors.append(f"linha {number}: Vídeo vazio")
        if not JW_ID.fullmatch(row["jwplayer_id"]):
            errors.append(f"linha {number}: JWPlayer ID inválido")
    duplicated_records = frame[frame["record_id"].duplicated(keep=False)]["record_id"].unique().tolist()
    if duplicated_records:
        errors.append(f"IDs de registro duplicados: {', '.join(duplicated_records[:5])}")
    if errors:
        detail = "; ".join(errors[:12])
        if len(errors) > 12:
            detail += f"; e mais {len(errors) - 12} erro(s)"
        raise SpreadsheetValidationError(detail)

    rows = frame.to_dict("records")
    report = {
        "rows": len(rows),
        "unique_media": frame["jwplayer_id"].nunique(),
        "reused_media": len(rows) - frame["jwplayer_id"].nunique(),
    }
    return rows, report
