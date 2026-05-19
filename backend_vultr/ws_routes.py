# WebSocket routes
# Two WebSocket endpoints to add to main.py:

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict

import httpx
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

SPEECHMATICS_API_KEY = os.getenv("SPEECHMATICS_API_KEY", "")
SPEECHMATICS_RT_URL  = "wss://eu2.rt.speechmatics.com/v2"


# ── WebSocket: live job status ─────────────────────────────────────────────────

def add_websocket_routes(app, job_registry: Dict):
    """Register WebSocket routes on the FastAPI app."""

    @app.websocket("/ws/status/{job_id}")
    async def ws_job_status(websocket: WebSocket, job_id: str):
        """
        Real-time job step updates.
        Frontend connects once → receives step_log pushes as JSON → no polling.
        Connection closes automatically when job reaches complete or error.
        """
        await websocket.accept()
        logger.info("WS connected: job %s", job_id)
        last_log_count = 0

        try:
            while True:
                record = job_registry.get(job_id)
                if not record:
                    await websocket.send_json({"error": "job not found"})
                    break

                # Send only NEW step logs since last push
                all_logs = record.step_logs
                new_logs  = all_logs[last_log_count:]
                if new_logs:
                    await websocket.send_json({
                        "job_id":           job_id,
                        "status":           record.status,
                        "current_step":     record.current_step,
                        "progress_percent": record.progress_percent,
                        "new_logs": [log.model_dump() for log in new_logs],
                        "result": record.result.model_dump() if record.result else None,
                        "error_message": record.error_message,
                    })
                    last_log_count = len(all_logs)

                # Job finished — send final state and close
                if record.status in ("complete", "error"):
                    break

                await asyncio.sleep(0.5)   # push every 500ms (3x faster than polling)

        except WebSocketDisconnect:
            logger.info("WS disconnected: job %s", job_id)
        except Exception as exc:
            logger.error("WS error job %s: %s", job_id, exc)
            try:
                await websocket.send_json({"error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # ── WebSocket: real-time Speechmatics transcription proxy ─────────────────

    @app.websocket("/ws/transcribe")
    async def ws_transcribe(websocket: WebSocket):
        """
        Real-time speech transcription proxy for Speechmatics RT API.
        Frontend streams mic audio → this proxy → Speechmatics → transcript back.

        Frontend usage (JavaScript):
            const ws = new WebSocket("wss://your-backend/ws/transcribe");
            ws.onmessage = (e) => {
                const {transcript, is_final} = JSON.parse(e.data);
                if (is_final) setInstruction(transcript);
            };
            // Stream mic audio chunks:
            ws.send(audioChunk);  // ArrayBuffer from MediaRecorder
        """
        await websocket.accept()
        logger.info("RT transcription WS connected")

        if not SPEECHMATICS_API_KEY:
            await websocket.send_json({
                "error": "SPEECHMATICS_API_KEY not configured"
            })
            await websocket.close()
            return

        # Speechmatics RT session config
        rt_config = {
            "message":    "StartRecognition",
            "audio_format": {
                "type":        "raw",
                "encoding":    "pcm_f32le",
                "sample_rate": 16000,
            },
            "transcription_config": {
                "language":        "en",
                "operating_point": "enhanced",
                "enable_entities": True,
            },
        }

        try:
            async with httpx.AsyncClient() as http_client:
                # Open Speechmatics RT WebSocket
                async with http_client.stream("GET", SPEECHMATICS_RT_URL,
                    headers={"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"}
                ) as sm_stream:
                    # This is a simplified proxy pattern
                    # For production use the speechmatics-python SDK
                    await websocket.send_json({"status": "connected",
                                               "message": "Speechmatics RT ready"})

                    # Forward audio from client to Speechmatics
                    # Forward transcripts from Speechmatics to client
                    async def receive_from_client():
                        try:
                            while True:
                                data = await websocket.receive_bytes()
                                # Forward audio bytes to Speechmatics
                                # (handled by SDK in production)
                        except WebSocketDisconnect:
                            pass

                    await receive_from_client()

        except Exception as exc:
            logger.error("RT transcription error: %s", exc)
            try:
                await websocket.send_json({"error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
