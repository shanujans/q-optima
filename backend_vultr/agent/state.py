# LangGraph AgentState — the single mutable state object that flows through
# every node in the StateGraph.  All fields are optional at construction;
# nodes populate them progressively.

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """
    Shared state passed between LangGraph nodes.
    Keys are populated step-by-step; downstream nodes read only what they need.
    """

    # -----------------------------------------------------------------------
    # Inputs (set once at graph invocation)
    # -----------------------------------------------------------------------
    job_id: str
    audio_bytes: Optional[bytes]      # Raw bytes of the uploaded audio file
    image_bytes: Optional[bytes]      # Raw bytes of the uploaded image
    image_mime_type: str              # e.g. "image/jpeg", "image/png"

    # -----------------------------------------------------------------------
    # Step 1 — Whisper transcription output
    # -----------------------------------------------------------------------
    transcribed_text: str             # Natural-language instruction from user audio

    # -----------------------------------------------------------------------
    # Step 2 — Gemini vision analysis output
    # -----------------------------------------------------------------------
    problem_type: str                 # "tsp" | "portfolio" | "scheduling"
    problem_description: str          # Gemini's prose summary of the problem
    city_names: List[str]             # Extracted location / asset names
    distance_matrix: List[List[float]]  # n×n symmetric distance matrix

    # -----------------------------------------------------------------------
    # Step 3 — QUBO construction (done in Python, not by the LLM)
    # -----------------------------------------------------------------------
    qubo_matrix: List[List[float]]    # n²×n² upper-triangular QUBO matrix Q
    num_variables: int                # Total binary decision variables
    penalty_coefficient: float        # A >> max(distances) to enforce constraints

    # -----------------------------------------------------------------------
    # Step 4 — Qiskit circuit generation
    # -----------------------------------------------------------------------
    circuit_code_display: str         # Human-readable Qiskit code string for UI
    num_qubits: int                   # == num_variables
    circuit_depth: int                # Depth of the transpiled QAOA circuit
    qaoa_layers: int                  # p (number of QAOA repetitions)
    optimal_params: List[float]       # γ, β parameters after classical optimisation

    # -----------------------------------------------------------------------
    # Step 5 — IBM Quantum / Aer execution
    # -----------------------------------------------------------------------
    quantum_backend: str              # "ibm_quantum" | "aer_simulator"
    raw_counts: Dict[str, int]        # {bitstring: shot_count}
    best_bitstring: str               # Lowest-QUBO-energy measurement outcome
    total_shots: int

    # -----------------------------------------------------------------------
    # Step 6 — Result parsing
    # -----------------------------------------------------------------------
    optimal_route: List[str]          # City names in visit order
    route_distance: float
    human_readable_result: str        # Plain-English enterprise decision
    top_solutions: List[Dict[str, Any]]  # Top 3 measurement outcomes

    # -----------------------------------------------------------------------
    # Agent lifecycle tracking
    # -----------------------------------------------------------------------
    current_step: str
    step_logs: List[Dict[str, Any]]   # List[StepLog.model_dump()]
    error_message: Optional[str]      # Set on any failure; subsequent nodes skip
