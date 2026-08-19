from __future__ import annotations

import csv
import io
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.portfolio.ai import AIError, analyze_frames, validate_ollama_model
from src.portfolio.database import Database, utc_now
from src.portfolio.ingestion import SpreadsheetValidationError, read_spreadsheet
from src.portfolio.jw_session import JWBrowserSession, JWSessionError
from src.portfolio.frames import extract_frames
from src.portfolio.transcription import transcribe_hls


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("CETRUS_DATA_DIR", BASE_DIR / "data"))
DATABASE = Database(DATA_DIR / "portfolio.db")
WEB_DIR = BASE_DIR / "web"
JW_PROPERTY_ID = "XdfUPSCL"
JW_LIBRARY_URL = f"https://dashboard.jwplayer.com/p/{JW_PROPERTY_ID}/media"
JW_SESSION = JWBrowserSession()
PROCESSOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-processing")
ANALYSIS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_BATCH_LOCK = threading.Lock()
ACTIVE_BATCH: threading.Event | None = None


class BatchCancelled(Exception):
    pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    JW_SESSION.close()
    PROCESSOR.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Portfólio de vídeos Cetrus", version="2.0.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


class LoginRequest(BaseModel):
    email: str
    password: str


class ProcessRequest(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=1000)
    provider: str = "Claude"
    api_key: str = ""
    model: str = "claude-sonnet-4-5"
    ollama_url: str = "http://127.0.0.1:11434"
    whisper_model: str = "small"
    analysis_mode: str = "frames"
    frame_count: int = Field(default=8, ge=4, le=16)


class ValidationRequest(BaseModel):
    jwplayer_id: str
    final_category: str
    summary: str = Field(max_length=500)
    validated: bool = True


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/stats")
def stats():
    return {**DATABASE.stats(), "jw_library_url": JW_LIBRARY_URL}


@app.get("/api/videos")
def videos(search: str = "", status: str = "", category: str = ""):
    rows = DATABASE.list_portfolio()
    needle = search.casefold().strip()
    if needle:
        rows = [row for row in rows if needle in " ".join(
            str(row.get(key) or "") for key in ("lesson_name", "keywords", "jwplayer_id")
        ).casefold()]
    if status:
        rows = [row for row in rows if (row.get("status") or "Pendente") == status]
    if category:
        rows = [row for row in rows if row.get("final_category") == category]
    return {"items": rows, "total": len(rows)}


@app.post("/api/import")
async def import_spreadsheet(file: UploadFile = File(...)):
    content = await file.read()
    try:
        rows, report = read_spreadsheet(content, file.filename or "planilha.xlsx")
    except SpreadsheetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cancel_active_batch()
    outcome = DATABASE.import_rows(rows, file.filename or "planilha.xlsx", replace=True)
    return {**report, **outcome}


@app.post("/api/import-and-process")
async def import_and_process(
    file: UploadFile = File(...),
    provider: str = Form("Claude"),
    api_key: str = Form(""),
    model: str = Form("claude-sonnet-4-5"),
    ollama_url: str = Form("http://127.0.0.1:11434"),
    whisper_model: str = Form("small"),
    analysis_mode: str = Form("frames"),
    frame_count: int = Form(8),
):
    if provider not in {"Claude", "Ollama"}:
        raise HTTPException(status_code=422, detail="Selecione Claude ou Ollama.")
    if JW_SESSION.status()["state"] != "connected":
        raise HTTPException(status_code=409, detail="Conecte a biblioteca JW Player antes de enviar a planilha.")
    content = await file.read()
    try:
        rows, report = read_spreadsheet(content, file.filename or "planilha.xlsx")
    except SpreadsheetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cancel_active_batch()
    outcome = DATABASE.import_rows(rows, file.filename or "planilha.xlsx", replace=True)
    imported_media = list(dict.fromkeys(row["jwplayer_id"] for row in rows))
    states = {item["jwplayer_id"]: item["status"] for item in DATABASE.unique_media()}
    pending_media = [media_id for media_id in imported_media if states.get(media_id) != "Concluído"]
    request = ProcessRequest(
        media_ids=pending_media or imported_media[:0], provider=provider, api_key=api_key,
        model=model, ollama_url=ollama_url, whisper_model=whisper_model,
        analysis_mode=analysis_mode, frame_count=frame_count,
    ) if pending_media else None
    queued = enqueue_jobs(request) if request else []
    api_key = ""
    return {**report, **outcome, "pending_media": len(pending_media), "jobs": queued}


