"""
Data Fetcher - Placeholder class (Step 1 cleanup)
Will be replaced with TorontoDataFetcher in Step 2.
"""
import json
import os
import requests
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


class TorontoDataFetcher:
    """Fetches and caches Toronto crime incident data."""

    def __init__(self):
        self.crime_data: List[Dict[str, Any]] = []
        self.last_fetch_time: datetime | None = None

    def fetch_all_data(self) -> List[Dict[str, Any]]:
        """Fetch all crime data and store in self.crime_data."""
        # Step 2 will implement the real Toronto TPS ArcGIS API calls.
        # For now, load from cache if available.
        print("[DATA] Toronto data fetcher - Step 2 will implement live fetch.")
        cached = self._load_from_cache("crime_data.json")
        if cached:
            self.crime_data = cached
            self.last_fetch_time = datetime.now()
            print(f"[CACHE] Loaded {len(self.crime_data)} incidents from cache")
        else:
            self.crime_data = []
            self.last_fetch_time = datetime.now()
            print("[WARN] No cached data found. Will return empty dataset until Step 2.")
        return self.crime_data

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
                    data = json.load(f)
                    return data
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}")
        return []
