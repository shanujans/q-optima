# backend_amd/whisper_service.py
# Standalone FastAPI service — AMD Perception Node.
# Exposes two endpoints:
#   GET  /api/health      → liveness probe
#   POST /api/transcribe  → accepts audio file, returns transcribed text
#
# The Vultr orchestrator calls this service via the Cloudflare Tunnel URL
# set in AMD_WHISPER_URL env var.

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone

import torch
import whisper
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("q_optima.perception")

# ── Config ────────────────────────────────────────────────────────────────────
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
MAX_UPLOAD_MB      = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES   = MAX_UPLOAD_MB * 1024 * 1024

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Q-Optima Perception Node",
    description="AMD ROCm Whisper transcription service",
    version="1.0.0",
    docs_url="/api/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Locked down by Cloudflare Tunnel — internal only
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Whisper model (loaded once at startup) ────────────────────────────────────
_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(
            "Loading Whisper '%s' on device '%s'  HIP=%s",
            WHISPER_MODEL_SIZE, device, getattr(torch.version, "hip", "N/A"),
        )
        _model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        logger.info("Whisper model loaded ✓")
    return _model


# ── Startup warm-up ───────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _get_model)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return {
        "status":       "ok",
        "service":      "Q-Optima Perception Node",
        "whisper_model": WHISPER_MODEL_SIZE,
        "device":       device,
        "hip_version":  getattr(torch.version, "hip", None),
        "model_loaded": _model is not None,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/transcribe", tags=["Transcription"])
async def transcribe(
    audio: UploadFile = File(..., description="Audio file (mp3/wav/webm/ogg/m4a)"),
):
    """
    Accepts an audio file upload and returns the Whisper transcription.
    Called by the Vultr orchestrator's whisper_node.py via HTTP.
    """
    # Size guard
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Audio exceeds {MAX_UPLOAD_MB} MB limit.")
    if not audio_bytes:
        raise HTTPException(400, "Empty audio file received.")

    # Determine suffix for ffmpeg
    filename  = audio.filename or "audio.webm"
    suffix    = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    try:
        model = _get_model()

        # Write to temp file — Whisper requires a path (uses ffmpeg internally)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        result = model.transcribe(
            tmp_path,
            language="en",
            fp16=torch.cuda.is_available(),   # fp16 only on GPU
        )

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        text: str = result["text"].strip()
        if not text:
            raise ValueError("Whisper returned empty transcription.")

        logger.info(
            "Transcribed %d chars from '%s': '%s…'",
            len(text), filename, text[:80],
        )

        return {
            "transcribed_text": text,
            "language":         result.get("language", "en"),
            "duration_seconds": round(
                sum(s.get("end", 0) - s.get("start", 0)
                    for s in result.get("segments", [])), 2
            ),
            "filename": filename,
        }

    except Exception as exc:
        logger.exception("Transcription failed: %s", exc)
        raise HTTPException(500, f"Transcription error: {exc}")


# ── Dev entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("whisper_service:app", host="0.0.0.0", port=8001,
                reload=False, log_level="info")
