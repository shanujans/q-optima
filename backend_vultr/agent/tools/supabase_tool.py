# backend_vultr/agent/tools/supabase_tool.py
# ENHANCEMENT 6 — Supabase job history + analytics
# Free tier: 500 MB database, unlimited API calls.
# Setup: https://supabase.com → new project → copy URL + anon key
#
# SQL to run in Supabase dashboard (SQL editor):
# -----------------------------------------------
# CREATE TABLE jobs (
#   id              TEXT PRIMARY KEY,
#   created_at      TIMESTAMPTZ DEFAULT NOW(),
#   status          TEXT,
#   city_names      JSONB,
#   optimal_route   JSONB,
#   quantum_distance FLOAT,
#   classical_distance FLOAT,
#   improvement_pct  FLOAT,
#   carbon_kg        FLOAT,
#   quantum_backend  TEXT,
#   num_qubits       INT,
#   qaoa_layers      INT,
#   total_shots      INT,
#   weather_summary  TEXT,
#   human_readable_result TEXT
# );
# -----------------------------------------------
#
# ENV VARS:
#   SUPABASE_URL       — https://xxxx.supabase.co
#   SUPABASE_ANON_KEY  — from project settings → API

from __future__ import annotations
import logging, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL      = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
TABLE             = "jobs"


def _headers() -> Dict[str, str]:
    return {
        "apikey":        SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }


def save_job(
    job_id: str,
    city_names: List[str],
    optimal_route: List[str],
    quantum_distance: float,
    classical_distance: float = 0.0,
    improvement_pct: float = 0.0,
    carbon_kg: float = 0.0,
    quantum_backend: str = "aer_simulator",
    num_qubits: int = 0,
    qaoa_layers: int = 1,
    total_shots: int = 0,
    weather_summary: str = "",
    human_readable_result: str = "",
    status: str = "complete",
) -> bool:
    """
    Persist a completed job to Supabase.
    Returns True on success, False on failure (non-fatal).
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.debug("Supabase not configured — skipping persistence.")
        return False

    payload = {
        "id":                    job_id,
        "status":                status,
        "city_names":            city_names,
        "optimal_route":         optimal_route,
        "quantum_distance":      quantum_distance,
        "classical_distance":    classical_distance,
        "improvement_pct":       improvement_pct,
        "carbon_kg":             carbon_kg,
        "quantum_backend":       quantum_backend,
        "num_qubits":            num_qubits,
        "qaoa_layers":           qaoa_layers,
        "total_shots":           total_shots,
        "weather_summary":       weather_summary[:500],
        "human_readable_result": human_readable_result[:1000],
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                json=payload,
            )
            r.raise_for_status()
        logger.info("Job %s saved to Supabase.", job_id)
        return True
    except Exception as e:
        logger.warning("Supabase save failed (non-fatal): %s", e)
        return False


def get_analytics() -> Dict[str, Any]:
    """
    Fetch aggregated analytics for the dashboard analytics tab.
    Returns stats across all stored jobs.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return {"error": "Supabase not configured"}

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers={**_headers(), "Prefer": ""},
                params={
                    "select": "id,quantum_distance,classical_distance,"
                              "improvement_pct,carbon_kg,quantum_backend,"
                              "num_qubits,created_at,status",
                    "order":  "created_at.desc",
                    "limit":  "50",
                },
            )
            r.raise_for_status()
            jobs = r.json()

        total       = len(jobs)
        completed   = [j for j in jobs if j.get("status") == "complete"]
        avg_improve = (sum(j.get("improvement_pct", 0) for j in completed)
                       / max(len(completed), 1))
        total_co2   = sum(j.get("carbon_kg", 0) for j in completed)
        ibm_count   = sum(1 for j in completed
                          if j.get("quantum_backend") == "ibm_quantum")

        return {
            "total_jobs":          total,
            "completed_jobs":      len(completed),
            "avg_improvement_pct": round(avg_improve, 1),
            "total_co2_kg":        round(total_co2, 1),
            "ibm_quantum_jobs":    ibm_count,
            "recent_jobs":         jobs[:10],
        }
    except Exception as e:
        logger.error("Supabase analytics failed: %s", e)
        return {"error": str(e)}


def get_job_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent job history for the dashboard history tab."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return []
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers={**_headers(), "Prefer": ""},
                params={"select": "*", "order": "created_at.desc",
                        "limit": str(limit)},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Supabase history failed: %s", e)
        return []
