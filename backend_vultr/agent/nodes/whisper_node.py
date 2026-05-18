# backend_vultr/agent/nodes/whisper_node.py
# Vultr orchestrator — does NOT import whisper locally.
# Calls the AMD perception node over HTTP via AMD_WHISPER_URL.
# Falls back gracefully if no audio or no AMD URL configured.

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from agent.state import AgentState

logger = logging.getLogger(__name__)

AMD_WHISPER_URL = os.getenv("AMD_WHISPER_URL", "").rstrip("/")
REQUEST_TIMEOUT = 60.0


def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {
        "step": step, "label": label, "status": status,
        "message": message, "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def transcribe_audio_node(state: AgentState) -> AgentState:
    logs: list = list(state.get("step_logs", []))
    audio_bytes: bytes | None = state.get("audio_bytes")

    FALLBACK = (
        "Find the optimal delivery route visiting all locations "
        "shown in the image, minimising total travel distance."
    )

    # No audio uploaded
    if not audio_bytes:
        logs.append(_log("transcribe", "🎙️  Audio transcription", "complete",
                         "No audio uploaded — using default instruction.", FALLBACK))
        return {**state, "transcribed_text": FALLBACK,
                "current_step": "transcribed", "step_logs": logs}

    # No AMD URL set (local dev)
    if not AMD_WHISPER_URL:
        logs.append(_log("transcribe", "🎙️  Audio transcription", "complete",
                         "AMD_WHISPER_URL not set — using default instruction (dev mode).",
                         FALLBACK))
        logger.warning("AMD_WHISPER_URL not configured — skipping transcription.")
        return {**state, "transcribed_text": FALLBACK,
                "current_step": "transcribed", "step_logs": logs}

    # Call AMD perception node
    logs.append(_log("transcribe", "🎙️  Audio transcription", "running",
                     f"Calling AMD Whisper node at {AMD_WHISPER_URL} …"))
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.post(
                f"{AMD_WHISPER_URL}/api/transcribe",
                files={"audio": ("audio.webm", audio_bytes, "audio/webm")},
            )
            r.raise_for_status()

        text: str = r.json().get("transcribed_text", "").strip()
        if not text:
            raise ValueError("AMD node returned empty transcription.")

        logs[-1].update({"status": "complete",
                          "message": f"Transcribed {len(text)} chars via AMD node.",
                          "detail": text})
        logger.info("Whisper (AMD): '%s…'", text[:100])
        return {**state, "transcribed_text": text,
                "current_step": "transcribed", "step_logs": logs}

    except Exception as exc:
        msg = f"AMD Whisper call failed ({exc}) — using default instruction."
        logger.warning(msg)
        logs[-1].update({"status": "complete", "message": msg, "detail": FALLBACK})
        return {**state, "transcribed_text": FALLBACK,
                "current_step": "transcribed", "step_logs": logs}