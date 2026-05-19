# Climatiq API — ESG carbon footprint per route segment.

from __future__ import annotations
import asyncio, logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

CLIMATIQ_URL      = "https://beta3.api.climatiq.io/estimate"
EMISSION_FACTOR   = ("freight_vehicle-vehicle_type_hgv-fuel_source_diesel"
                     "-vehicle_weight_gt_17t-percentage_laden_50")
DEFAULT_CARGO_T   = 5.0
CARBON_COST       = 0.5   # distance units per kg CO₂e (tune to balance objectives)

def _offline_co2(dist_km:float, tonnes:float) -> float:
    return dist_km * tonnes * 0.08   # EU HGV average kg CO₂e / tonne-km

async def _estimate(client:httpx.AsyncClient, api_key:str,
                    dist_km:float, tonnes:float) -> Optional[Dict[str,Any]]:
    if dist_km <= 0: return None
    try:
        r=await client.post(CLIMATIQ_URL,
            json={"emission_factor":{"activity_id":EMISSION_FACTOR,"data_version":"^1"},
                  "parameters":{"distance":dist_km,"distance_unit":"km",
                                "weight":tonnes,"weight_unit":"t"}},
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Climatiq failed (%.1f km): %s", dist_km, e)
        return None

async def get_carbon_context(city_names:List[str], distance_matrix:List[List[float]],
                              climatiq_api_key:str,
                              cargo_tonnes:float=DEFAULT_CARGO_T) -> Dict[str,Any]:
    n=len(city_names)
    pairs=[(i,j) for i in range(n) for j in range(i+1,n)]
    dists=[distance_matrix[i][j] for i,j in pairs]

    if climatiq_api_key:
        async with httpx.AsyncClient() as client:
            results=await asyncio.gather(
                *[_estimate(client,climatiq_api_key,d,cargo_tonnes) for d in dists],
                return_exceptions=True)
    else:
        results=[None]*len(pairs)

    co2_mat=[[0.0]*n for _ in range(n)]
    pen_mat=[[0.0]*n for _ in range(n)]
    lines=[]

    for idx,(i,j) in enumerate(pairs):
        res=results[idx] if not isinstance(results[idx],Exception) else None
        co2=float(res["co2e"]) if res and "co2e" in res else _offline_co2(dists[idx],cargo_tonnes)
        src="Climatiq" if res and "co2e" in res else "offline"
        p=round(co2*CARBON_COST,2)
        co2_mat[i][j]=co2_mat[j][i]=co2
        pen_mat[i][j]=pen_mat[j][i]=p
        lines.append(f"- {city_names[i]}→{city_names[j]}: {co2:.1f} kg CO₂e [{src}] penalty +{p:.1f}")

    return {"carbon_summary":"CARBON/ESG CONTEXT:\n"+"\n".join(lines),
            "carbon_matrix":co2_mat, "penalty_matrix":pen_mat}

def fetch_carbon_sync(city_names:List[str], distance_matrix:List[List[float]],
                       climatiq_api_key:str,
                       cargo_tonnes:float=DEFAULT_CARGO_T) -> Dict[str,Any]:
    try:
        return asyncio.run(get_carbon_context(
            city_names,distance_matrix,climatiq_api_key,cargo_tonnes))
    except Exception as e:
        logger.error("Carbon tool failed: %s", e)
        n=len(city_names)
        return {"carbon_summary":f"Carbon unavailable: {e}",
                "carbon_matrix":[[0.0]*n for _ in range(n)],
                "penalty_matrix":[[0.0]*n for _ in range(n)]}
