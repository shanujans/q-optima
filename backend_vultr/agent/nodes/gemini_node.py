from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import google.generativeai as genai
from PIL import Image
import io

from agent.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialisation
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

genai.configure(api_key=GEMINI_API_KEY)
_gemini_model = genai.GenerativeModel(GEMINI_MODEL)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a mathematical optimization expert embedded in an enterprise AI agent.
Your task is to analyze the provided image (which may be a logistics map, delivery route diagram, 
city graph, or abstract network) and extract a structured optimization problem.

User instruction: {instruction}

Return a single JSON object with EXACTLY this schema — no markdown, no explanation, just JSON:

{{
    "problem_type": "tsp",
    "problem_description": "One sentence describing the optimization problem found in the image.",
    "cities": ["Name1", "Name2", "Name3"],
    "distance_matrix": [
        [0, 12, 25],
        [12, 0, 18],
        [25, 18, 0]
    ],
    "num_cities": 3
}}

Rules:
- "problem_type" must be "tsp" (Traveling Salesman Problem) for route optimization.
- "cities" must be short alphanumeric strings (max 15 chars each). Use labels visible in the image; 
  if unlabelled, name them "Node_A", "Node_B", etc.
- "distance_matrix" must be symmetric (dist[i][j] == dist[j][i]) with zeros on the diagonal.
  If distances are not visible, estimate them from relative visual positions (any unit is fine).
- Include between 2 and 6 cities. If the image shows more, select the most prominent ones.
- Output ONLY valid JSON. Do not include any text before or after the JSON object.
"""

# Fallback demo data used when no image is uploaded
_DEMO_DATA = {
    "problem_type":        "tsp",
    "problem_description": "Demo: find the shortest delivery route among 4 warehouse hubs.",
    "cities":              ["Warehouse_A", "Depot_B", "Hub_C", "Port_D"],
    "distance_matrix": [
        [0,  12, 25, 18],
        [12,  0, 14, 22],
        [25, 14,  0, 16],
        [18, 22, 16,  0],
    ],
    "num_cities": 4,
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {
        "step":      step,
        "label":     label,
        "status":    status,
        "message":   message,
        "detail":    detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_json(raw: str) -> Dict[str, Any]:
    """Strip markdown fences and parse the first JSON object found."""
    # Remove ```json ... ``` fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Find the outermost {...}
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in Gemini response.")
    return json.loads(raw[start:end])


def _validate_and_fix(data: Dict[str, Any]) -> Dict[str, Any]:
    """Light validation + auto-correction of Gemini's output."""
    cities: List[str] = data.get("cities", [])
    matrix: List[List[float]] = data.get("distance_matrix", [])
    n = len(cities)

    if n < 2:
        raise ValueError(f"Need at least 2 cities, got {n}.")
    if n > 3:
        logger.warning("Capping at 3 cities for performance.")
        cities = cities[:3]
        n = 3
        matrix = [row[:3] for row in matrix[:3]]

    # Ensure symmetry and zero diagonal
    m = [[float(matrix[i][j]) for j in range(n)] for i in range(n)]
    for i in range(n):
        m[i][i] = 0.0
        for j in range(i + 1, n):
            avg = (m[i][j] + m[j][i]) / 2.0
            m[i][j] = avg
            m[j][i] = avg

    # Ensure no negative distances
    for i in range(n):
        for j in range(n):
            if m[i][j] < 0:
                m[i][j] = abs(m[i][j])

    data["cities"]          = cities
    data["distance_matrix"] = m
    data["num_cities"]      = n
    return data


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

def analyze_with_gemini_node(state: AgentState) -> AgentState:
    """
    Sends the image + transcribed instruction to Gemini 1.5 Pro Vision.
    Parses the structured JSON response and writes city_names / distance_matrix
    into state so the QUBO builder can proceed.
    """
    # Skip if a previous node errored
    if state.get("error_message"):
        return state

    logs: list = list(state.get("step_logs", []))
    logs.append(_log(
        "analyze", "🔭  Gemini vision analysis", "running",
        f"Sending image to {GEMINI_MODEL} for problem formulation …",
    ))

    image_bytes: bytes | None = state.get("image_bytes")
    instruction: str = state.get("transcribed_text", "Find the optimal route.")

    # --- No-image fallback (demo mode) ---
    if not image_bytes or not GEMINI_API_KEY:
        reason = "no image" if not image_bytes else "no GEMINI_API_KEY"
        logger.warning("Gemini node: using demo data (%s).", reason)
        data = _DEMO_DATA.copy()
        logs[-1].update({
            "status":  "complete",
            "message": f"Demo mode ({reason}) — using synthetic 4-city dataset.",
            "detail":  json.dumps(data, indent=2),
        })
        return {
            **state,
            "problem_type":        data["problem_type"],
            "problem_description": data["problem_description"],
            "city_names":          data["cities"],
            "distance_matrix":     data["distance_matrix"],
            "current_step":        "analyzed",
            "step_logs":           logs,
        }

    # --- Gemini API call ---
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        prompt = _SYSTEM_PROMPT.format(instruction=instruction)

        response = _gemini_model.generate_content(
            [prompt, image],
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,      # Deterministic for math extraction
                max_output_tokens=512,
            ),
        )

        raw_text = response.text
        logger.debug("Gemini raw response: %s", raw_text[:400])

        data = _extract_json(raw_text)
        data = _validate_and_fix(data)

        logs[-1].update({
            "status":  "complete",
            "message": (
                f"Extracted {data['num_cities']} cities: "
                + ", ".join(data["cities"])
            ),
            "detail": json.dumps({
                "problem_type": data["problem_type"],
                "cities":       data["cities"],
            }),
        })
        logger.info(
            "Gemini extracted %d cities: %s",
            data["num_cities"], data["cities"],
        )

        return {
            **state,
            "problem_type":        data["problem_type"],
            "problem_description": data["problem_description"],
            "city_names":          data["cities"],
            "distance_matrix":     data["distance_matrix"],
            "current_step":        "analyzed",
            "step_logs":           logs,
        }

    except Exception as exc:
        msg = f"Gemini analysis failed: {exc}"
        logger.exception(msg)
        logs[-1].update({"status": "error", "message": msg})
        return {
            **state,
            "error_message": msg,
            "current_step":  "error",
            "step_logs":     logs,
        }
