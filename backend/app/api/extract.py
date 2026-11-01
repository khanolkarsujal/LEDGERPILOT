"""
API router for ledger page extraction.

Endpoints:
- POST /api/extract: Synchronous extraction returning LedgerPageExtraction JSON.
- POST /api/extract/jobs: Asynchronous job creation returning 202 Accepted with job_id.
- GET /api/extract/jobs/{job_id}: Poll job status, lifecycle stages, backend events, and results.
"""

import io
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from app.extraction.gemini_extractor import (
    DAILY_QUOTA_USER_MESSAGE,
    QUOTA_ERROR_CODE,
    GeminiQuotaExhaustedError,
    extract_ledger_page,
)
from app.schemas.ledger import LedgerPageExtraction

router = APIRouter(prefix="/api", tags=["Extraction"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/jpg"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class ProcessingStage(str, Enum):
    UPLOAD_RECEIVED = "upload_received"
    PREPROCESSING = "preprocessing"
    GEMINI_REQUEST_STARTED = "gemini_request_started"
    WAITING_GEMINI = "waiting_gemini"
    PARSING_EXTRACTION = "parsing_extraction"
    COMPLETED = "completed"
    FAILED = "failed"


class JobEvent(BaseModel):
    timestamp: float
    iso_time: str
    stage: ProcessingStage
    message: str
    details: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    filename: str
    file_size_bytes: int
    status: str  # "pending", "processing", "completed", "failed"
    current_stage: ProcessingStage
    stage_message: str
    events: List[JobEvent]
    elapsed_time_s: float
    result: Optional[LedgerPageExtraction] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


# In-memory job registry for real-time progress tracking
JOBS: Dict[str, Dict[str, Any]] = {}


def _record_event(job_id: str, stage: ProcessingStage, message: str, details: Optional[str] = None) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    now = time.time()
    iso = datetime.now(timezone.utc).isoformat()
    job["current_stage"] = stage
    job["stage_message"] = message
    event = JobEvent(
        timestamp=now,
        iso_time=iso,
        stage=stage,
        message=message,
        details=details,
    )
    job["events"].append(event)


def _process_job_worker(job_id: str, image_bytes: bytes) -> None:
    """Synchronous worker executed in background thread."""
    def on_stage(stage_name: str, msg: str, det: Optional[str] = None):
        try:
            st = ProcessingStage(stage_name)
        except ValueError:
            st = ProcessingStage.WAITING_GEMINI
        _record_event(job_id, st, msg, det)

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        extraction = extract_ledger_page(image, on_stage_change=on_stage)

        job = JOBS.get(job_id)
        if job:
            job["result"] = extraction
            job["status"] = "completed"
            job["completed_at"] = time.time()
    except GeminiQuotaExhaustedError as e:
        job = JOBS.get(job_id)
        if job:
            # Fail only this job. Previously completed jobs in JOBS stay intact.
            job["status"] = "failed"
            job["error"] = str(e) or DAILY_QUOTA_USER_MESSAGE
            job["error_code"] = getattr(e, "error_code", None) or QUOTA_ERROR_CODE
            job["completed_at"] = time.time()
            _record_event(job_id, ProcessingStage.FAILED, str(e) or DAILY_QUOTA_USER_MESSAGE)
    except Exception as e:
        job = JOBS.get(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = str(e)
            job["completed_at"] = time.time()
            _record_event(job_id, ProcessingStage.FAILED, f"Extraction failed: {str(e)}")


@router.post(
    "/extract/jobs",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a background extraction job for a ledger photo",
)
async def create_extraction_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Handwritten ledger photograph (JPEG or PNG, max 10MB)"),
) -> JobStatusResponse:
    """
    Accepts a ledger photograph, validates size/format, creates an in-memory job ID,
    spawns background processing, and returns immediately with job ID and initial status.
    """
    # 1. Validate extension and content type
    filename = file.filename or "ledger_photo"
    file_ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if file_ext not in ALLOWED_EXTENSIONS and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{file.content_type or file_ext}'. Supported formats: JPEG (.jpg, .jpeg) and PNG (.png).",
        )

    # 2. Read bytes and validate size
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds the 10 MB limit ({len(contents) / (1024 * 1024):.2f} MB).",
        )

    # 3. Quick image load validation
    try:
        test_img = Image.open(io.BytesIO(contents))
        test_img.verify()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted image file: {str(e)}",
        )

    # 4. Create Job Record
    job_id = str(uuid.uuid4())
    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    initial_event = JobEvent(
        timestamp=start_time,
        iso_time=now_iso,
        stage=ProcessingStage.UPLOAD_RECEIVED,
        message=f"Upload received and verified: {filename} ({len(contents) / 1024:.1f} KB)",
        details=f"MIME: {file.content_type or 'image'}, Size: {len(contents)} bytes",
    )

    job_entry = {
        "job_id": job_id,
        "filename": filename,
        "file_size_bytes": len(contents),
        "status": "processing",
        "current_stage": ProcessingStage.UPLOAD_RECEIVED,
        "stage_message": "Upload received and validated",
        "events": [initial_event],
        "created_at": start_time,
        "completed_at": None,
        "result": None,
        "error": None,
        "error_code": None,
    }
    JOBS[job_id] = job_entry

    # 5. Dispatch worker to background tasks
    background_tasks.add_task(_process_job_worker, job_id, contents)

    return JobStatusResponse(
        job_id=job_id,
        filename=filename,
        file_size_bytes=len(contents),
        status="processing",
        current_stage=ProcessingStage.UPLOAD_RECEIVED,
        stage_message="Upload received and validated",
        events=[initial_event],
        elapsed_time_s=0.0,
        result=None,
        error=None,
        error_code=None,
    )


