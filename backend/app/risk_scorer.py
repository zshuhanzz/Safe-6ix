# -*- coding: utf-8 -*-
"""
Risk Scoring Algorithm Module
Calculates path safety scores using distance-weighted incident data.
No time decay - Toronto data is historical (monthly updates).
"""
import numpy as np
from datetime import datetime
from geopy.distance import geodesic
from typing import List, Dict, Tuple, Any
import math


class RiskScorer:
    """Calculate risk scores for walking paths"""

    # Risk weights by incident type (Toronto TPS categories)
    CRIME_RISK_WEIGHTS = {
        # High risk (w=3)
        "SHOOTING": 3,
        "FIREARM": 3,
        "HOMICIDE": 3,
        "ROBBERY": 3,
        "ASSAULT": 3,
        # Medium risk (w=2)
        "BREAK AND ENTER": 2,
    }

    def __init__(self):
        self.current_time = datetime.now()

    @staticmethod
    def validate_coordinates(lat: float, lng: float) -> bool:
        """Return True if lat/lng are valid numbers in range."""
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

    def assign_risk(self, incident: Dict[str, Any]) -> int:
        """Return risk weight (1-3) for an incident based on its type."""
        description = incident.get("offence", "").upper()
        for crime_type, weight in self.CRIME_RISK_WEIGHTS.items():
            if crime_type in description:
                return weight
        return 1  # default low risk for any unmatched incident

    def min_distance_to_path(self, incident_coords: Tuple[float, float], path: List[Tuple[float, float]]) -> float:
        """Return minimum distance (km) from incident to any point on the path."""
        if len(path) < 2:
            return float('inf')
        if not self.validate_coordinates(incident_coords[0], incident_coords[1]):
            return float('inf')

        min_dist = float('inf')
        for path_point in path:
            try:
                if not self.validate_coordinates(path_point[0], path_point[1]):
                    continue
                dist = geodesic(incident_coords, path_point).kilometers
                min_dist = min(min_dist, dist)
            except:
                continue
        return min_dist

    def calculate_risk_score(self, path: List[Tuple[float, float]], incidents: List[Dict[str, Any]]) -> float:
        """
        Calculate total risk score for a path.

        Formula (no time decay - static weights):
            risk = w^2 * e^(-d^2 / 0.02)

        Where:
            w = risk weight (1=low, 2=medium, 3=high)
            d = minimum distance from incident to route (km)

        Distance decay: 50% risk at 118m, ~0% at 300m+
        """
        total_risk = 0.0
        for incident in incidents:
            lat = incident.get("lat_wgs84")
            lng = incident.get("long_wgs84")
            if lat is None or lng is None:
                continue
            try:
                lat, lng = float(lat), float(lng)
            except (ValueError, TypeError):
                continue

            if not self.validate_coordinates(lat, lng):
                continue

            w = self.assign_risk(incident)
            d = self.min_distance_to_path((lat, lng), path)
            distance_factor = np.exp(-(d ** 2) / 0.02)
            total_risk += (w ** 2) * distance_factor

        return total_risk

    def analyze_route(self, path_coords: List[Dict[str, float]], crime_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze a route and return its total risk score."""
        path = [(coord["lat"], coord["lng"]) for coord in path_coords]
        total_risk = self.calculate_risk_score(path, crime_data)
        return {
            "total_risk": total_risk,
            "crime_count": len(crime_data)
        }

    def calculate_path_length(self, path: List[Tuple[float, float]]) -> float:
        """Return total path length in kilometers."""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(len(path) - 1):
            total += geodesic(path[i], path[i + 1]).kilometers
        return total

    def find_nearby_incidents(self, path: List[Tuple[float, float]], incidents: List[Dict[str, Any]],
                              radius_km: float = 0.118) -> List[Dict[str, Any]]:
        """
        Return incidents within radius_km of the path.
        Default radius = 118m (50% distance decay point).
        """
        nearby = []
        for incident in incidents:
            lat = incident.get("lat_wgs84")
            lng = incident.get("long_wgs84")
            if lat is None or lng is None:
                continue
            try:
                lat, lng = float(lat), float(lng)
            except (ValueError, TypeError):
                continue

            if not self.validate_coordinates(lat, lng):
                continue

            incident_coords = (lat, lng)
            min_dist = self.min_distance_to_path(incident_coords, path)
            weight = self.assign_risk(incident)

            if min_dist <= radius_km:
                distance_factor = np.exp(-(min_dist ** 2) / 0.02)
                nearby.append({
                    "incident": incident,
                    "coords": incident_coords,
                    "min_distance_km": min_dist,
                    "weight": weight,
                    "risk_contribution": (weight ** 2) * distance_factor
                })

        return nearby
