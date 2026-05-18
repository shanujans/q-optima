# backend/main.py
# Q-Optima FastAPI backend entry point
#
# Endpoints:
#   POST /api/solve         — accept image + audio upload, return job_id
#   GET  /api/status/{id}  — poll live job status (step logs + result)
#   GET  /api/health        — liveness probe (Vercel / Cloudflare health checks)
#
# Architecture:
#   - Multipart upload is received synchronously (fast).
#   - The LangGraph agent runs in a ThreadPoolExecutor background task so the
#     upload endpoint returns immediately.
#   - An in-memory dict stores JobRecord objects; fine for a single-instance
#     demo.  Replace with Redis for production multi-instance deployments.
#   - CORS is configured to accept requests from any Vercel preview URL
#     AND the Cloudflare Tunnel URL (both set via ALLOWED_ORIGINS env var).

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from fastapi.responses import JSONResponse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import FastAPI
from dotenv import load_dotenv
load_dotenv()
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# --- Internal imports ---
from agent.graph import run_agent
from agent.state import AgentState
from models.schemas import (
    JobRecord,
    JobStatus,
    QuantumResult,
    SolveResponse,
    StatusResponse,
    StepLog,
    StepStatus,
    SolutionCandidate,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("q_optima.main")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS_RAW = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://*.vercel.app",
)
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Q-Optima API",
    description="Autonomous Quantum Logistics Agent — Milan AI Week 2026",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# --- CORS ---
# Note: wildcard patterns like "*.vercel.app" require allow_origin_regex.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.(vercel\.app|trycloudflare\.com)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"], 
)

# ---------------------------------------------------------------------------
# In-memory job registry
# ---------------------------------------------------------------------------
_job_registry: Dict[str, JobRecord] = {}
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="q-agent")

# Progress milestones mapped to steps (for progress_percent field)
_STEP_PROGRESS: Dict[str, int] = {
    "queued":         5,
    "transcribed":    20,
    "analyzed":       38,
    "circuit_built":  60,
    "executed":       82,
    "complete":       100,
    "error":          100,
}


# ---------------------------------------------------------------------------
# Background task: runs the LangGraph agent and updates the job registry
# ---------------------------------------------------------------------------

