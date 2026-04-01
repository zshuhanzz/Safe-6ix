# Safe 6ix

A pedestrian safety routing app for Toronto. Enter an origin and destination, and the app recommends the safest walking route based on real Toronto Police Service crime data.

---

## How It Works

**Data:** The app fetches crime incident data from 3 Toronto Police Service datasets — Major Crime Indicators, Shootings & Firearm Discharges, and Homicide — and caches it locally. The cache refreshes every hour.

**Risk Scoring:** Each route is scored by analyzing every crime incident within 300m of the path. Incidents are weighted by:
- **Type** — shootings, homicides, robbery, and assault score highest; break & enter is medium; everything else is low
- **Distance** — incidents closer to the path contribute more risk
- **Recency** — older crimes are weighted down using a time decay formula (`exp(-years / 3)`)

**Routing:** The app uses GraphHopper to generate 5 candidate walking routes, then applies a Multi-Objective Shortest Path algorithm with weighted sum scalarization to select 3 Pareto-optimal routes:
- **Optimal** — best balance of safety and distance (70% safety, 30% distance)
- **Safest** — lowest risk, even if longer
- **Shortest** — shortest distance, even if less safe

---

## Setup

**Requirements:** Python 3.9+, Node.js 16+, a free GraphHopper API key ([graphhopper.com](https://www.graphhopper.com/))

Run `START.bat` — it handles everything on first launch (virtual environment, dependencies, .env setup) and starts both servers. The app opens automatically at `http://localhost:3000`.

---

## Project Structure

```
Safe 6ix/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, routing logic, graph theory selection
│   │   ├── data_fetcher.py  # TPS API integration and caching
│   │   └── risk_scorer.py   # Risk scoring formula
│   ├── cache/               # Cached crime data (auto-generated, not committed)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/      # React UI (map, route input, route cards)
│       └── services/        # GraphHopper API client, geocoding
├── .env                     # API keys (not committed)
├── .env.example
└── START.bat                # One-click launcher
```

---

## Tech Stack

Backend: FastAPI, Python, APScheduler, Geopy
Frontend: React, TypeScript, Tailwind CSS, React Leaflet
APIs: Toronto Police Service ArcGIS REST, GraphHopper
Map: OpenStreetMap

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check and incident count |
| GET | `/api/data/stats` | Crime data statistics |
| GET | `/api/incidents` | All incidents for map markers |
| POST | `/api/routes` | Calculate routes for origin → destination |
