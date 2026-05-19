# Adds weather penalty to QUBO distance matrix.

from __future__ import annotations
import asyncio, logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL   = "https://api.open-meteo.com/v1/forecast"

WMO_SEVERITY: Dict[int, Tuple[float, str]] = {
    0:(0.0,"clear sky"), 1:(0.05,"mainly clear"), 2:(0.10,"partly cloudy"),
    3:(0.15,"overcast"), 45:(0.25,"fog"), 48:(0.30,"icy fog"),
    51:(0.20,"light drizzle"), 53:(0.25,"moderate drizzle"), 55:(0.30,"dense drizzle"),
    61:(0.30,"light rain"), 63:(0.40,"moderate rain"), 65:(0.50,"heavy rain"),
    71:(0.40,"light snow"), 73:(0.55,"moderate snow"), 75:(0.70,"heavy snow"),
    80:(0.35,"rain showers"), 81:(0.45,"moderate showers"), 82:(0.60,"violent showers"),
    95:(0.80,"thunderstorm"), 99:(1.00,"severe thunderstorm"),
}

def _severity(code: int) -> Tuple[float, str]:
    if code in WMO_SEVERITY: return WMO_SEVERITY[code]
    for k in sorted(WMO_SEVERITY, reverse=True):
        if k <= code: return WMO_SEVERITY[k]
    return (0.0, "unknown")

def _city_penalty(code:int, wind:float, precip:float,
                  vis:Optional[float], max_p:float) -> float:
    sev,_ = _severity(code)
    return round((0.40*sev + 0.25*min(wind/80,1) +
                  0.25*min(precip/20,1) + 0.10*max(0,1-(vis or 1000)/1000))*max_p, 2)

async def _geocode(client:httpx.AsyncClient, city:str) -> Tuple[float,float]:
    try:
        r = await client.get(GEOCODING_URL,
            params={"name":city,"count":1,"language":"en","format":"json"}, timeout=8.0)
        res = r.json().get("results",[])
        if res: return res[0]["latitude"], res[0]["longitude"]
    except Exception as e:
        logger.warning("Geocode failed %s: %s", city, e)
    return 45.4654, 9.1859  # fallback Milan

async def _weather(client:httpx.AsyncClient, lat:float, lon:float) -> Dict[str,Any]:
    r = await client.get(WEATHER_URL, params={
        "latitude":lat,"longitude":lon,
        "current":"weather_code,wind_speed_10m,precipitation,visibility",
        "wind_speed_unit":"kmh","forecast_days":1}, timeout=8.0)
    r.raise_for_status()
    return r.json().get("current", {})

async def get_weather_context(city_names:List[str], distance_matrix:List[List[float]],
                               max_penalty_factor:float=0.30) -> Dict[str,Any]:
    n = len(city_names)
    max_dist = max(max(r) for r in distance_matrix) if distance_matrix else 100.0
    max_p = max_dist * max_penalty_factor
    city_weather: Dict[str,Any] = {}
    penalties: List[float] = []
    lines: List[str] = []

    async with httpx.AsyncClient() as client:
        coords = await asyncio.gather(*[_geocode(client,c) for c in city_names], return_exceptions=True)
        weathers = await asyncio.gather(
            *[_weather(client,*coord) if not isinstance(coord,Exception)
              else asyncio.sleep(0,result={}) for coord in coords], return_exceptions=True)

    for i, city in enumerate(city_names):
        wr = weathers[i] if not isinstance(weathers[i], Exception) else {}
        code=int(wr.get("weather_code",0)); wind=float(wr.get("wind_speed_10m",0))
        precip=float(wr.get("precipitation",0)); vis=wr.get("visibility")
        _,desc=_severity(code); p=_city_penalty(code,wind,precip,vis,max_p)
        penalties.append(p)
        city_weather[city]={"description":desc,"wind_kmh":wind,"precipitation_mm":precip,"penalty_added":p}
        lines.append(f"- {city}: {desc}, wind {wind:.0f} km/h — penalty +{p:.1f}")

    penalty_matrix=[[round((penalties[i]+penalties[j])/2,2) if i!=j else 0.0
                     for j in range(n)] for i in range(n)]
    return {"weather_summary":"WEATHER CONTEXT:\n"+"\n".join(lines),
            "penalty_matrix":penalty_matrix, "city_weather":city_weather}

def fetch_weather_sync(city_names:List[str], distance_matrix:List[List[float]],
                        max_penalty_factor:float=0.30) -> Dict[str,Any]:
    try:
        return asyncio.run(get_weather_context(city_names,distance_matrix,max_penalty_factor))
    except Exception as e:
        logger.error("Weather tool failed: %s", e)
        n=len(city_names)
        return {"weather_summary":f"Weather unavailable: {e}",
                "penalty_matrix":[[0.0]*n for _ in range(n)],"city_weather":{}}
