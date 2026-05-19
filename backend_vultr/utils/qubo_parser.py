# Two responsibilities:
#   1. build_tsp_qubo()  — converts a distance matrix into an upper-triangular
#      QUBO matrix suitable for QAOA / VQE.
#   2. parse_bitstring() — decodes a quantum measurement bitstring back into a
#      human-readable route and computes the total distance.

from __future__ import annotations

import itertools
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QUBO builder
# ---------------------------------------------------------------------------

def build_tsp_qubo(
    city_names: List[str],
    distance_matrix: List[List[float]],
) -> Tuple[np.ndarray, float]:
    """
    Build an upper-triangular QUBO matrix for the Travelling Salesman Problem.

    Parameters
    ----------
    city_names      : list of n city name strings
    distance_matrix : n×n symmetric distance matrix (floats)

    Returns
    -------
    Q               : np.ndarray of shape (n², n²)  — upper-triangular QUBO
    penalty         : float  — the penalty coefficient A that was used

    Variable encoding
    -----------------
    x[city * n + pos] == 1  ⟺  city is visited at position pos
    """
    n = len(city_names)
    dist = np.array(distance_matrix, dtype=float)

    if dist.shape != (n, n):
        raise ValueError(
            f"distance_matrix must be {n}×{n} but got {dist.shape}"
        )

    # Ensure matrix is symmetric (Gemini occasionally returns slightly asymmetric)
    dist = (dist + dist.T) / 2.0
    np.fill_diagonal(dist, 0.0)

    # Penalty must dominate any feasible-route difference
    max_dist = float(dist.max()) if dist.max() > 0 else 1.0
    A = float(n) * max_dist * 10.0   # 10× safety factor

    size = n * n                      # Total binary variables
    Q = np.zeros((size, size), dtype=float)

    def var(city: int, pos: int) -> int:
        return city * n + pos

    # --- Constraint A: each city visited exactly once ---
    # A · (1 - Σ_pos x_{c,pos})²
    # Diagonal term  : -A  per variable
    # Off-diagonal   : +2A per pair (same city, different positions) — upper triangle only
    for city in range(n):
        for pos in range(n):
            v = var(city, pos)
            Q[v, v] -= A
            for pos2 in range(pos + 1, n):
                v2 = var(city, pos2)
                Q[v, v2] += 2.0 * A

    # --- Constraint B: each position filled by exactly one city ---
    # A · (1 - Σ_city x_{city,p})²
    for pos in range(n):
        for city in range(n):
            v = var(city, pos)
            Q[v, v] -= A
            for city2 in range(city + 1, n):
                v2 = var(city2, pos)
                Q[v, v2] += 2.0 * A

    # --- Objective: minimise total cyclic route distance ---
    for pos in range(n):
        next_pos = (pos + 1) % n
        for city_i in range(n):
            for city_j in range(n):
                if city_i == city_j:
                    continue
                vi = var(city_i, pos)
                vj = var(city_j, next_pos)
                # Keep upper-triangular
                lo, hi = (vi, vj) if vi <= vj else (vj, vi)
                Q[lo, hi] += dist[city_i, city_j]

    logger.info(
        "QUBO built: %d cities → %d variables, penalty=%.1f",
        n, size, A,
    )
    return Q, A


# ---------------------------------------------------------------------------
# Bitstring evaluator
# ---------------------------------------------------------------------------

def evaluate_qubo(Q: np.ndarray, bitstring: str) -> float:
    """
    Compute x^T Q x for an upper-triangular Q and a binary bitstring.
    Qiskit measures qubits in little-endian order (qubit 0 = rightmost char).
    """
    n_vars = Q.shape[0]
    # Reverse so index 0 → qubit 0
    x = np.array([int(b) for b in reversed(bitstring)], dtype=float)
    if len(x) != n_vars:
        # Pad or truncate silently (shouldn't happen if circuit is built correctly)
        if len(x) < n_vars:
            x = np.pad(x, (0, n_vars - len(x)))
        else:
            x = x[:n_vars]
    return float(x @ Q @ x)


# ---------------------------------------------------------------------------
# Result decoder
# ---------------------------------------------------------------------------

