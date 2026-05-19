# Two modes:
#   BATCH  — uploaded audio file → POST /v2/jobs → poll → transcript
#   RT     — live mic stream via WebSocket proxy (see main.py /ws/transcribe)
#
# Fallback chain:  Speechmatics → AMD Whisper node → default instruction

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from agent.state import AgentState

logger = logging.getLogger(__name__)

SPEECHMATICS_API_KEY  = os.getenv("SPEECHMATICS_API_KEY", "")
SPEECHMATICS_LANGUAGE = os.getenv("SPEECHMATICS_LANGUAGE", "en")
SPEECHMATICS_BASE     = "https://asr.api.speechmatics.com/v2"
AMD_WHISPER_URL       = os.getenv("AMD_WHISPER_URL", "").rstrip("/")

# Batch job config — enable speaker diarization for multi-commander scenarios
BATCH_CONFIG = {
    "type": "transcription",
    "transcription_config": {
        "language":             SPEECHMATICS_LANGUAGE,
        "diarization":          "speaker",          # identifies multiple speakers
        "operating_point":      "enhanced",          # highest accuracy model
        "enable_entities":      True,                # extract city names, numbers
        "punctuation_overrides": {
            "permitted_marks": [".", ",", "?", "!"]
        },
    },
}

POLL_INTERVAL = 2.0    # seconds between job status checks
POLL_TIMEOUT  = 120.0  # max seconds to wait for transcription


def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {
        "step": step, "label": label, "status": status,
        "message": message, "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Speechmatics batch transcription ─────────────────────────────────────────

async def _submit_job(audio_bytes: bytes, filename: str) -> Optional[str]:
    """Submit audio to Speechmatics batch API. Returns job_id or None."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SPEECHMATICS_BASE}/jobs",
            headers={"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"},
            files={"data_file": (filename, audio_bytes, "audio/webm")},
            data={"config": __import__("json").dumps(BATCH_CONFIG)},
        )
        resp.raise_for_status()
        job_id = resp.json().get("id")
        logger.info("Speechmatics job submitted: %s", job_id)
        return job_id


async def _poll_job(job_id: str) -> Optional[str]:
    """Poll until job is done. Returns transcript text or None."""
    deadline = time.time() + POLL_TIMEOUT
    async with httpx.AsyncClient(timeout=15.0) as client:
        while time.time() < deadline:
            resp = await client.get(
                f"{SPEECHMATICS_BASE}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"},
            )
            resp.raise_for_status()
            job = resp.json().get("job", {})
            status = job.get("status")
            logger.debug("Speechmatics job %s status: %s", job_id, status)

            if status == "done":
                # Fetch the transcript
                t_resp = await client.get(
                    f"{SPEECHMATICS_BASE}/jobs/{job_id}/transcript",
                    headers={"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"},
                    params={"format": "txt"},
                )
                t_resp.raise_for_status()
                return t_resp.text.strip()

            if status in ("rejected", "deleted"):
                raise ValueError(f"Speechmatics job {job_id} {status}")

            await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Speechmatics job {job_id} timed out after {POLL_TIMEOUT}s")


async def _transcribe_with_speechmatics(
    audio_bytes: bytes, filename: str
) -> str:
    """Full Speechmatics batch transcription flow."""
    job_id = await _submit_job(audio_bytes, filename)
    if not job_id:
        raise ValueError("Speechmatics did not return a job ID.")
    text = await _poll_job(job_id)
    if not text:
        raise ValueError("Speechmatics returned empty transcript.")
    return text


# ── AMD Whisper fallback ──────────────────────────────────────────────────────

def _transcribe_with_amd(audio_bytes: bytes) -> str:
    """Call AMD perception node over HTTP."""
    if not AMD_WHISPER_URL:
        raise RuntimeError("AMD_WHISPER_URL not configured.")
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{AMD_WHISPER_URL}/api/transcribe",
            files={"audio": ("audio.webm", audio_bytes, "audio/webm")},
        )
        r.raise_for_status()
        text = r.json().get("transcribed_text", "").strip()
        if not text:
            raise ValueError("AMD Whisper returned empty transcription.")
        return text


# ── LangGraph node ────────────────────────────────────────────────────────────

def transcribe_audio_node(state: AgentState) -> AgentState:
    """
    Priority order:
      1. Speechmatics batch API  (if SPEECHMATICS_API_KEY set)
      2. AMD Whisper HTTP node   (if AMD_WHISPER_URL set)
      3. Default fallback instruction
    """
    logs: list = list(state.get("step_logs", []))
    audio_bytes: bytes | None = state.get("audio_bytes")

    FALLBACK = (
        "Find the optimal delivery route visiting all locations "
        "shown in the image, minimising total travel distance."
    )

    if not audio_bytes:
        logs.append(_log("transcribe", "🎙️  Speechmatics STT", "complete",
                         "No audio — using default instruction.", FALLBACK))
        return {**state, "transcribed_text": FALLBACK,
                "current_step": "transcribed", "step_logs": logs}

    # ── Try Speechmatics first ────────────────────────────────────────────────
    if SPEECHMATICS_API_KEY:
        logs.append(_log("transcribe", "🎙️  Speechmatics STT", "running",
                         "Submitting audio to Speechmatics enhanced model …"))
        try:
            text = asyncio.run(
                _transcribe_with_speechmatics(audio_bytes, "logistics_memo.webm")
            )
            logs[-1].update({
                "status": "complete",
                "message": f"Speechmatics transcribed {len(text)} chars (speaker diarization on).",
                "detail": text,
            })
            logger.info("Speechmatics transcript: '%s…'", text[:120])
            return {**state, "transcribed_text": text,
                    "current_step": "transcribed", "step_logs": logs}
        except Exception as exc:
            logger.warning("Speechmatics failed — trying AMD: %s", exc)
            logs[-1].update({"status": "running",
                             "message": f"Speechmatics failed ({exc}) — falling back to AMD Whisper …"})

    # ── Fallback: AMD Whisper ─────────────────────────────────────────────────
    if AMD_WHISPER_URL:
        try:
            text = _transcribe_with_amd(audio_bytes)
            logs[-1].update({"status": "complete",
                             "message": f"AMD Whisper transcribed {len(text)} chars.",
                             "detail": text})
            return {**state, "transcribed_text": text,
                    "current_step": "transcribed", "step_logs": logs}
        except Exception as exc:
            logger.warning("AMD Whisper failed: %s", exc)

    # ── Final fallback ────────────────────────────────────────────────────────
    logs[-1].update({"status": "complete",
                     "message": "All STT services unavailable — using default instruction.",
                     "detail": FALLBACK})
    return {**state, "transcribed_text": FALLBACK,
            "current_step": "transcribed", "step_logs": logs}
