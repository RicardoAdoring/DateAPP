export interface TripRequestPayload {
  destination: string;
  start_date: string;
  end_date: string;
  travelers: number;
  budget: number;
  preferences: string[];
  pace?: string | null;
  dietary_preferences: string[];
  hotel_level?: string | null;
  special_notes?: string | null;
}

export interface TripEditPayload {
  trip_id: string;
  current_itinerary: Itinerary;
  user_instruction: string;
  edit_scope?: string | null;
  preserve_constraints: string[];
}

export interface SpotItem {
  name: string;
  start_time?: string | null;
  end_time?: string | null;
  description?: string | null;
  estimated_cost?: number;
  location?: string | null;
  image_url?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  poi_id?: string | null;
}

export interface MealItem {
  name: string;
  meal_type: string;
  estimated_cost?: number;
  notes?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  location?: string | null;
  image_url?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  poi_id?: string | null;
}

export interface HotelItem {
  name: string;
  level?: string | null;
  estimated_cost?: number;
  location?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface TransportItem {
  mode: string;
  from_place?: string | null;
  to_place?: string | null;
  estimated_cost?: number;
  duration?: string | null;
  distance_km?: number | null;
  estimated_minutes?: number | null;
}

export interface DayPlan {
  day_index: number;
  date?: string | null;
  theme?: string | null;
  spots: SpotItem[];
  meals: MealItem[];
  hotel?: HotelItem | null;
  transport: TransportItem[];
  notes: string[];
}

export interface BudgetBreakdown {
  transport: number;
  hotel: number;
  meals: number;
  tickets: number;
  other: number;
  total: number;
}

export interface Itinerary {
  trip_id: string;
  destination: string;
  summary: string;
  days: DayPlan[];
  estimated_budget: number;
  budget_breakdown: BudgetBreakdown;
  tips: string[];
  source_notes: string[];
  source_links?: PlanSource[];
}

export interface SelectedLocation {
  name?: string | null;
  address?: string | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  latitude: number;
  longitude: number;
  poi_id?: string | null;
}

export interface LocationCandidate {
  name: string;
  address?: string | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  type?: string | null;
  poi_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_url?: string | null;
  distance_meters?: number | null;
}

export interface PlanSource {
  title: string;
  url?: string | null;
  snippet?: string | null;
  source: string;
}

export interface DatePlanRequestPayload {
  anchor: SelectedLocation;
  date: string;
  start_time: string;
  end_time: string;
  travelers: number;
  budget: number;
  preferences: string[];
  dietary_preferences: string[];
  transport_mode: string;
  radius_meters: number;
  special_notes?: string | null;
}

export type StreamEventType = "stage" | "thought" | "plan_item" | "route" | "complete" | "error";

export interface PlanningStreamEvent {
  type: StreamEventType;
  title?: string;
  content?: string;
  data?: Record<string, unknown> | null;
  itinerary?: Itinerary;
}

export interface PlanStreamRun {
  id: number;
  mode: "generate" | "edit";
  payload: DatePlanRequestPayload | TripEditPayload;
  title: string;
  subtitle?: string;
}

export interface TripSaveResponse {
  message: string;
  trip_id: string;
}

export interface TripSummaryItem {
  trip_id: string;
  destination: string;
  summary: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TripListResponse {
  total: number;
  items: TripSummaryItem[];
}

export interface TripDetailResponse {
  trip_id: string;
  itinerary: Itinerary;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WeatherForecastDay {
  date?: string | null;
  week?: string | null;
  day_weather?: string | null;
  night_weather?: string | null;
  day_temp?: string | null;
  night_temp?: string | null;
  day_wind?: string | null;
  night_wind?: string | null;
}

export interface WeatherForecastResponse {
  city: string;
  province?: string | null;
  adcode?: string | null;
  report_time?: string | null;
  days: WeatherForecastDay[];
}