def bitstring_to_route(
    bitstring: str,
    city_names: List[str],
) -> Tuple[List[str], bool]:
    """
    Decode a measurement bitstring into a TSP route.

    Returns
    -------
    route    : list of city names in visit order (length n), may repeat
               cities if the bitstring encodes an invalid permutation
    is_valid : True if the bitstring encodes a genuine permutation
    """
    n = len(city_names)
    # Reverse for Qiskit little-endian
    bits = [int(b) for b in reversed(bitstring)]
    if len(bits) < n * n:
        bits.extend([0] * (n * n - len(bits)))

    # Reshape into n×n assignment matrix  M[city][pos]
    M = np.array(bits[: n * n], dtype=int).reshape(n, n)

    route: List[str] = []
    is_valid = True

    for pos in range(n):
        col = M[:, pos]
        ones = np.where(col == 1)[0]
        if len(ones) == 1:
            route.append(city_names[ones[0]])
        else:
            # Invalid: either no city or multiple cities at this position
            is_valid = False
            if len(ones) > 1:
                route.append(city_names[ones[0]])   # take first
            else:
                route.append(f"?pos{pos}")

    # Also check each city appears exactly once
    if len(set(route)) != n:
        is_valid = False

    return route, is_valid


def compute_route_distance(
    route: List[str],
    city_names: List[str],
    distance_matrix: List[List[float]],
) -> float:
    """
    Compute the cyclic distance for a given city visit order.
    Returns infinity if any city in route is unrecognised.
    """
    idx = {name: i for i, name in enumerate(city_names)}
    dist = np.array(distance_matrix, dtype=float)
    total = 0.0
    n = len(route)
    for step in range(n):
        c_from = route[step]
        c_to   = route[(step + 1) % n]
        if c_from not in idx or c_to not in idx:
            return float("inf")
        total += dist[idx[c_from], idx[c_to]]
    return float(total)


def parse_quantum_results(
    counts: Dict[str, int],
    Q: np.ndarray,
    city_names: List[str],
    distance_matrix: List[List[float]],
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    Given the raw shot counts from the quantum backend, find the best
    (lowest QUBO energy) bitstring and decode it into a route.

    Returns a dict ready to be spread into AgentState.
    """
    total_shots = sum(counts.values())

    # Rank bitstrings by QUBO energy (ascending)
    ranked = sorted(
        counts.items(),
        key=lambda kv: evaluate_qubo(Q, kv[0]),
    )

    best_bitstring, _ = ranked[0]
    best_route, best_valid = bitstring_to_route(best_bitstring, city_names)
    best_distance = compute_route_distance(best_route, city_names, distance_matrix)

    # If the absolute best is invalid, scan for the first valid one
    if not best_valid:
        for bs, _ in ranked[1:]:
            route, valid = bitstring_to_route(bs, city_names)
            dist_val = compute_route_distance(route, city_names, distance_matrix)
            if valid and dist_val < float("inf"):
                best_bitstring = bs
                best_route = route
                best_distance = dist_val
                best_valid = True
                break

    # Build top-K solution list
    top_solutions: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for bs, shot_count in ranked:
        if bs in seen:
            continue
        seen.add(bs)
        route, valid = bitstring_to_route(bs, city_names)
        d = compute_route_distance(route, city_names, distance_matrix)
        top_solutions.append({
            "bitstring": bs,
            "route": route,
            "distance": d,
            "probability": round(shot_count / total_shots, 4),
            "is_valid": valid,
        })
        if len(top_solutions) >= top_k:
            break

    # Generate human-readable enterprise decision
    route_str = " → ".join(best_route) + f" → {best_route[0]}"  # cyclic
    if best_valid:
        human = (
            f"✅ Optimal route identified: {route_str}\n"
            f"Total distance: {best_distance:.1f} units.\n"
            f"Quantum confidence: {counts.get(best_bitstring, 0) / total_shots * 100:.1f}% of {total_shots} shots "
            f"converged on this solution."
        )
    else:
        human = (
            f"⚠️  Best quantum measurement: {route_str}\n"
            f"Note: the circuit may need more QAOA layers (p) for a stricter "
            f"constraint guarantee. Distance estimate: {best_distance:.1f} units."
        )

    return {
        "best_bitstring":        best_bitstring,
        "optimal_route":         best_route,
        "route_distance":        best_distance,
        "human_readable_result": human,
        "top_solutions":         top_solutions,
    }
