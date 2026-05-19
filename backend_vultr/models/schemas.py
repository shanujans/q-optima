# Pydantic v2 request / response models for Q-Optima API.
# All data crossing the HTTP boundary is validated here.

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETE  = "complete"
    ERROR     = "error"


class StepStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    COMPLETE = "complete"
    SKIPPED  = "skipped"
    ERROR    = "error"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class StepLog(BaseModel):
    """A single entry in the agent's reasoning timeline."""
    step: str
    label: str                          # Human-friendly step name for the UI
    status: StepStatus
    message: str
    detail: Optional[str] = None        # Extra context (e.g. transcribed text)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SolutionCandidate(BaseModel):
    """One of the top quantum measurement outcomes."""
    bitstring: str
    route: List[str]                    # City names in visit order
    distance: float
    probability: float                  # Relative frequency in shot counts


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------

class SolveResponse(BaseModel):
    """Returned immediately after POST /api/solve."""
    job_id: str
    message: str = "Job accepted. Poll /api/status/{job_id} for live updates."


class QuantumResult(BaseModel):
    """The final structured result embedded in StatusResponse."""
    problem_description: str
    problem_type: str                   # "tsp" | "portfolio" | "scheduling"
    city_names: List[str]

    # Quantum execution metadata
    quantum_backend: str                # "ibm_quantum" | "aer_simulator"
    num_qubits: int
    circuit_depth: int
    qaoa_layers: int                    # p value used
    total_shots: int

    # Solution
    best_bitstring: str
    optimal_route: List[str]
    route_distance: float
    human_readable_result: str          # Plain-English enterprise decision
    top_solutions: List[SolutionCandidate] = []

    # Raw Qiskit circuit code (for the UI timeline display)
    circuit_code_display: str = ""


class StatusResponse(BaseModel):
    """Full job status — polled by the frontend every 1.5 s."""
    job_id: str
    status: JobStatus
    current_step: str
    progress_percent: int = Field(ge=0, le=100)
    step_logs: List[StepLog] = []
    result: Optional[QuantumResult] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal job store entry (not serialised to clients directly)
# ---------------------------------------------------------------------------

class JobRecord(BaseModel):
    """Stored in the in-memory job registry on the FastAPI server."""
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    current_step: str = "queued"
    progress_percent: int = 0
    step_logs: List[StepLog] = []
    result: Optional[QuantumResult] = None
    error_message: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    model_config = {"arbitrary_types_allowed": True}
