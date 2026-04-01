/**
 * Geocoding Service using GraphHopper API
 * Address autocomplete filtered to Toronto bounding box.
 */

export interface AddressSuggestion {
  display_name: string
  lat: string
  lon: string
  place_id: number
  osm_type: string
  type: string
}

const GRAPHHOPPER_API_KEY = process.env.REACT_APP_GRAPHHOPPER_API_KEY || ""
const GRAPHHOPPER_GEOCODE_URL = "https://graphhopper.com/api/1/geocode"

// Toronto bounding box
const TORONTO_BBOX = {
  min_lat: 43.58,
  max_lat: 43.86,
  min_lon: -79.64,
  max_lon: -79.12,
}

let lastRequestTime = 0
const MIN_REQUEST_INTERVAL = 300

export async function searchAddresses(query: string): Promise<AddressSuggestion[]> {
  if (!query || query.trim().length < 3) return []

  const now = Date.now()
  const wait = MIN_REQUEST_INTERVAL - (now - lastRequestTime)
  if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait))

  try {
    const searchQuery = query.toLowerCase().includes("toronto")
      ? query
      : `${query}, Toronto, ON`

    const params = new URLSearchParams({
      q: searchQuery,
      key: GRAPHHOPPER_API_KEY,
      limit: "10",
      locale: "en",
    })

    const response = await fetch(`${GRAPHHOPPER_GEOCODE_URL}?${params}`)
    lastRequestTime = Date.now()

    if (!response.ok) return []

    const data = await response.json()
    if (!data.hits || data.hits.length === 0) return []

    return data.hits
      .filter((hit: any) => {
        const { lat, lng } = hit.point
        return (
          lat >= TORONTO_BBOX.min_lat &&
          lat <= TORONTO_BBOX.max_lat &&
          lng >= TORONTO_BBOX.min_lon &&
          lng <= TORONTO_BBOX.max_lon
        )
      })
      .map((hit: any, index: number) => {
        const parts: string[] = []
        if (hit.housenumber && hit.street) {
          parts.push(`${hit.housenumber} ${hit.street}`)
        } else if (hit.street) {
          parts.push(hit.street)
        } else if (hit.name) {
          parts.push(hit.name)
        }
        parts.push("Toronto, ON")

        return {
          display_name: parts.join(", "),
          lat: hit.point.lat.toString(),
          lon: hit.point.lng.toString(),
          place_id: hit.osm_id || index,
          osm_type: hit.osm_type || "node",
          type: hit.osm_value || "place",
        }
      })
      .slice(0, 5)
  } catch {
    return []
  }
}

export function formatAddress(displayName: string): string {
  const parts = displayName.split(", ")
  return parts.slice(0, Math.min(4, parts.length)).join(", ")
}
