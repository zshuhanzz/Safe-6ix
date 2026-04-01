"""
Data Fetcher - Toronto Police Service Open Data
Fetches crime incident data from TPS ArcGIS REST API and caches it locally.

Datasets used:
  - Major Crime Indicators (MCI): Assault, B&E, Robbery, Auto Theft, Theft Over
  - Shootings & Firearm Discharges
  - Homicide

All incidents are normalized to: { lat_wgs84, long_wgs84, offence, occ_date }
"""
import json
import os
import requests
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# TPS ArcGIS REST API base URL
TPS_BASE = "https://services.arcgis.com/S9th0jAJ7bqgIRjw/arcgis/rest/services"

# Datasets to fetch: (service_name, lat_field, lng_field, offence_field)
DATASETS = [
    {
        "name": "Major Crime Indicators",
        "service": "Major_Crime_Indicators_Open_Data",
        "lat_field": "LAT_WGS84",
        "lng_field": "LONG_WGS84",
        "offence_field": "OFFENCE",
        "date_field": "OCC_DATE",
    },
    {
        "name": "Shootings & Firearm Discharges",
        "service": "Shootings_and_Firearm_Discharges_Open_Data",
        "lat_field": "LAT_WGS84",
        "lng_field": "LONG_WGS84",
        "offence_field": "CATEGORY",
        "date_field": "OCC_DATE",
    },
    {
        "name": "Homicide",
        "service": "Homicide_Open_Data",
        "lat_field": "LAT_WGS84",
        "lng_field": "LONG_WGS84",
        "offence_field": "HOMICIDE_TYPE",
        "date_field": "OCC_DATE",
    },
]

# Max records per page (ArcGIS limit)
PAGE_SIZE = 2000


class TorontoDataFetcher:
    """Fetches and caches Toronto Police Service crime incident data."""

    def __init__(self):
        self.crime_data: List[Dict[str, Any]] = []
        self.last_fetch_time: datetime | None = None

    def fetch_all_data(self) -> List[Dict[str, Any]]:
        """
        Fetch all crime data from TPS datasets and store in self.crime_data.
        Falls back to cache if the live fetch fails.
        """
        print("[DATA] Fetching Toronto crime data from TPS Open Data...")
        all_incidents = []

        for dataset in DATASETS:
            try:
                incidents = self._fetch_dataset(dataset)
                all_incidents.extend(incidents)
                print(f"[DATA] {dataset['name']}: {len(incidents)} incidents")
            except Exception as e:
                print(f"[WARN] Failed to fetch {dataset['name']}: {e}")

        if all_incidents:
            self.crime_data = all_incidents
            self.last_fetch_time = datetime.now()
            self._save_to_cache(all_incidents, "crime_data.json")
            print(f"[DATA] Total: {len(all_incidents)} incidents cached")
        else:
            # Live fetch returned nothing — try cache
            print("[WARN] Live fetch failed or returned no data. Loading from cache...")
            cached = self._load_from_cache("crime_data.json")
            if cached:
                self.crime_data = cached
                self.last_fetch_time = datetime.now()
                print(f"[CACHE] Loaded {len(self.crime_data)} incidents from cache")
            else:
                self.crime_data = []
                self.last_fetch_time = datetime.now()
                print("[WARN] No cached data found. Crime data is empty.")

        return self.crime_data

    def _fetch_dataset(self, dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fetch all records for a single TPS ArcGIS dataset using pagination.
        Returns a list of normalized incidents.
        """
        url = f"{TPS_BASE}/{dataset['service']}/FeatureServer/0/query"
        incidents = []
        offset = 0

        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "resultRecordCount": PAGE_SIZE,
                "resultOffset": offset,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                break  # No more records

            for feature in features:
                attrs = feature.get("attributes", {})
                incident = self._normalize(attrs, dataset)
                if incident:
                    incidents.append(incident)

            # If fewer records returned than page size, we've reached the end
            if len(features) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        return incidents

    def _normalize(self, attrs: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Normalize a raw ArcGIS feature into the standard incident schema:
          { lat_wgs84, long_wgs84, offence, occ_date }

        Returns None if lat/lng are missing or invalid.
        """
        lat = attrs.get(dataset["lat_field"])
        lng = attrs.get(dataset["lng_field"])
        offence = attrs.get(dataset["offence_field"], "UNKNOWN")
        occ_date = attrs.get(dataset["date_field"], "")

        # Skip records with missing or zero coordinates
        if lat is None or lng is None:
            return None
        try:
            lat, lng = float(lat), float(lng)
        except (ValueError, TypeError):
            return None
        if lat == 0.0 or lng == 0.0:
            return None

        # TPS dates can be Unix epoch ms (int) or ISO string — normalize to ISO string
        if isinstance(occ_date, (int, float)) and occ_date > 0:
            try:
                occ_date = datetime.utcfromtimestamp(occ_date / 1000).strftime("%Y-%m-%d")
            except Exception:
                occ_date = ""
        elif isinstance(occ_date, str):
            # Keep as-is (already a string)
            pass
        else:
            occ_date = ""

        # For Homicide dataset, map HOMICIDE_TYPE to a clear label
        if dataset["name"] == "Homicide" and offence:
            offence = f"HOMICIDE - {str(offence).upper()}"
        else:
            offence = str(offence).upper()

        return {
            "lat_wgs84": lat,
            "long_wgs84": lng,
            "offence": offence,
            "occ_date": occ_date,
        }

    def _save_to_cache(self, data: List[Dict[str, Any]], filename: str):
        try:
            with open(CACHE_DIR / filename, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[WARN] Cache save failed: {e}")

    def _load_from_cache(self, filename: str) -> List[Dict[str, Any]]:
        try:
            cache_path = CACHE_DIR / filename
            if cache_path.exists():
                with open(cache_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}")
        return []
