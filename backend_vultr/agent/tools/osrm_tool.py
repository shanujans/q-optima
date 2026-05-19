from __future__ import annotations
import asyncio, logging
from typing import Any, Dict, List, Tuple
import httpx

logger = logging.getLogger(__name__)
OSRM_BASE = "https://router.project-osrm.org/table/v1/driving"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


async def _geocode_all(city_names: List[str]) -> List[Tuple[float, float]]:
    """Geocode all cities concurrently via Open-Meteo free geocoder."""
    async def _one(client: httpx.AsyncClient, city: str) -> Tuple[float, float]:
        try:
            r = await client.get(GEOCODING_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
                timeout=8.0)
            res = r.json().get("results", [])
            if res:
                return res[0]["latitude"], res[0]["longitude"]
        except Exception as e:
            logger.warning("Geocode failed for %s: %s", city, e)
        return 45.4654, 9.1859  # fallback: Milan

    async with httpx.AsyncClient() as client:
        return list(await asyncio.gather(*[_one(client, c) for c in city_names]))


async def _osrm_matrix(coords: List[Tuple[float, float]]) -> List[List[float]]:
    """
    Call OSRM Table API to get driving duration matrix.
    Returns distance matrix in KM (converted from seconds using avg 50 km/h).
    OSRM returns durations in seconds — we convert to km equivalent for QUBO.
    """
    # OSRM expects lon,lat order
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"{OSRM_BASE}/{coord_str}"

    async with httpx.AsyncClient() as client:
        r = await client.get(url,
            params={"annotations": "distance"},  # get distance in metres
            timeout=15.0)
        r.raise_for_status()
        data = r.json()

    if data.get("code") != "Ok":
        raise ValueError(f"OSRM error: {data.get('message', 'unknown')}")

    # distances in metres → km
    raw = data.get("distances", [])
    n = len(coords)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and raw and i < len(raw) and j < len(raw[i]):
                matrix[i][j] = round(raw[i][j] / 1000.0, 2)
    return matrix


async def get_real_distances(
    city_names: List[str],
    gemini_matrix: List[List[float]],
) -> Dict[str, Any]:
    """
    Get real driving distances from OSRM.
    Falls back to Gemini's visual estimates if OSRM fails.

    Returns:
        distance_matrix : List[List[float]] — n×n matrix in km
        city_coords     : List[Tuple[float,float]] — for TomTom midpoint queries
        source          : "osrm" | "gemini_fallback"
    """
    try:
        coords = await _geocode_all(city_names)
        matrix = await _osrm_matrix(coords)
        logger.info("OSRM real distances fetched for %d cities.", len(city_names))
        return {
            "distance_matrix": matrix,
            "city_coords":     coords,
            "source":          "osrm",
        }
    except Exception as e:
        logger.warning("OSRM failed — using Gemini estimates: %s", e)
        n = len(city_names)
        # Generate placeholder coords (Milan area) for TomTom
        coords = [(45.4654 + i*0.05, 9.1859 + i*0.05) for i in range(n)]
        return {
            "distance_matrix": gemini_matrix,
            "city_coords":     coords,
            "source":          "gemini_fallback",
        }


def fetch_real_distances_sync(
    city_names: List[str],
    gemini_matrix: List[List[float]],
) -> Dict[str, Any]:
    try:
        return asyncio.run(get_real_distances(city_names, gemini_matrix))
    except Exception as e:
        n = len(city_names)
        logger.error("OSRM sync failed: %s", e)
        coords = [(45.4654 + i*0.05, 9.1859 + i*0.05) for i in range(n)]
        return {"distance_matrix": gemini_matrix, "city_coords": coords,
                "source": "gemini_fallback"}
