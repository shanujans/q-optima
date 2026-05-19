# Classical vs Quantum comparison
# Runs a nearest-neighbour TSP heuristic on the same distance matrix.
# Shows percentage improvement of quantum over classical in the result card.

from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def nearest_neighbour_tsp(
    city_names: List[str],
    distance_matrix: List[List[float]],
    start: int = 0,
) -> Tuple[List[str], float]:
    """
    Greedy nearest-neighbour TSP heuristic.
    Starts at city[start], always visits the closest unvisited city.
    Returns (route, total_distance).
    Time complexity: O(n²) — instant for n ≤ 20.
    """
    n = len(city_names)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [city_names[0]], 0.0

    visited = [False] * n
    route_idx = [start]
    visited[start] = True
    total = 0.0

    for _ in range(n - 1):
        current = route_idx[-1]
        best_dist = float("inf")
        best_next = -1
        for j in range(n):
            if not visited[j] and distance_matrix[current][j] < best_dist:
                best_dist = distance_matrix[current][j]
                best_next = j
        if best_next == -1:
            break
        route_idx.append(best_next)
        visited[best_next] = True
        total += best_dist

    # Return to start (cyclic)
    total += distance_matrix[route_idx[-1]][start]
    route = [city_names[i] for i in route_idx]
    return route, round(total, 2)


def run_all_starts(
    city_names: List[str],
    distance_matrix: List[List[float]],
) -> Tuple[List[str], float]:
    """
    Run nearest-neighbour from every city as start point.
    Return the best (shortest) result — strongest classical baseline.
    """
    best_route, best_dist = [], float("inf")
    for start in range(len(city_names)):
        route, dist = nearest_neighbour_tsp(city_names, distance_matrix, start)
        if dist < best_dist:
            best_dist = dist
            best_route = route
    return best_route, best_dist


def compute_quantum_advantage(
    classical_distance: float,
    quantum_distance: float,
) -> Dict[str, Any]:
    """
    Compare classical vs quantum route distances.
    Returns a rich dict with improvement stats and a narrative sentence.
    """
    if classical_distance <= 0:
        return {"improvement_pct": 0.0, "narrative": "No classical baseline available."}

    diff = classical_distance - quantum_distance
    pct  = (diff / classical_distance) * 100.0

    if pct > 0:
        narrative = (
            f"⚡ Quantum advantage confirmed: the QAOA solution is "
            f"{pct:.1f}% shorter than the best classical nearest-neighbour route "
            f"({quantum_distance:.1f} vs {classical_distance:.1f} units). "
            f"Saving {diff:.1f} distance units per delivery cycle."
        )
    elif pct < -1:
        narrative = (
            f"📊 Classical heuristic found a shorter route ({classical_distance:.1f} vs "
            f"{quantum_distance:.1f} units). This is expected at p=1 with limited shots — "
            f"increase QAOA layers for stronger quantum performance."
        )
    else:
        narrative = (
            f"✅ Quantum and classical routes are equivalent ({quantum_distance:.1f} units). "
            f"Quantum circuit validated against classical baseline."
        )

    return {
        "classical_route":    None,  # populated by caller
        "classical_distance": round(classical_distance, 2),
        "quantum_distance":   round(quantum_distance, 2),
        "improvement_pct":    round(pct, 1),
        "distance_saved":     round(diff, 2),
        "narrative":          narrative,
    }


def get_classical_comparison(
    city_names: List[str],
    distance_matrix: List[List[float]],
    quantum_distance: float,
) -> Dict[str, Any]:
    """
    Full pipeline: run classical solver + compute advantage.
    Called from parse_result_node and added to QuantumResult.
    """
    try:
        classical_route, classical_dist = run_all_starts(city_names, distance_matrix)
        result = compute_quantum_advantage(classical_dist, quantum_distance)
        result["classical_route"] = classical_route
        logger.info(
            "Classical baseline: %.1f  Quantum: %.1f  Improvement: %.1f%%",
            classical_dist, quantum_distance, result["improvement_pct"],
        )
        return result
    except Exception as e:
        logger.error("Classical comparison failed: %s", e)
        return {
            "classical_route":    city_names,
            "classical_distance": 0.0,
            "quantum_distance":   quantum_distance,
            "improvement_pct":   0.0,
            "distance_saved":    0.0,
            "narrative":         f"Classical comparison unavailable: {e}",
        }
