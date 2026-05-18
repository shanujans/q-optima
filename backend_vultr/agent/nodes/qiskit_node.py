# backend/agent/nodes/qiskit_node.py
# LangGraph node — Steps 3 & 4: QUBO construction + Qiskit QAOA circuit
#
# This node:
#   1. Calls build_tsp_qubo() to produce the upper-triangular QUBO matrix Q.
#   2. Converts Q to a SparsePauliOp Ising Hamiltonian.
#   3. Builds a QAOAAnsatz circuit and runs classical COBYLA optimisation
#      using the local Aer simulator as the cost-function evaluator.
#   4. Stores the optimal γ/β parameters and a display-ready Qiskit code
#      string into state for the IBM execution node and the UI timeline.
#
# Qubit budget
# ------------
# n cities → n² qubits.  For n=3 → 9 qubits (runs on real IBM hardware).
# For n=4 → 16 qubits (uses Aer; IBM free tier has queue constraints).
# For n≥5 → always uses Aer; IBM free tier devices top out at ~127 qubits
# but queue wait times are prohibitive for a live demo.

from __future__ import annotations

import logging
import textwrap
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator
from qiskit import transpile

from agent.state import AgentState
from utils.qubo_parser import build_tsp_qubo, evaluate_qubo

logger = logging.getLogger(__name__)

# QAOA hyperparameters — tunable via env vars if desired
QAOA_LAYERS  = 1         # p=1 sufficient for small TSP; increase for better quality
COBYLA_ITER  = 150       # Max classical optimisation iterations
SHOTS_OPTIM  = 1024      # Shots during optimisation (fast)
SHOTS_FINAL  = 4096      # Shots for the final optimal-parameter sampling


# ---------------------------------------------------------------------------
# QUBO → Ising Hamiltonian conversion
# ---------------------------------------------------------------------------

def qubo_to_ising(Q: np.ndarray) -> Tuple[SparsePauliOp, float]:
    """
    Map an upper-triangular QUBO matrix Q to a SparsePauliOp Ising Hamiltonian.

    Substitution: x_i = (1 - Z_i) / 2
    Results in:
        Q_ii · x_i   →   -Q_ii/2 · Z_i  + Q_ii/2  (constant)
        Q_ij · x_i x_j →  Q_ij/4 · (1 - Z_i - Z_j + Z_i Z_j)   (i < j)
    """
    n = Q.shape[0]
    pauli_terms: List[Tuple[str, complex]] = []
    offset = 0.0

    def _z(qubit: int) -> str:
        """Pauli string with Z on `qubit` (Qiskit: qubit 0 = rightmost char)."""
        s = ["I"] * n
        s[n - 1 - qubit] = "Z"
        return "".join(s)

    def _zz(qi: int, qj: int) -> str:
        s = ["I"] * n
        s[n - 1 - qi] = "Z"
        s[n - 1 - qj] = "Z"
        return "".join(s)

    for i in range(n):
        qii = Q[i, i]
        if abs(qii) > 1e-10:
            offset += qii / 2.0
            pauli_terms.append((_z(i), -qii / 2.0))

        for j in range(i + 1, n):
            qij = Q[i, j]
            if abs(qij) > 1e-10:
                offset += qij / 4.0
                pauli_terms.append((_z(i),    -qij / 4.0))
                pauli_terms.append((_z(j),    -qij / 4.0))
                pauli_terms.append((_zz(i,j),  qij / 4.0))

    if not pauli_terms:
        pauli_terms = [("I" * n, 0.0)]

    hamiltonian = SparsePauliOp.from_list(pauli_terms).simplify()
    return hamiltonian, offset


# ---------------------------------------------------------------------------
# Circuit display string generator (for the UI timeline)
# ---------------------------------------------------------------------------

def _make_display_code(n_cities: int, n_qubits: int, p: int, city_names: List[str]) -> str:
    """Generate a human-readable Qiskit snippet shown in the UI timeline."""
    cities_str = ", ".join(f'"{c}"' for c in city_names)
    return textwrap.dedent(f"""
        # Q-Optima — Auto-generated Qiskit QAOA circuit
        # Problem: TSP with {n_cities} cities ({n_qubits} qubits, p={p})
        # Cities: [{cities_str}]

        from qiskit.circuit.library import QAOAAnsatz
        from qiskit.quantum_info import SparsePauliOp
        from qiskit_aer import AerSimulator
        from qiskit import transpile

        # Ising Hamiltonian built from QUBO matrix Q ({n_qubits}×{n_qubits})
        hamiltonian = SparsePauliOp.from_list(ising_pauli_terms)

        # QAOA ansatz with p={p} layers
        ansatz = QAOAAnsatz(cost_operator=hamiltonian, reps={p})
        ansatz.measure_all()

        # Bind optimised γ/β parameters from COBYLA
        bound = ansatz.assign_parameters(optimal_params)

        # Execute on backend
        simulator = AerSimulator()
        transpiled = transpile(bound, simulator, optimization_level=3)
        job    = simulator.run(transpiled, shots={SHOTS_FINAL})
        counts = job.result().get_counts()
        # → decode best bitstring → optimal route
    """).strip()


