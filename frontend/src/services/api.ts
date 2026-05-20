import axios from "axios";

import type {
  DatePlanRequestPayload,
  Itinerary,
  LocationCandidate,
  PlanningStreamEvent,
  SelectedLocation,
  TripDetailResponse,
  TripEditPayload,
  TripListResponse,
  TripRequestPayload,
  TripSaveResponse,
  WeatherForecastResponse,
} from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

export async function generateTrip(payload: TripRequestPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/generate", payload);
  return response.data;
}

export async function searchLocations(
  keyword: string,
  city?: string,
  limit = 8
): Promise<LocationCandidate[]> {
  const response = await api.get<LocationCandidate[]>("/location/search", {
    params: { keyword, city, limit },
  });
  return response.data;
}

export async function reverseGeocodeLocation(
  longitude: number,
  latitude: number
): Promise<SelectedLocation> {
  const response = await api.get<SelectedLocation>("/location/reverse-geocode", {
    params: { longitude, latitude },
  });
  return response.data;
}

export async function generateDatePlan(payload: DatePlanRequestPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/date-plan/generate", payload);
  return response.data;
}

async function streamJsonLines<TPayload>(
  path: string,
  payload: TPayload,
  onEvent: (event: PlanningStreamEvent) => void,
  signal?: AbortSignal
): Promise<Itinerary> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Stream request failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Stream response body is unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finalItinerary: Itinerary | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const event = JSON.parse(trimmed) as PlanningStreamEvent;
      onEvent(event);
      if (event.type === "error") {
        throw new Error(event.content || event.title || "Streaming task failed.");
      }
      if (event.type === "complete" && event.itinerary) {
        finalItinerary = event.itinerary;
      }
    }
  }

  const trailing = buffer.trim();
  if (trailing) {
    const event = JSON.parse(trailing) as PlanningStreamEvent;
    onEvent(event);
    if (event.type === "error") {
      throw new Error(event.content || event.title || "Streaming task failed.");
    }
    if (event.type === "complete" && event.itinerary) {
      finalItinerary = event.itinerary;
    }
  }

  if (!finalItinerary) {
    throw new Error("Streaming task ended without a final itinerary.");
  }
  return finalItinerary;
}

export async function streamDatePlan(
  payload: DatePlanRequestPayload,
  onEvent: (event: PlanningStreamEvent) => void,
  signal?: AbortSignal
): Promise<Itinerary> {
  return streamJsonLines("/date-plan/generate/stream", payload, onEvent, signal);
}

export async function editTrip(payload: TripEditPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/edit", payload);
  return response.data;
}

export async function streamTripEdit(
  payload: TripEditPayload,
  onEvent: (event: PlanningStreamEvent) => void,
  signal?: AbortSignal
): Promise<Itinerary> {
  return streamJsonLines("/trip/edit/stream", payload, onEvent, signal);
}

export async function saveTrip(itinerary: Itinerary): Promise<TripSaveResponse> {
  const response = await api.post<TripSaveResponse>("/trip/save", {
    trip_id: itinerary.trip_id,
    itinerary,
    user_id: "frontend_demo_user",
  });
  return response.data;
}

export async function listTrips(): Promise<TripListResponse> {
  const response = await api.get<TripListResponse>("/trip");
  return response.data;
}

export async function getTripDetail(tripId: string): Promise<TripDetailResponse> {
  const response = await api.get<TripDetailResponse>(`/trip/${tripId}`);
  return response.data;
}

export async function deleteTrip(tripId: string): Promise<void> {
  await api.delete(`/trip/${tripId}`);
}

export async function fetchWeatherForecast(city: string): Promise<WeatherForecastResponse> {
  const response = await api.get<WeatherForecastResponse>("/weather/forecast", {
    params: { city },
  });
  return response.data;
}

export function getMarkdownExportUrl(tripId: string): string {
  return `${API_BASE_URL}/export/${encodeURIComponent(tripId)}/markdown`;
}

export function getPdfExportUrl(tripId: string): string {
  return `${API_BASE_URL}/export/${encodeURIComponent(tripId)}/pdf`;
}

export default api;
