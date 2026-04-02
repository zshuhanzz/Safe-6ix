import type { Route } from "@/components/safe-6ix-app"

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"

export async function calculateRoutes(
  origin: string,
  destination: string
): Promise<{ routes: Route[]; originCoords: { lat: number; lng: number }; destCoords: { lat: number; lng: number } } | null> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/routes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin, destination }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Backend error: ${response.statusText}`)
    }

    const data = await response.json()
    return {
      routes: data.routes,
      originCoords: data.originCoords,
      destCoords: data.destCoords,
    }
  } catch (error) {
    if (error instanceof TypeError && error.message.includes("fetch")) {
      throw new Error("Cannot connect to Safe 6ix backend. Please ensure the backend server is running on http://localhost:8000")
    }
    throw error
  }
}
