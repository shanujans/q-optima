# backend_vultr/agent/tools/telegram_tool.py
# Telegram Bot API — fires dispatch alert at end of pipeline.
# Setup: @BotFather → /newbot → copy token.
# Get chat_id: curl "https://api.telegram.org/bot<TOKEN>/getUpdates"

from __future__ import annotations
import asyncio, logging, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)
TG_BASE = "https://api.telegram.org/bot{token}/sendMessage"

def _build_message(optimal_route:List[str], route_distance:float,
                   human_readable_result:str, city_weather:Optional[Dict]=None,
                   carbon_co2_kg:Optional[float]=None, quantum_backend:str="aer_simulator",
                   num_qubits:int=0, total_shots:int=0, job_id:Optional[str]=None) -> str:
    route_str=" → ".join(optimal_route)+f" → {optimal_route[0]}"
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    backend_label=("🌐 IBM Quantum" if quantum_backend=="ibm_quantum" else "🖥️ Aer Simulator")
    carbon_line=f"\n🌿 *Carbon:* `{carbon_co2_kg:.1f} kg CO₂e`" if carbon_co2_kg else ""
    weather_lines=""
    if city_weather:
        for city,data in city_weather.items():
            weather_lines+=f"  • *{city}*: {data.get('description','—')}, {data.get('wind_kmh',0):.0f} km/h\n"
    job_line=f"\n🔑 `{job_id}`" if job_id else ""

    msg=(f"🚀 *Q-Optima Dispatch Alert*\n{ts}\n\n"
         f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
         f"📍 *Optimal Route:*\n`{route_str}`\n\n"
         f"📏 *Distance:* `{route_distance:.1f} units`{carbon_line}\n\n"
         f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
         f"⚛️ *Quantum:* {backend_label}\n"
         f"Qubits: `{num_qubits}` | Shots: `{total_shots:,}`\n\n"
         f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
         f"📋 *Decision:*\n{human_readable_result.strip()}")
    if weather_lines:
        msg+=f"\n\n🌦️ *Weather:*\n{weather_lines}"
    msg+=f"\n\n_Q-Optima · Milan AI Week 2026_{job_line}"
    return msg[:4000]

async def _send(token:str, chat_id:str, text:str) -> Dict[str,Any]:
    async with httpx.AsyncClient() as client:
        r=await client.post(TG_BASE.format(token=token),
            json={"chat_id":chat_id,"text":text,"parse_mode":"Markdown"}, timeout=10.0)
        r.raise_for_status()
        return r.json()

def send_dispatch_alert_sync(optimal_route:List[str], route_distance:float,
                              human_readable_result:str,
                              city_weather:Optional[Dict]=None,
                              carbon_co2_kg:Optional[float]=None,
                              quantum_backend:str="aer_simulator",
                              num_qubits:int=0, total_shots:int=0,
                              job_id:Optional[str]=None) -> Dict[str,Any]:
    token=os.getenv("TELEGRAM_BOT_TOKEN","")
    chat_id=os.getenv("TELEGRAM_CHAT_ID","")
    if not token or not chat_id:
        logger.warning("Telegram credentials not set — skipping alert.")
        return {"ok":False,"error":"credentials not configured"}
    try:
        msg=_build_message(optimal_route,route_distance,human_readable_result,
                           city_weather,carbon_co2_kg,quantum_backend,
                           num_qubits,total_shots,job_id)
        result=asyncio.run(_send(token,chat_id,msg))
        mid=result.get("result",{}).get("message_id")
        logger.info("Telegram alert sent (message_id=%s)", mid)
        return {"ok":True,"message_id":mid}
    except Exception as e:
        logger.error("Telegram failed: %s", e)
        return {"ok":False,"error":str(e)}