@router.get(
    "/extract/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get extraction job status, live progress stages, and final extraction results",
)
def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Returns current stage, full event activity history, elapsed time, and result/error.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction job '{job_id}' not found.",
        )

    now = time.time()
    end_time = job["completed_at"] if job["completed_at"] else now
    elapsed = round(end_time - job["created_at"], 2)

    return JobStatusResponse(
        job_id=job["job_id"],
        filename=job["filename"],
        file_size_bytes=job["file_size_bytes"],
        status=job["status"],
        current_stage=job["current_stage"],
        stage_message=job["stage_message"],
        events=job["events"],
        elapsed_time_s=elapsed,
        result=job["result"],
        error=job["error"],
        error_code=job.get("error_code"),
    )


@router.post(
    "/extract",
    response_model=LedgerPageExtraction,
    summary="Synchronously extract structured financial records from a handwritten Marathi ledger photograph",
    status_code=status.HTTP_200_OK,
)
async def extract_ledger(
    file: UploadFile = File(..., description="Handwritten ledger photograph (JPEG or PNG, max 10MB)"),
) -> LedgerPageExtraction:
    """
    Synchronous fallback endpoint: Receives image, validates format/size, runs extraction
    via worker threadpool, and returns structured LedgerPageExtraction directly.
    """
    # 1. Validate file extension
    filename = file.filename or ""
    file_ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if file_ext not in ALLOWED_EXTENSIONS and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{file.content_type or file_ext}'. Supported formats: JPEG (.jpg, .jpeg) and PNG (.png).",
        )

    # 2. Read contents into memory and validate size
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds the 10 MB limit ({len(contents) / (1024 * 1024):.2f} MB).",
        )

    # 3. Validate image integrity and normalize EXIF orientation
    try:
        image = Image.open(io.BytesIO(contents))
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted image file: {str(e)}",
        )

    # 4. Extract structured records with Gemini in threadpool
    try:
        extraction = await run_in_threadpool(extract_ledger_page, image)
        return extraction
    except GeminiQuotaExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e) or DAILY_QUOTA_USER_MESSAGE,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction service configuration error: {str(e)}",
        )
    except Exception as e:
        err_msg = str(e)
        if "503" in err_msg or "unavailable" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vision AI service is currently experiencing high demand. Please try again in a few moments.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Extraction failed: {err_msg}",
        )
