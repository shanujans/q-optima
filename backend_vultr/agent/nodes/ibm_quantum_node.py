# Execution strategy (automatic):
#   1. If IBM_QUANTUM_TOKEN is set AND n_qubits ≤ IBM_MAX_QUBITS (default 20):
#      Submit to the least-busy real IBM Quantum backend.
#   2. Otherwise: run on local Aer simulator (instant, deterministic).
#
# The two-node split (execute / parse) keeps each node single-responsibility
# and makes the LangGraph timeline cleaner.

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from qiskit import transpile
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator

from agent.state import AgentState
from agent.nodes.qiskit_node import qubo_to_ising   # reuse the conversion
from utils.qubo_parser import build_tsp_qubo, parse_quantum_results

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IBM_QUANTUM_TOKEN = os.getenv("IBM_QUANTUM_TOKEN", "")
IBM_MAX_QUBITS    = int(os.getenv("IBM_MAX_QUBITS", "20"))   # Safety ceiling
SHOTS_FINAL       = int(os.getenv("SHOTS_FINAL", "4096"))

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {
        "step": step, "label": label, "status": status,
        "message": message, "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _rebuild_ansatz(state: AgentState) -> QAOAAnsatz:
    """
    Re-builds the QAOAAnsatz from the QUBO stored in state.
    (Qiskit objects are not serialisable into the state dict, so we recreate.)
    """
    Q = np.array(state["qubo_matrix"])
    hamiltonian, _ = qubo_to_ising(Q)
    p = state.get("qaoa_layers", 1)
    return QAOAAnsatz(cost_operator=hamiltonian, reps=p)


# ---------------------------------------------------------------------------
# IBM Quantum execution path
# ---------------------------------------------------------------------------

def _run_on_ibm(
    ansatz: QAOAAnsatz,
    optimal_params: List[float],
    n_qubits: int,
) -> Dict[str, Any]:
    """
    Submit the QAOA circuit to the least-busy IBM Quantum backend.
    Uses the SamplerV2 primitive from qiskit-ibm-runtime.
    """
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    service = QiskitRuntimeService(
        channel="ibm_quantum",
        token=IBM_QUANTUM_TOKEN,
    )
    backend = service.least_busy(
        operational=True,
        simulator=False,
        min_num_qubits=n_qubits,
    )
    logger.info("IBM Quantum backend selected: %s (%d qubits)", backend.name, backend.num_qubits)

    # Transpile circuit for the real device's native gate set
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    bound = ansatz.assign_parameters(optimal_params)
    bound.measure_all()
    isa_circuit = pm.run(bound)

    sampler = Sampler(mode=backend)
    job     = sampler.run([(isa_circuit,)], shots=SHOTS_FINAL)
    result  = job.result()

    # SamplerV2 result accessor
    counts: Dict[str, int] = result[0].data.meas.get_counts()
    return {
        "counts":          counts,
        "backend_name":    backend.name,
        "backend_type":    "ibm_quantum",
    }


# ---------------------------------------------------------------------------
# Aer simulation execution path
# ---------------------------------------------------------------------------

def _run_on_aer(
    ansatz: QAOAAnsatz,
    optimal_params: List[float],
) -> Dict[str, Any]:
    """Execute the bound QAOA circuit on the local Aer simulator."""
    simulator = AerSimulator()
    bound = ansatz.assign_parameters(optimal_params)
    bound.measure_all()
    transpiled = transpile(bound, simulator, optimization_level=3)

    job    = simulator.run(transpiled, shots=SHOTS_FINAL)
    counts = job.result().get_counts()
    return {
        "counts":       counts,
        "backend_name": "AerSimulator",
        "backend_type": "aer_simulator",
    }


# ---------------------------------------------------------------------------
# LangGraph node — Step 5: Execute quantum circuit
# ---------------------------------------------------------------------------

def execute_quantum_node(state: AgentState) -> AgentState:
    """
    Binds the optimal parameters to the QAOA ansatz and executes it on
    either IBM Quantum or Aer, depending on config + qubit count.
    """
    if state.get("error_message"):
        return state

    logs: list = list(state.get("step_logs", []))
    n_qubits: int       = state.get("num_qubits", 0)
    optimal_params      = state.get("optimal_params", [])

    use_ibm = (
        bool(IBM_QUANTUM_TOKEN)
        and n_qubits <= IBM_MAX_QUBITS
    )
    backend_label = "IBM Quantum (real device)" if use_ibm else "Aer Simulator (local)"
    logs.append(_log(
        "execute_quantum", f"🌐  {backend_label}", "running",
        f"Executing QAOA circuit ({n_qubits} qubits, {SHOTS_FINAL} shots) …",
        f"Backend: {backend_label}",
    ))

    try:
        ansatz = _rebuild_ansatz(state)

        if use_ibm:
            exec_result = _run_on_ibm(ansatz, optimal_params, n_qubits)
        else:
            exec_result = _run_on_aer(ansatz, optimal_params)

        counts: Dict[str, int] = exec_result["counts"]
        total_shots = sum(counts.values())

        # Find the most frequent bitstring (modal answer)
        modal_bs = max(counts, key=counts.__getitem__)

        logs[-1].update({
            "status":  "complete",
            "message": (
                f"{total_shots} shots collected. "
                f"Most frequent: |{modal_bs}⟩ "
                f"({counts[modal_bs] / total_shots * 100:.1f}%)"
            ),
            "detail": f"Backend: {exec_result['backend_name']}  Unique outcomes: {len(counts)}",
        })
        logger.info(
            "Quantum execution complete: backend=%s shots=%d unique=%d",
            exec_result["backend_name"], total_shots, len(counts),
        )

        return {
            **state,
            "quantum_backend": exec_result["backend_type"],
            "raw_counts":      counts,
            "total_shots":     total_shots,
            "current_step":    "executed",
            "step_logs":       logs,
        }

    except Exception as exc:
        msg = f"Quantum execution failed: {exc}"
        logger.exception(msg)
        logs[-1].update({"status": "error", "message": msg})
        return {**state, "error_message": msg, "current_step": "error", "step_logs": logs}


# ---------------------------------------------------------------------------
# LangGraph node — Step 6: Parse quantum result → human-readable decision
# ---------------------------------------------------------------------------

def parse_result_node(state: AgentState) -> AgentState:
    """
    Reads raw_counts + QUBO + city metadata from state.
    Decodes the best bitstring into an ordered route and generates the
    plain-English enterprise decision text.
    """
    if state.get("error_message"):
        return state

    logs: list = list(state.get("step_logs", []))
    logs.append(_log(
        "parse_result", "📊  Decoding quantum result", "running",
        "Mapping measurement bitstrings → optimal route …",
    ))

    try:
        Q             = np.array(state["qubo_matrix"])
        counts        = state.get("raw_counts", {})
        city_names    = state.get("city_names", [])
        dist_matrix   = state.get("distance_matrix", [])
        problem_desc  = state.get("problem_description", "")

        parsed = parse_quantum_results(
            counts=counts,
            Q=Q,
            city_names=city_names,
            distance_matrix=dist_matrix,
            top_k=3,
        )

        logs[-1].update({
            "status":  "complete",
            "message": (
                f"Optimal route: "
                + " → ".join(parsed["optimal_route"])
                + f"  |  Distance: {parsed['route_distance']:.1f}"
            ),
            "detail": parsed["human_readable_result"],
        })
        logger.info(
            "Result parsed: route=%s dist=%.1f",
            parsed["optimal_route"], parsed["route_distance"],
        )

        return {
            **state,
            **parsed,       # best_bitstring, optimal_route, route_distance, human_readable_result, top_solutions
            "current_step": "complete",
            "step_logs":    logs,
        }

    except Exception as exc:
        msg = f"Result parsing failed: {exc}"
        logger.exception(msg)
        logs[-1].update({"status": "error", "message": msg})
        return {**state, "error_message": msg, "current_step": "error", "step_logs": logs}
