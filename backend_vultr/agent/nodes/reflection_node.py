# backend_vultr/agent/nodes/reflection_node.py
# ENHANCEMENT 3 — Agent self-reflection loop
# This is the single most important node for winning "Intelligent Reasoning".
#
# After IBM Quantum returns results, this node autonomously decides:
#   - Is the best bitstring a valid TSP permutation?
#   - Is quantum confidence above threshold?
#   - If not → increase QAOA layers (p) and signal graph to retry
#
# LangGraph conditional edge reads state["reflection_action"]:
#   "retry"    → go back to build_circuit node with p+1
#   "accept"   → go forward to parse_result node
#   "fallback" → accept best available (max retries hit)

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from agent.state import AgentState

logger = logging.getLogger(__name__)

MAX_RETRIES         = 2      # max times to increase p before accepting
MIN_CONFIDENCE      = 0.12   # minimum fraction of shots on best bitstring
QAOA_P_INCREMENT    = 1      # add this many layers per retry


def _is_valid_permutation(bitstring: str, n_cities: int) -> bool:
    """Check if bitstring encodes a valid TSP permutation (each city once)."""
    if len(bitstring) < n_cities * n_cities:
        return False
    bits = [int(b) for b in reversed(bitstring)]
    M = [bits[i*n_cities:(i+1)*n_cities] for i in range(n_cities)]
    # Each row and column must sum to exactly 1
    for i in range(n_cities):
        if sum(M[i]) != 1:
            return False
        if sum(M[r][i] for r in range(n_cities)) != 1:
            return False
    return True


def _compute_confidence(counts: Dict[str, int], best_bs: str) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return counts.get(best_bs, 0) / total


def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {"step": step, "label": label, "status": status,
            "message": message, "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat()}


def reflect_on_result_node(state: AgentState) -> AgentState:
    """
    Autonomous quality check on quantum measurement results.
    Sets state["reflection_action"] to control the conditional edge.
    """
    logs: list = list(state.get("step_logs", []))
    logs.append(_log("reflect", "🧠  Agent self-reflection", "running",
                     "Evaluating quantum result quality …"))

    counts:      Dict[str, int] = state.get("raw_counts", {})
    best_bs:     str            = state.get("best_bitstring", "")
    n_cities:    int            = len(state.get("city_names", []))
    current_p:   int            = state.get("qaoa_layers", 1)
    retry_count: int            = state.get("reflection_retries", 0)

    if not counts or not best_bs:
        logs[-1].update({"status": "complete",
                         "message": "No quantum results yet — skipping reflection."})
        return {**state, "reflection_action": "accept", "step_logs": logs}

    valid      = _is_valid_permutation(best_bs, n_cities)
    confidence = _compute_confidence(counts, best_bs)

    issues = []
    if not valid:
        issues.append(f"bitstring not a valid permutation")
    if confidence < MIN_CONFIDENCE:
        issues.append(f"confidence {confidence*100:.1f}% < {MIN_CONFIDENCE*100:.0f}% threshold")

    if not issues:
        # ✅ Result is good — proceed
        detail = (f"Valid permutation ✓  |  Confidence {confidence*100:.1f}% ✓  "
                  f"|  p={current_p}  |  No retry needed.")
        logs[-1].update({"status": "complete",
                         "message": "Result quality acceptable — proceeding to decode.",
                         "detail": detail})
        logger.info("Reflection: ACCEPT (valid=%s conf=%.2f p=%d)", valid, confidence, current_p)
        return {**state, "reflection_action": "accept", "step_logs": logs}

    if retry_count >= MAX_RETRIES:
        # ⚠️ Max retries hit — accept anyway
        detail = f"Issues: {', '.join(issues)}. Max retries ({MAX_RETRIES}) hit — accepting best available."
        logs[-1].update({"status": "complete",
                         "message": f"Max retries reached — accepting result (p={current_p}).",
                         "detail": detail})
        logger.warning("Reflection: FALLBACK after %d retries", retry_count)
        return {**state, "reflection_action": "fallback", "step_logs": logs}

    # 🔁 Retry with higher p
    new_p = current_p + QAOA_P_INCREMENT
    detail = (f"Issues detected: {', '.join(issues)}\n"
              f"Action: increasing QAOA layers {current_p} → {new_p} and retrying.")
    logs[-1].update({"status": "complete",
                     "message": f"Quality insufficient — retrying with p={new_p} (attempt {retry_count+1}/{MAX_RETRIES}).",
                     "detail": detail})
    logger.info("Reflection: RETRY p=%d→%d (attempt %d)", current_p, new_p, retry_count+1)

    return {
        **state,
        "reflection_action":  "retry",
        "qaoa_layers":        new_p,
        "reflection_retries": retry_count + 1,
        "optimal_params":     [],   # reset params so build_circuit reruns COBYLA
        "step_logs":          logs,
    }


def reflection_router(state: AgentState) -> str:
    """
    LangGraph conditional edge function.
    Returns the name of the next node based on reflection_action.
    """
    action = state.get("reflection_action", "accept")
    if action == "retry":
        return "build_circuit"    # go back and rebuild with higher p
    return "parse"                # accept or fallback → decode result
