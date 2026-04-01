# -*- coding: utf-8 -*-
"""
Safe 6ix Backend - FastAPI Application
Route safety analysis using Toronto Police Service crime data.
Graph theory: bi-criteria shortest path with Pareto-optimal selection.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import os
import math
import time
import asyncio
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from geopy.distance import geodesic
import requests

try:
    from .data_fetcher import TorontoDataFetcher
    from .risk_scorer import RiskScorer
except ImportError:
    from data_fetcher import TorontoDataFetcher
    from risk_scorer import RiskScorer

load_dotenv()

# Services
data_fetcher = TorontoDataFetcher()
risk_scorer = RiskScorer()
scheduler = BackgroundScheduler()

# Caches
reverse_geocode_cache: Dict[str, str] = {}
geocode_cache: Dict[str, Optional[Dict[str, float]]] = {}
last_geocode_request_time = 0.0
geocode_semaphore = asyncio.Semaphore(2)

# Config
GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY", "")
GEOCODING_URL = "https://graphhopper.com/api/1/geocode"
ROUTING_URL = "https://graphhopper.com/api/1/route"

# Toronto bounding box
TORONTO_BBOX = {"min_lat": 43.58, "max_lat": 43.86, "min_lng": -79.64, "max_lng": -79.12}

# Graph theory weights: safety matters more than distance
SAFETY_WEIGHT = 0.70
DISTANCE_WEIGHT = 0.30


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Safe 6ix Backend (Toronto)...")
    data_fetcher.fetch_all_data()

    interval_minutes = int(os.getenv("DATA_REFRESH_INTERVAL", 1440))
    scheduler.add_job(
        periodic_data_fetch,
        'interval',
        minutes=interval_minutes,
        id='fetch_data',
        replace_existing=True
    )
    scheduler.start()
    print(f"Data refresh scheduled every {interval_minutes} minutes")
    print("Safe 6ix Backend ready!")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Safe 6ix API",
    description="Route safety analysis for Toronto, ON",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class RouteRequest(BaseModel):
    origin: str
    destination: str


class CoordinatePair(BaseModel):
    lat: float
    lng: float


class RouteAnalysis(BaseModel):
    id: int
    name: str
    description: str
    distance: str
    time: str
    safetyScore: int
    total_risk: float
    coordinates: List[CoordinatePair]
    color: str


class RoutesResponse(BaseModel):
    routes: List[RouteAnalysis]
    originCoords: CoordinatePair
    destCoords: CoordinatePair
    data_timestamp: str


# --- Helper Functions ---

def validate_coordinates(lat: float, lng: float) -> bool:
    """Return True if coordinates are valid numbers in range."""
    try:
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            return False
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return False
        if math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng):
            return False
        return True
    except:
        return False


async def reverse_geocode(lat: float, lng: float) -> str:
    """Convert coordinates to street name using GraphHopper. Returns coord string on failure."""
    global last_geocode_request_time

    if not validate_coordinates(lat, lng):
        return f"{lat:.4f}, {lng:.4f}"

    cache_key = f"{lat:.4f},{lng:.4f}"
    if cache_key in reverse_geocode_cache:
        return reverse_geocode_cache[cache_key]

    try:
        current_time = time.time()
        wait = 1.0 - (current_time - last_geocode_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        last_geocode_request_time = time.time()

        response = requests.get(
            f"{GEOCODING_URL}?point={lat},{lng}&key={GRAPHHOPPER_API_KEY}&reverse=true&locale=en",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        result = f"{lat:.4f}, {lng:.4f}"
        if data.get("hits"):
            hit = data["hits"][0]
            street = hit.get("street", "")
            house_number = hit.get("housenumber", "")
            if street:
                result = f"{house_number} {street}".strip() if house_number else street
            elif hit.get("name"):
                result = hit["name"]

        reverse_geocode_cache[cache_key] = result
        return result
    except Exception as e:
        result = f"{lat:.4f}, {lng:.4f}"
        reverse_geocode_cache[cache_key] = result
        return result


async def geocode_address(address: str, retry_count: int = 0, max_retries: int = 5) -> Optional[Dict[str, float]]:
    """Convert address string to lat/lng using GraphHopper, filtered to Toronto."""
    global last_geocode_request_time

    async with geocode_semaphore:
        try:
            if "toronto" not in address.lower():
                address = f"{address}, Toronto, ON"

            cache_key = address.lower().strip()
            if cache_key in geocode_cache:
                return geocode_cache[cache_key]

            current_time = time.time()
            wait = 3.0 - (current_time - last_geocode_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            last_geocode_request_time = time.time()

            response = requests.get(
                f"{GEOCODING_URL}?q={address}&key={GRAPHHOPPER_API_KEY}",
                timeout=10
            )

            if response.status_code == 429:
                if retry_count < max_retries:
                    backoff = 10 * (3 ** retry_count)
                    print(f"Rate limit hit. Waiting {backoff}s before retry {retry_count + 1}/{max_retries}...")
                    await asyncio.sleep(backoff)
                    return await geocode_address(address, retry_count + 1, max_retries)
                geocode_cache[cache_key] = None
                return None

            response.raise_for_status()
            data = response.json()

            if data.get("hits"):
                for hit in data["hits"]:
                    point = hit["point"]
                    lat, lng = point["lat"], point["lng"]
                    # Toronto bounding box filter
                    if (TORONTO_BBOX["min_lat"] <= lat <= TORONTO_BBOX["max_lat"] and
                            TORONTO_BBOX["min_lng"] <= lng <= TORONTO_BBOX["max_lng"]):
                        geocode_cache[cache_key] = point
                        return point

                print(f"No Toronto coordinates found for '{address}'")
                geocode_cache[cache_key] = None
                return None

            geocode_cache[cache_key] = None
            return None

        except requests.exceptions.HTTPError as e:
            if "429" in str(e) and retry_count < max_retries:
                backoff = 10 * (3 ** retry_count)
                await asyncio.sleep(backoff)
                return await geocode_address(address, retry_count + 1, max_retries)
            geocode_cache[cache_key] = None
            return None
        except Exception as e:
            print(f"Geocoding error: {e}")
            if "429" not in str(e):
                geocode_cache[cache_key] = None
            return None


async def get_graphhopper_routes(origin_coords: Dict, dest_coords: Dict, num_routes: int = 5) -> List[Dict]:
    """Request walking route alternatives from GraphHopper."""
    if not validate_coordinates(origin_coords['lat'], origin_coords['lng']):
        raise ValueError(f"Invalid origin coordinates: {origin_coords}")
    if not validate_coordinates(dest_coords['lat'], dest_coords['lng']):
        raise ValueError(f"Invalid destination coordinates: {dest_coords}")

    point_str = f"point={origin_coords['lat']},{origin_coords['lng']}&point={dest_coords['lat']},{dest_coords['lng']}"
    params = {
        "vehicle": "foot",
        "locale": "en",
        "points_encoded": "false",
        "algorithm": "alternative_route",
        "alternative_route.max_paths": str(num_routes),
        "key": GRAPHHOPPER_API_KEY,
    }

    try:
        response = requests.get(
            f"{ROUTING_URL}?{point_str}&" + "&".join([f"{k}={v}" for k, v in params.items()]),
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        routes = []
        if data.get("paths"):
            for path in data["paths"]:
                routes.append({
                    "distance": path["distance"],
                    "time": path["time"],
                    "coordinates": [(coord[1], coord[0]) for coord in path["points"]["coordinates"]],
                })
            print(f"GraphHopper returned {len(routes)} routes")
        return routes

    except Exception as e:
        print(f"GraphHopper error: {e}")
        return []


def select_optimal_routes(scored_routes: List[Dict]) -> List[Dict]:
    """
    Multi-objective route selection using bi-criteria shortest path (MOSP).

    Each route is scored on two dimensions:
        - normalized safety risk (lower = safer)
        - normalized distance (lower = shorter)

    Composite score = 0.7 * norm_risk + 0.3 * norm_dist

    Returns 3 Pareto-optimal routes:
        1. Optimal: lowest composite score (best safety/distance balance)
        2. Safest: lowest risk (even if longer)
        3. Shortest: shortest distance that differs from Route 1
    """
    if not scored_routes:
        return []

    max_risk = max(r["total_risk"] for r in scored_routes) or 1
    max_dist = max(r["distance_km"] for r in scored_routes) or 1

    for r in scored_routes:
        r["norm_risk"] = r["total_risk"] / max_risk
        r["norm_dist"] = r["distance_km"] / max_dist
        r["composite"] = SAFETY_WEIGHT * r["norm_risk"] + DISTANCE_WEIGHT * r["norm_dist"]

    # Route 1: best composite score
    route1 = min(scored_routes, key=lambda r: r["composite"])

    # Route 2: safest (lowest risk), deduplicated from route1
    remaining = [r for r in scored_routes if r is not route1]
    if remaining:
        route2 = min(remaining, key=lambda r: r["total_risk"])
    else:
        route2 = route1

    # Route 3: shortest distance not already selected
    not_selected = [r for r in scored_routes if r is not route1 and r is not route2]
    if not_selected:
        route3 = min(not_selected, key=lambda r: r["distance_km"])
    elif remaining:
        route3 = max(remaining, key=lambda r: r["distance_km"])
    else:
        route3 = route1

    return [route1, route2, route3]


def periodic_data_fetch():
    """Scheduled background data refresh."""
    print(f"[{datetime.now()}] Fetching updated Toronto crime data...")
    try:
        data_fetcher.fetch_all_data()
        print("Data fetch complete")
    except Exception as e:
        print(f"Data fetch failed: {e}")


# --- API Endpoints ---

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Safe 6ix API - Toronto",
        "version": "2.0.0",
        "last_data_fetch": data_fetcher.last_fetch_time.isoformat() if data_fetcher.last_fetch_time else None
    }


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "crime_incidents": len(data_fetcher.crime_data),
        "last_fetch": data_fetcher.last_fetch_time.isoformat() if data_fetcher.last_fetch_time else None,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/data/stats")
async def get_data_stats():
    return {
        "crime_incidents": len(data_fetcher.crime_data),
        "last_fetch": data_fetcher.last_fetch_time.isoformat() if data_fetcher.last_fetch_time else None,
    }


@app.get("/api/incidents")
async def get_all_incidents():
    """Return all crime incidents formatted for map markers."""
    incidents = []
    for crime in data_fetcher.crime_data:
        lat = crime.get("lat_wgs84")
        lng = crime.get("long_wgs84")
        if lat is None or lng is None:
            continue
        try:
            lat, lng = float(lat), float(lng)
        except (ValueError, TypeError):
            continue
        if not validate_coordinates(lat, lng):
            continue

        incidents.append({
            "type": "crime",
            "title": crime.get("offence", "Unknown Incident"),
            "date": crime.get("occ_date", ""),
            "coordinates": {"lat": lat, "lng": lng}
        })

    return {
        "incidents": incidents,
        "total_count": len(incidents),
        "last_fetch": data_fetcher.last_fetch_time.isoformat() if data_fetcher.last_fetch_time else None
    }


@app.post("/api/routes", response_model=RoutesResponse)
async def calculate_routes(request: RouteRequest):
    """Calculate safe walking routes using multi-objective graph theory selection."""
    try:
        return await asyncio.wait_for(_calculate_routes_internal(request), timeout=60.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Route calculation timed out. Please try different addresses.")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Route calculation error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


async def _calculate_routes_internal(request: RouteRequest):
    # Validate inputs
    if not request.origin or not request.origin.strip():
        raise HTTPException(status_code=400, detail="Origin address cannot be empty.")
    if not request.destination or not request.destination.strip():
        raise HTTPException(status_code=400, detail="Destination address cannot be empty.")

    # Step 1: Geocode
    print(f"Geocoding: '{request.origin}' -> '{request.destination}'")
    origin_coords, dest_coords = await asyncio.gather(
        geocode_address(request.origin),
        geocode_address(request.destination)
    )

    if not origin_coords or not dest_coords:
        raise HTTPException(status_code=400, detail="Could not find those addresses in Toronto. Please check and try again.")

    distance_m = geodesic(
        (origin_coords["lat"], origin_coords["lng"]),
        (dest_coords["lat"], dest_coords["lng"])
    ).meters

    if distance_m < 50:
        raise HTTPException(status_code=400, detail="Origin and destination are too close together. Please enter locations at least 50m apart.")

    # Step 2: Get candidate routes from GraphHopper
    print("Fetching routes from GraphHopper...")
    raw_routes = await get_graphhopper_routes(origin_coords, dest_coords, num_routes=5)

    if not raw_routes:
        raise HTTPException(status_code=500, detail="Could not generate routes. Please try again.")

    # Step 3: Score each route
    print(f"Scoring {len(raw_routes)} candidate routes...")
    crime_data = data_fetcher.crime_data
    scored = []

    for route in raw_routes:
        path_coords = [{"lat": lat, "lng": lng} for lat, lng in route["coordinates"]]
        analysis = risk_scorer.analyze_route(path_coords, crime_data)
        distance_km = route["distance"] / 1000

        scored.append({
            "distance_km": distance_km,
            "distance_m": route["distance"],
            "time_ms": route["time"],
            "total_risk": analysis["total_risk"],
            "coordinates": route["coordinates"],
        })

    # Step 4: Pareto-optimal selection (bi-criteria shortest path)
    print("Applying multi-objective route selection...")
    selected = select_optimal_routes(scored)

    if not selected:
        raise HTTPException(status_code=500, detail="No valid routes found.")

    # Step 5: Build response
    route_configs = [
        {"name": "Optimal Route",  "color": "#10b981", "desc_prefix": "Best balance of safety and distance"},
        {"name": "Safest Route",   "color": "#3b82f6", "desc_prefix": "Safest path, avoids highest-risk areas"},
        {"name": "Shortest Route", "color": "#f59e0b", "desc_prefix": "Shortest path, slightly less safe"},
    ]

    result_routes = []
    for i, (route, config) in enumerate(zip(selected, route_configs)):
        distance_mi = round(route["distance_km"] * 0.621371, 1)
        time_min = round(route["time_ms"] / 1000 / 60)
        total_risk = route["total_risk"]

        safety_score = int(100 * math.exp(-total_risk / 10)) if total_risk > 0 else 100
        safety_score = max(0, min(100, safety_score))

        nearby = risk_scorer.find_nearby_incidents(
            [(lat, lng) for lat, lng in route["coordinates"]],
            crime_data
        )

        if nearby:
            threat_count = len(nearby)
            description = f"{config['desc_prefix']}. {threat_count} incident(s) within 120m. Risk score: {total_risk:.1f}"
        else:
            description = f"{config['desc_prefix']}. No incidents within 120m. Risk score: {total_risk:.1f}"

        result_routes.append({
            "id": i + 1,
            "name": config["name"],
            "description": description,
            "distance": f"{distance_mi} mi",
            "time": f"{time_min} min",
            "safetyScore": safety_score,
            "total_risk": total_risk,
            "coordinates": [{"lat": lat, "lng": lng} for lat, lng in route["coordinates"]],
            "color": config["color"],
        })

    print(f"Returning {len(result_routes)} routes")
    return {
        "routes": result_routes,
        "originCoords": {"lat": origin_coords["lat"], "lng": origin_coords["lng"]},
        "destCoords": {"lat": dest_coords["lat"], "lng": dest_coords["lng"]},
        "data_timestamp": data_fetcher.last_fetch_time.isoformat() if data_fetcher.last_fetch_time else datetime.now().isoformat()
    }