# ---------------------------------------------------------------------------
# QAOA cost function (evaluated on Aer for the classical optimisation loop)
# ---------------------------------------------------------------------------

def _make_cost_fn(ansatz: QAOAAnsatz, Q: np.ndarray, simulator: AerSimulator):
    """
    Returns a callable f(params) → float that COBYLA can minimise.
    Evaluates the QUBO expectation value using shot-based sampling.
    """
    n_vars = Q.shape[0]

    def cost(params: np.ndarray) -> float:
        bound = ansatz.assign_parameters(params)
        bound.measure_all()
        transpiled = transpile(bound, simulator, optimization_level=1)
        job    = simulator.run(transpiled, shots=SHOTS_OPTIM)
        counts: Dict[str, int] = job.result().get_counts()

        expectation = 0.0
        total = sum(counts.values())
        for bitstring, count in counts.items():
            e = evaluate_qubo(Q, bitstring)
            expectation += count * e / total
        return expectation

    return cost


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

def build_qubo_and_circuit_node(state: AgentState) -> AgentState:
    """
    Reads city_names + distance_matrix from state.
    Builds QUBO → Ising Hamiltonian → QAOA ansatz → classical optimisation.
    Writes optimal_params, circuit metadata, and display code into state.
    """
    if state.get("error_message"):
        return state

    logs: list = list(state.get("step_logs", []))

    city_names: List[str]          = state.get("city_names", [])
    distance_matrix: List[List[float]] = state.get("distance_matrix", [])
    n_cities = len(city_names)

    # --- Step 3: Build QUBO ---
    logs.append({
        "step": "build_qubo", "label": "🧮  QUBO formulation", "status": "running",
        "message": f"Building {n_cities}²={n_cities**2}-variable QUBO matrix …",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        Q, penalty = build_tsp_qubo(city_names, distance_matrix)
        n_vars = n_cities * n_cities
        logs[-1].update({
            "status":  "complete",
            "message": f"QUBO built: {n_vars}×{n_vars} matrix, penalty A={penalty:.1f}",
            "detail":  f"Non-zero entries: {int(np.count_nonzero(Q))}",
        })
    except Exception as exc:
        msg = f"QUBO construction failed: {exc}"
        logger.exception(msg)
        logs[-1].update({"status": "error", "message": msg})
        return {**state, "error_message": msg, "current_step": "error", "step_logs": logs}

    # --- Step 4: Build QAOA ansatz and optimise ---
    p = QAOA_LAYERS
    n_qubits = n_vars

    logs.append({
        "step": "build_circuit", "label": "⚛️  Qiskit QAOA circuit", "status": "running",
        "message": f"Building QAOA ansatz ({n_qubits} qubits, p={p}) and running COBYLA …",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        hamiltonian, _offset = qubo_to_ising(Q)

        ansatz = QAOAAnsatz(cost_operator=hamiltonian, reps=p)
        # Number of parameters: 2*p (p gammas + p betas)
        n_params = 2 * p

        simulator = AerSimulator()
        cost_fn   = _make_cost_fn(ansatz, Q, simulator)

        # Multi-start: run COBYLA from 3 random initialisations, keep best
        best_result = None
        best_val    = float("inf")
        rng = np.random.default_rng(seed=42)

        for trial in range(3):
            x0 = rng.uniform(0, 2 * np.pi, n_params)
            result = minimize(
                cost_fn, x0,
                method="COBYLA",
                options={"maxiter": COBYLA_ITER // 3, "rhobeg": 0.8},
            )
            if result.fun < best_val:
                best_val    = result.fun
                best_result = result

        optimal_params: List[float] = best_result.x.tolist()

        # Measure circuit depth after transpilation (informational)
        bound = ansatz.assign_parameters(best_result.x)
        bound.measure_all()
        transpiled_for_depth = transpile(bound, simulator, optimization_level=3)
        depth = transpiled_for_depth.depth()

        display_code = _make_display_code(n_cities, n_qubits, p, city_names)

        logs[-1].update({
            "status":  "complete",
            "message": (
                f"QAOA optimised in {best_result.nfev} function evals. "
                f"Circuit depth: {depth}. Final cost: {best_val:.3f}"
            ),
            "detail": display_code,
        })
        logger.info(
            "QAOA optimised: qubits=%d p=%d depth=%d cost=%.3f",
            n_qubits, p, depth, best_val,
        )

        return {
            **state,
            "qubo_matrix":          Q.tolist(),
            "num_variables":        n_vars,
            "penalty_coefficient":  float(penalty),
            "circuit_code_display": display_code,
            "num_qubits":           n_qubits,
            "circuit_depth":        depth,
            "qaoa_layers":          p,
            "optimal_params":       optimal_params,
            "current_step":         "circuit_built",
            "step_logs":            logs,
        }

    except Exception as exc:
        msg = f"QAOA circuit build / optimisation failed: {exc}"
        logger.exception(msg)
        logs[-1].update({"status": "error", "message": msg})
        return {**state, "error_message": msg, "current_step": "error", "step_logs": logs}
