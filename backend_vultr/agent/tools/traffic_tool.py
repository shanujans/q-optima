# TomTom Traffic Flow API — real-time congestion penalties.

from __future__ import annotations
import asyncio, logging, math
from typing import Any, Dict, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)
TOMTOM_FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json"

def _midpoint(lat1,lon1,lat2,lon2): return (lat1+lat2)/2, (lon1+lon2)/2

def _congestion(flow:Optional[Dict[str,Any]]) -> Tuple[float,str]:
    if not flow: return 0.0, "data unavailable"
    cur=float(flow.get("currentSpeed",0)); ff=float(flow.get("freeFlowSpeed",1))
    conf=float(flow.get("confidence",1))
    if ff<=0: return 0.0, "no road data"
    ratio=max(0.0,min(1.0,1.0-cur/ff))*conf
    desc=("free flow" if ratio<0.10 else "light congestion" if ratio<0.30
          else "moderate congestion" if ratio<0.55 else "heavy congestion" if ratio<0.75
          else "standstill")
    return round(ratio,3), desc

async def _fetch_flow(client:httpx.AsyncClient, lat:float, lon:float,
                       api_key:str) -> Optional[Dict[str,Any]]:
    try:
        r=await client.get(TOMTOM_FLOW_URL,
            params={"point":f"{lat},{lon}","unit":"KMPH","openLr":"false","key":api_key},
            timeout=8.0)
        r.raise_for_status()
        return r.json().get("flowSegmentData")
    except Exception as e:
        logger.warning("TomTom failed (%.4f,%.4f): %s", lat, lon, e)
        return None

async def get_traffic_context(city_names:List[str], city_coords:List[Tuple[float,float]],
                               distance_matrix:List[List[float]], tomtom_api_key:str,
                               max_penalty_factor:float=0.40) -> Dict[str,Any]:
    n=len(city_names)
    max_dist=max(max(r) for r in distance_matrix) if distance_matrix else 100.0
    max_p=max_dist*max_penalty_factor
    edges=[(i,j,*_midpoint(*city_coords[i],*city_coords[j]))
           for i in range(n) for j in range(i+1,n)]

    async with httpx.AsyncClient() as client:
        flows=await asyncio.gather(*[_fetch_flow(client,lat,lon,tomtom_api_key)
                                      for _,_,lat,lon in edges], return_exceptions=True)

    matrix=[[0.0]*n for _ in range(n)]; lines=[]
    for idx,(i,j,_,_) in enumerate(edges):
        flow=flows[idx] if not isinstance(flows[idx],Exception) else None
        ratio,desc=_congestion(flow); p=round(ratio*max_p,2)
        matrix[i][j]=p; matrix[j][i]=p
        lines.append(f"- {city_names[i]}→{city_names[j]}: {desc} (penalty +{p:.1f})")

    return {"traffic_summary":"TRAFFIC CONTEXT:\n"+"\n".join(lines),
            "congestion_matrix":matrix}

def fetch_traffic_sync(city_names:List[str], city_coords:List[Tuple[float,float]],
                        distance_matrix:List[List[float]], tomtom_api_key:str,
                        max_penalty_factor:float=0.40) -> Dict[str,Any]:
    if not tomtom_api_key:
        n=len(city_names)
        return {"traffic_summary":"Traffic skipped (no API key).",
                "congestion_matrix":[[0.0]*n for _ in range(n)]}
    try:
        return asyncio.run(get_traffic_context(
            city_names,city_coords,distance_matrix,tomtom_api_key,max_penalty_factor))
    except Exception as e:
        n=len(city_names)
        logger.error("Traffic tool failed: %s", e)
        return {"traffic_summary":f"Traffic unavailable: {e}",
                "congestion_matrix":[[0.0]*n for _ in range(n)]}