@app.post("/api/jw/login")
def jw_login(request: LoginRequest):
    try:
        return JW_SESSION.login(request.email, request.password, JW_PROPERTY_ID)
    except JWSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível iniciar a sessão JW Player. Reinicie a aplicação e tente novamente.",
        ) from exc


@app.get("/api/jw/status")
def jw_status(verify: bool = False):
    return JW_SESSION.verify() if verify else JW_SESSION.status()


def update_job(job_id: str, **values) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(values)


def cancel_active_batch() -> None:
    global ACTIVE_BATCH
    with ACTIVE_BATCH_LOCK:
        if ACTIVE_BATCH is not None:
            ACTIVE_BATCH.cancelled = True
            ACTIVE_BATCH.reason = "Lote substituído por uma nova planilha."
            ACTIVE_BATCH.set()
        ACTIVE_BATCH = None
    with JOBS_LOCK:
        JOBS.clear()


def ensure_batch_active(batch_abort: threading.Event) -> None:
    if getattr(batch_abort, "cancelled", False):
        raise BatchCancelled("Lote substituído por uma nova planilha.")


def is_session_interruption(exc: Exception) -> bool:
    if not isinstance(exc, JWSessionError):
        return False
    message = str(exc).casefold()
    return any(marker in message for marker in (
        "conecte uma sessão", "navegador jw player foi fechado",
        "sessão jw player expirou", "sessão expirou", "autenticação",
    ))


def run_media_job(job_id: str, media_id: str, request: ProcessRequest,
                  batch_abort: threading.Event) -> None:
    with ANALYSIS_LOCK:
        _run_media_job_serial(job_id, media_id, request, batch_abort)


def _run_media_job_serial(job_id: str, media_id: str, request: ProcessRequest,
                          batch_abort: threading.Event) -> None:
    if getattr(batch_abort, "cancelled", False):
        update_job(job_id, state="cancelled", message="Lote substituído por uma nova planilha.")
        return
    if batch_abort.is_set():
        reason = getattr(batch_abort, "reason", "Corrija a conexão ou configuração e tente novamente.")
        DATABASE.update_analysis(media_id, status="Pendente", error_message=None)
        update_job(job_id, state="paused", message=f"Lote pausado: {reason}")
        return
    update_job(job_id, state="running", message="Capturando o vídeo no JW Player")
    DATABASE.update_analysis(media_id, status="Processando", error_message=None)
    work_dir = DATA_DIR / "work" / media_id
    try:
        captured = JW_SESSION.capture_media(media_id)
        ensure_batch_active(batch_abort)
        update_job(job_id, message=f"Extraindo {request.frame_count} frames distribuídos")
        frames, duration = extract_frames(captured["master_url"], work_dir, request.frame_count)
        ensure_batch_active(batch_abort)
        transcript = ""
        if request.analysis_mode == "hybrid":
            update_job(job_id, message="Transcrevendo áudio complementar (modo híbrido)")
            transcript = transcribe_hls(captured["master_url"], work_dir, request.whisper_model)
            ensure_batch_active(batch_abort)
        title = next(
            (item["lesson_name"] for item in DATABASE.unique_media() if item["jwplayer_id"] == media_id),
            media_id,
        )
        update_job(job_id, message="Classificando e resumindo com IA")
        if request.provider != "Ollama" and not request.api_key:
            raise RuntimeError(f"Informe a chave da {request.provider}.")
        result = analyze_frames(
            request.provider, request.api_key, request.model, title, frames,
            transcript=transcript, ollama_url=request.ollama_url,
        )
        ensure_batch_active(batch_abort)
        DATABASE.update_analysis(
            media_id, status="Concluído", ai_category=result["category"],
            final_category=result["category"], summary=result["summary"],
            confidence=result["confidence"], validation_status="Pendente",
            transcript=transcript, source_title=title, duration=duration,
            analyzed_at=utc_now(), error_message=None,
        )
        update_job(job_id, state="completed", message="Processamento concluído", result=result)
    except BatchCancelled:
        update_job(job_id, state="cancelled", message="Lote substituído por uma nova planilha.")
    except Exception as exc:
        message = str(exc)
        if is_session_interruption(exc):
            batch_abort.reason = "A sessão do JW Player foi interrompida. Reconecte para retomar."
            batch_abort.set()
            DATABASE.update_analysis(media_id, status="Pendente", error_message=message)
            update_job(
                job_id, state="paused",
                message="Processamento pausado. Reconecte o JW Player e envie novamente a planilha para retomar.",
            )
        elif isinstance(exc, AIError):
            batch_abort.reason = message
            batch_abort.set()
            DATABASE.update_analysis(media_id, status="Pendente", error_message=message)
            update_job(
                job_id, state="paused",
                message=f"Lote pausado por configuração da IA: {message}",
            )
        else:
            DATABASE.update_analysis(media_id, status="Erro", error_message=message)
            update_job(job_id, state="error", message=message)
    finally:
        request.api_key = ""


