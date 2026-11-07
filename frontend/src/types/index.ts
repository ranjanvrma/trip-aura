// Mirrors backend/app/schemas. Keep in sync when the API changes.

export type DataSource =
  | "google" | "mock" | "estimate" | "user"
  | "open_data" | "osm" | "overture" | "wikidata" | "wikivoyage";
export type Pace = "relaxed" | "moderate" | "packed";
export type TransportMode = "walking" | "metro" | "bus" | "train" | "cab" | "auto" | "personal_vehicle";
export type ItemType = "start" | "activity" | "meal" | "rest" | "travel" | "end";

export interface LatLng { lat: number; lng: number }

export interface Money {
  amount: number;
  currency: string;
  verified: boolean;
  source: DataSource;
  note?: string | null;
}

export interface TimeRange { open: string; close: string }
export interface OpeningHours { known: boolean; weekly: Record<string, TimeRange[]>; source: DataSource }

export interface ExternalRating {
  provider: DataSource;
  rating: number | null;
  review_count: number | null;
  verified: boolean;
  label: string;
}

export interface SuitabilityScore {
  score: number;
  components: Record<string, number>;
  weights: Record<string, number>;
  reasons: string[];
  discovery: boolean;
}

export interface Review { text: string; rating?: number | null; source: DataSource }

export interface DietInfo {
  vegetarian_only: boolean; vegetarian_options: boolean; vegan_options: boolean;
  jain_options: boolean; egg_options: boolean; non_veg: boolean; known: boolean; source: DataSource;
}

export interface Place {
  id: string;
  name: string;
  kind: "attraction" | "park" | "restaurant" | "cafe" | "accommodation" | "other";
  categories: string[];
  location: LatLng;
  address?: string | null;
  description?: string | null;
  external_rating?: ExternalRating | null;
  price_level?: number | null;
  entry_fee?: Money | null;
  avg_cost_per_person?: Money | null;
  typical_visit_minutes: number;
  opening_hours?: OpeningHours | null;
  is_famous: boolean;
  best_time: string[];
  diet?: DietInfo | null;
  food_categories: string[];
  cuisines: string[];
  reviews: Review[];
  google_maps_uri?: string | null;
  external_ids: Record<string, string>;
  prominence?: number | null;
  price_level_estimated?: boolean;
  source: DataSource;
}

export interface TransportOption {
  mode: TransportMode;
  distance_km: number;
  duration_min: number;
  cost: Money;
  practical: boolean;
  score: number;
  note?: string | null;
  traffic_aware: boolean;
  source: DataSource;
  polyline: LatLng[];
}

export interface TravelLeg {
  from_name: string;
  to_name: string;
  origin: LatLng;
  destination: LatLng;
  chosen: TransportOption;
  alternatives: TransportOption[];
  recommendation_reason: string;
}

export interface ItineraryItem {
  id: string;
  type: ItemType;
  period: string;
  start: string;
  end: string;
  duration_min: number;
  title: string;
  place?: Place | null;
  suitability?: SuitabilityScore | null;
  meal_type?: string | null;
  cost?: Money | null;
  travel?: TravelLeg | null;
  notes: string[];
}

export interface CategoryTotals { food: number; transport: number; attractions: number; accommodation: number }
export interface DayBudget {
  day_number: number; totals: CategoryTotals; total: number; verified_amount: number; estimated_amount: number;
}
export interface DayPlan {
  day_number: number; date: string; weekday: string; items: ItineraryItem[]; budget: DayBudget; warnings: string[];
}

export interface DishSuggestion {
  name: string;
  status: "popular" | "mentioned" | "guide" | "suggestion";
  evidence: string[];
  evidence_source?: DataSource | null;
  mention_count: number;
}

export interface FoodRecommendation {
  place: Place; suitability: SuitabilityScore; meal_types: string[]; dishes: DishSuggestion[]; diet_match: string[];
}

export interface BudgetSuggestion {
  kind: string; message: string; estimated_saving: number; item_id?: string | null; alternative_place_id?: string | null;
}

export interface BudgetSummary {
  currency: string; total_budget: number; planned_total: number; remaining: number; over_budget: boolean;
  by_category: CategoryTotals; per_day: DayBudget[]; verified_total: number; estimated_total: number;
  suggestions: BudgetSuggestion[]; applied_optimizations: string[]; notes: string[];
}

export interface AccommodationInput {
  type: string;
  name_or_address: string;
  location?: LatLng | null;
}

export interface TripRequest {
  accommodation: AccommodationInput;
  destination_city: string;
  start_date?: string | null;
  num_days: number;
  travelers: number;
  budget: number;
  currency: string;
  accommodation_cost_total: number;
  interests: string[];
  food_preferences: string[];
  food_categories: string[];
  transport_modes: TransportMode[];
  pace: Pace;
  return_to_accommodation: boolean;
  fit_to_budget: boolean;
}

export interface Itinerary {
  trip_id: number | null;
  data_source: DataSource;
  generated_at: string;
  request: TripRequest;
  accommodation: Place;
  days: DayPlan[];
  food_recommendations: FoodRecommendation[];
  popular_dishes: DishSuggestion[];
  budget: BudgetSummary;
  unscheduled: { place: Place; reason: string }[];
  warnings: string[];
  disclaimers: string[];
  attributions: string[];
  ai_summary?: string | null;
  ai_status: string;
}

export interface TripSummary {
  id: number; title: string; destination: string; num_days: number; data_source: string; created_at: string;
}

export interface ApiStatus {
  data_mode: "mock" | "open" | "live";
  google: { configured: boolean; active: boolean; role: string; services: Record<string, string> };
  open_data: { sources: string[]; routing: string; city_cache_days: number } | null;
  worldwide: boolean;
  ai: { enabled: boolean; configured: boolean; model: string };
  mock_city: string | null;
  problems: string[];
}

export interface ApiOptions {
  interests: string[]; food_preferences: string[]; food_categories: string[]; transport_modes: TransportMode[];
  paces: Pace[]; accommodation_types: string[]; currencies: string[];
}

export interface TransportAlert { kind: string; message: string; suggested_mode?: TransportMode | null }

export interface LiveProgress {
  next_item_id: string | null;
  next_place_name: string | null;
  next_location: LatLng | null;
  straight_line_km: number | null;
  options: TransportOption[];
  recommended: TransportOption | null;
  alerts: TransportAlert[];
  checked_at: string;
  data_source: string;
}

export interface CitySuggestion {
  id: number; name: string; region: string; country: string; country_code: string;
  lat: number; lng: number; population: number; display: string; query: string;
}

export interface AddressSuggestion { label: string; name: string; lat: number; lng: number; kind?: string | null }

export interface ParsedTrip {
  fields: Partial<Omit<TripRequest, "accommodation">> & { accommodation?: Partial<AccommodationInput> };
  understood: string[];
  notes: string[];
  city: CitySuggestion | null;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
