# backend_vultr/agent/graph.py — ENHANCED (all 7 upgrades wired)
from __future__ import annotations
import logging, os
from datetime import datetime, timezone
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.speechmatics_node import transcribe_audio_node
from agent.nodes.gemini_node        import analyze_with_gemini_node
from agent.nodes.qiskit_node        import build_qubo_and_circuit_node
from agent.nodes.ibm_quantum_node   import execute_quantum_node, parse_result_node
from agent.nodes.reflection_node    import reflect_on_result_node, reflection_router
from agent.tools.osrm_tool          import fetch_real_distances_sync
from agent.tools.weather_tool       import fetch_weather_sync
from agent.tools.traffic_tool       import fetch_traffic_sync
from agent.tools.carbon_tool        import fetch_carbon_sync
from agent.tools.telegram_tool      import send_dispatch_alert_sync
from agent.tools.supabase_tool      import save_job
from utils.classical_comparison     import get_classical_comparison

logger = logging.getLogger(__name__)


def _log(step, label, status, message, detail="") -> Dict[str, Any]:
    return {"step":step,"label":label,"status":status,"message":message,
            "detail":detail,"timestamp":datetime.now(timezone.utc).isoformat()}


# ── Enrich node: OSRM + weather + traffic + carbon ────────────────────────────

def enrich_with_context_node(state: AgentState) -> AgentState:
    if state.get("error_message"): return state
    logs = list(state.get("step_logs", []))
    logs.append(_log("enrich","🌐  Context enrichment","running",
                     "OSRM roads · weather · traffic · carbon …"))

    city_names    = state.get("city_names", [])
    gemini_matrix = state.get("distance_matrix", [])
    n = len(city_names)

    try:
        osrm   = fetch_real_distances_sync(city_names, gemini_matrix)
        dm     = osrm["distance_matrix"]
        coords = osrm["city_coords"]

        weather = fetch_weather_sync(city_names, dm)
        traffic = fetch_traffic_sync(city_names, coords, dm,
                                     os.getenv("TOMTOM_API_KEY",""))
        carbon  = fetch_carbon_sync(city_names, dm,
                                    os.getenv("CLIMATIQ_API_KEY",""))

        enriched = [[dm[i][j]+weather["penalty_matrix"][i][j]
                               +traffic["congestion_matrix"][i][j]
                               +carbon["penalty_matrix"][i][j]
                     if i!=j else 0.0 for j in range(n)] for i in range(n)]

        logs[-1].update({"status":"complete",
                         "message":f"OSRM:{osrm['source']} | Weather✓ | Traffic✓ | Carbon✓",
                         "detail":weather["weather_summary"][:300]})
        return {**state, "distance_matrix":enriched, "city_coords":coords,
                "weather_summary":weather["weather_summary"],
                "traffic_summary":traffic["traffic_summary"],
                "carbon_summary":carbon["carbon_summary"],
                "carbon_matrix":carbon["carbon_matrix"],
                "city_weather":weather.get("city_weather",{}),
                "current_step":"enriched","step_logs":logs}
    except Exception as e:
        logs[-1].update({"status":"complete","message":f"Enrichment partial: {e}"})
        return {**state,"current_step":"enriched","step_logs":logs}


# ── Parse + finalize: classical comparison + Supabase + Telegram ──────────────

def parse_and_finalize_node(state: AgentState) -> AgentState:
    state = parse_result_node(state)
    if state.get("error_message"): return state

    city_names = state.get("city_names",[])
    dist_matrix= state.get("distance_matrix",[])
    q_dist     = state.get("route_distance",0.0)
    route      = state.get("optimal_route",[])
    cm         = state.get("carbon_matrix",[])
    idx        = {c:i for i,c in enumerate(city_names)}

    # Classical comparison
    try:
        comp = get_classical_comparison(city_names, dist_matrix, q_dist)
        state = {**state,
                "classical_route":     comp.get("classical_route", []),      # use .get()
                "classical_distance":  comp.get("classical_distance", 0.0),  # use .get()
                "improvement_pct":     comp.get("improvement_pct", 0.0),     # use .get()
                "quantum_advantage_narrative": comp.get("narrative", "")}    # use .get()

    except Exception as e:
        logger.warning("Classical comparison skipped: %s", e)

    # Carbon total for route
    co2 = 0.0

    try:
        if cm and route:
            for k in range(len(route)):
                a,b=route[k],route[(k+1)%len(route)]
                if a in idx and b in idx: co2+=cm[idx[a]][idx[b]]
    except Exception: pass

    # Supabase
    try:
        save_job(job_id=state.get("job_id","?"),city_names=city_names,
                 optimal_route=route,quantum_distance=q_dist,
                 classical_distance=state.get("classical_distance",0.0),
                 improvement_pct=state.get("improvement_pct",0.0),
                 carbon_kg=round(co2,2),
                 quantum_backend=state.get("quantum_backend","aer_simulator"),
                 num_qubits=state.get("num_qubits",0),
                 qaoa_layers=state.get("qaoa_layers",1),
                 total_shots=state.get("total_shots",0),
                 weather_summary=state.get("weather_summary",""),
                 human_readable_result=state.get("human_readable_result",""))
    except Exception as e: logger.warning("Supabase skipped: %s",e)

    # Telegram
    try:
        send_dispatch_alert_sync(
            optimal_route=route, route_distance=q_dist,
            human_readable_result=state.get("human_readable_result",""),
            city_weather=state.get("city_weather"),
            carbon_co2_kg=round(co2,2),
            quantum_backend=state.get("quantum_backend","aer_simulator"),
            num_qubits=state.get("num_qubits",0),
            total_shots=state.get("total_shots",0),
            job_id=state.get("job_id"))
    except Exception as e: logger.warning("Telegram skipped: %s",e)

    return {**state,"current_step":"complete"}


# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph():
    wf = StateGraph(AgentState)
    wf.add_node("transcribe",    transcribe_audio_node)
    wf.add_node("analyze",       analyze_with_gemini_node)
    wf.add_node("enrich",        enrich_with_context_node)
    wf.add_node("build_circuit", build_qubo_and_circuit_node)
    wf.add_node("execute",       execute_quantum_node)
    wf.add_node("reflect",       reflect_on_result_node)
    wf.add_node("parse",         parse_and_finalize_node)

    wf.set_entry_point("transcribe")
    wf.add_edge("transcribe",    "analyze")
    wf.add_edge("analyze",       "enrich")
    wf.add_edge("enrich",        "build_circuit")
    wf.add_edge("build_circuit", "execute")
    wf.add_edge("execute",       "reflect")
    wf.add_conditional_edges("reflect", reflection_router,
                             {"build_circuit":"build_circuit","parse":"parse"})
    wf.add_edge("parse", END)
    return wf.compile()


quantum_agent = _build_graph()
logger.info("Q-Optima enhanced agent compiled ✓  (Speechmatics+OSRM+Reflect+Classical+WS+Supabase+Voice)")


def run_agent(job_id, audio_bytes, image_bytes, image_mime_type="image/jpeg"):
    initial: AgentState = {
        "job_id":job_id,"audio_bytes":audio_bytes,
        "image_bytes":image_bytes,"image_mime_type":image_mime_type,
        "current_step":"queued","step_logs":[],"error_message":None,
        "reflection_retries":0,"reflection_action":"accept",
    }
    final = quantum_agent.invoke(initial)
    logger.info("Agent done — job=%s step=%s", job_id, final.get("current_step"))
    return final