def enqueue_jobs(request: ProcessRequest) -> list[dict]:
    global ACTIVE_BATCH
    if request.provider not in {"Claude", "Ollama"}:
        raise HTTPException(status_code=422, detail="Selecione Claude ou Ollama.")
    if JW_SESSION.status()["state"] != "connected":
        raise HTTPException(status_code=409, detail="Conecte o JW Player antes de processar.")
    if request.provider != "Ollama" and not request.api_key:
        raise HTTPException(status_code=422, detail=f"Informe a chave da {request.provider}.")
    if request.provider == "Ollama":
        try:
            validate_ollama_model(request.ollama_url, request.model)
        except AIError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    jobs = []
    batch_abort = threading.Event()
    batch_abort.cancelled = False
    with ACTIVE_BATCH_LOCK:
        ACTIVE_BATCH = batch_abort
    for media_id in dict.fromkeys(request.media_ids):
        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id, "media_id": media_id, "state": "queued",
                "message": "Na fila", "created_at": utc_now(),
            }
        PROCESSOR.submit(run_media_job, job_id, media_id, request.model_copy(deep=True), batch_abort)
        jobs.append(JOBS[job_id])
    request.api_key = ""
    return jobs


@app.post("/api/process")
def process(request: ProcessRequest):
    return {"jobs": enqueue_jobs(request)}


@app.get("/api/jobs")
def jobs():
    with JOBS_LOCK:
        return {"items": list(JOBS.values())[-100:]}


@app.post("/api/validate")
def validate(request: ValidationRequest):
    DATABASE.update_analysis(
        request.jwplayer_id, final_category=request.final_category,
        summary=" ".join(request.summary.split()),
        validation_status="Validado" if request.validated else "Pendente",
    )
    return {"ok": True}


@app.get("/api/export.csv")
def export_csv():
    output = io.StringIO()
    fields = ["lesson_name", "final_category", "summary", "jwplayer_id", "status", "validation_status", "confidence", "keywords"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writerow({
        "lesson_name": "Nome da aula", "final_category": "Modelo de aula",
        "summary": "Resumo do conteúdo", "jwplayer_id": "JWPlayer ID", "status": "Status",
        "validation_status": "Validação", "confidence": "Confiança", "keywords": "Palavras-chave",
    })
    writer.writerows(DATABASE.list_portfolio())
    return Response(
        content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="portfolio_cetrus.csv"'},
    )