def _run_agent_background(
    job_id: str,
    audio_bytes: Optional[bytes],
    image_bytes: Optional[bytes],
    image_mime_type: str,
) -> None:
    """Synchronous function executed in the thread pool executor."""
    record = _job_registry[job_id]
    record.status = JobStatus.RUNNING
    record.current_step = "running"

    try:
        final_state: AgentState = run_agent(
            job_id=job_id,
            audio_bytes=audio_bytes,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )

        # --- Hydrate the job record from final_state ---
        step_logs = [StepLog(**log) for log in final_state.get("step_logs", [])]
        current_step = final_state.get("current_step", "unknown")

        if final_state.get("error_message"):
            record.status        = JobStatus.ERROR
            record.error_message = final_state["error_message"]
        else:
            # Build QuantumResult
            top = [
                SolutionCandidate(
                    bitstring=s["bitstring"],
                    route=s["route"],
                    distance=s["distance"],
                    probability=s["probability"],
                )
                for s in final_state.get("top_solutions", [])
            ]
            record.result = QuantumResult(
                problem_description=final_state.get("problem_description", ""),
                problem_type=final_state.get("problem_type", "tsp"),
                city_names=final_state.get("city_names", []),
                quantum_backend=final_state.get("quantum_backend", "aer_simulator"),
                num_qubits=final_state.get("num_qubits", 0),
                circuit_depth=final_state.get("circuit_depth", 0),
                qaoa_layers=final_state.get("qaoa_layers", 1),
                total_shots=final_state.get("total_shots", 0),
                best_bitstring=final_state.get("best_bitstring", ""),
                optimal_route=final_state.get("optimal_route", []),
                route_distance=final_state.get("route_distance", 0.0),
                human_readable_result=final_state.get("human_readable_result", ""),
                top_solutions=top,
                circuit_code_display=final_state.get("circuit_code_display", ""),
            )
            record.status = JobStatus.COMPLETE

        record.step_logs       = step_logs
        record.current_step    = current_step
        record.progress_percent = _STEP_PROGRESS.get(current_step, 50)

    except Exception as exc:
        logger.exception("Unhandled error in agent background task: %s", exc)
        record.status        = JobStatus.ERROR
        record.current_step  = "error"
        record.error_message = f"Internal agent error: {exc}"
        record.progress_percent = 100


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/solve")
async def solve(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(default=None),   # default=None not ...
    audio: UploadFile = File(default=None),   # default=None not ...
):
    MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
 
    image_bytes = None
    image_mime_type = "image/jpeg"
    if image and image.filename:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_BYTES:
            return JSONResponse(status_code=413,
                                content={"detail": "Image too large"})
        image_mime_type = image.content_type or "image/jpeg"
 
    audio_bytes = None
    if audio and audio.filename:
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_BYTES:
            return JSONResponse(status_code=413,
                                content={"detail": "Audio too large"})
 
    job_id = str(uuid.uuid4())
 
    # Import your registry + runner (adjust import path if needed)
    from agent.graph import run_agent
    from models.schemas import JobRecord, JobStatus
 
    _job_registry[job_id] = JobRecord(
        job_id=job_id,
        status=JobStatus.QUEUED,
        current_step="queued",
        progress_percent=5,
    )
 
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_agent_background,
        job_id, audio_bytes, image_bytes, image_mime_type,
    )
 
    # Explicit JSONResponse — guarantees Content-Type: application/json
    return JSONResponse(
        status_code=200,
        content={
            "job_id": job_id,
            "message": "Job accepted. Poll /api/status/{job_id} for live updates."
        }
    )
 
 
@app.get("/api/health")
async def health():
    from datetime import datetime, timezone
    return JSONResponse(content={
        "status": "ok",
        "service": "Q-Optima Quantum Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/status/{job_id}", response_model=StatusResponse, tags=["Agent"])
async def get_status(job_id: str):
    """
    Return the current status of a quantum agent job.
    The frontend polls this endpoint every 1.5 seconds to update the
    live timeline UI.
    """
    record = _job_registry.get(job_id)
    if not record:
        raise HTTPException(404, f"Job '{job_id}' not found.")

    return StatusResponse(
        job_id=record.job_id,
        status=record.status,
        current_step=record.current_step,
        progress_percent=record.progress_percent,
        step_logs=record.step_logs,
        result=record.result,
        error_message=record.error_message,
    )


@app.get("/api/jobs", tags=["System"])
async def list_jobs():
    """
    List all in-memory jobs (recent 50).  Useful during development / demo.
    """
    jobs = [
        {
            "job_id":           r.job_id,
            "status":           r.status,
            "current_step":     r.current_step,
            "progress_percent": r.progress_percent,
            "created_at":       r.created_at,
        }
        for r in list(_job_registry.values())[-50:]
    ]
    return {"total": len(jobs), "jobs": jobs}


# ---------------------------------------------------------------------------
# Startup event — warm up the Whisper model so the first request is fast
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    import os
    token = os.getenv("IBM_QUANTUM_TOKEN", "")
    if token:
        logger.info("IBM Quantum token loaded ✓ (%d chars)", len(token))
    else:
        logger.warning("IBM_QUANTUM_TOKEN not set — using Aer simulator")

    # Warm up Whisper model
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _preload_whisper)

async def warmup():
    """Pre-load the Whisper model in a background thread on startup."""
    logger.info("Warming up Whisper model …")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _preload_whisper)


def _preload_whisper() -> None:
    logger.info("Whisper runs on AMD node — no local warm-up needed ✓")


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
