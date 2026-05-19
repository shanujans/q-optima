# Vultr orchestrator delegates transcription to AMD perception node.

from __future__ import annotations
import logging, os
from datetime import datetime, timezone
from typing import Any, Dict
import httpx
from agent.state import AgentState

logger = logging.getLogger(__name__)
AMD_WHISPER_URL = os.getenv("AMD_WHISPER_URL", "").rstrip("/")

def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {"step":step,"label":label,"status":status,
            "message":message,"detail":detail,
            "timestamp":datetime.now(timezone.utc).isoformat()}

FALLBACK = ("Find the optimal delivery route visiting all locations "
            "shown in the image, minimising total travel distance.")

def transcribe_audio_node(state: AgentState) -> AgentState:
    logs = list(state.get("step_logs", []))
    audio_bytes = state.get("audio_bytes")

    if not audio_bytes:
        logs.append(_log("transcribe","🎙️  Audio transcription","complete",
                         "No audio — using default instruction.", FALLBACK))
        return {**state,"transcribed_text":FALLBACK,
                "current_step":"transcribed","step_logs":logs}

    if not AMD_WHISPER_URL:
        logs.append(_log("transcribe","🎙️  Audio transcription","complete",
                         "AMD_WHISPER_URL not set — using default (dev mode).", FALLBACK))
        return {**state,"transcribed_text":FALLBACK,
                "current_step":"transcribed","step_logs":logs}

    logs.append(_log("transcribe","🎙️  Audio transcription","running",
                     f"Calling AMD Whisper at {AMD_WHISPER_URL} …"))
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(f"{AMD_WHISPER_URL}/api/transcribe",
                            files={"audio":("audio.webm",audio_bytes,"audio/webm")})
            r.raise_for_status()
        text = r.json().get("transcribed_text","").strip()
        if not text:
            raise ValueError("Empty transcription returned")
        logs[-1].update({"status":"complete",
                         "message":f"AMD Whisper transcribed {len(text)} chars.",
                         "detail":text})
        return {**state,"transcribed_text":text,
                "current_step":"transcribed","step_logs":logs}
    except Exception as e:
        msg = f"AMD call failed ({e}) — using default."
        logs[-1].update({"status":"complete","message":msg,"detail":FALLBACK})
        return {**state,"transcribed_text":FALLBACK,
                "current_step":"transcribed","step_logs":logs}
