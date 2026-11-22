// apiClient.ts - drop into the CrowdWise frontend (e.g. src/api/apiClient.ts).
// Talks to the Python backend described in docs/API_CONTRACT.md.
//
// Setup:  .env  ->  VITE_API_BASE_URL=http://localhost:8000      (or leave empty and use the Vite proxy, see vite.proxy.snippet.ts)

export type CrowdTier = 'seats_available' | 'standing_room' | 'crowded' | 'unknown';
export type Confidence = 'high' | 'medium' | 'low';
export type PredictionSource = 'observed_tickets' | 'ml_fallback' | 'route_average';
export type DayType = 'weekday' | 'weekend';

export interface StopHit { stop_id: string; stop_name: string; lat: number; lng: number; routes_count: number; sample_routes: string[]; match_score: number }
export interface PlanLeg {
  route_id: string; route_short_name: string; from_stop: { stop_id: string; stop_name: string; lat: number; lng: number }; to_stop: { stop_id: string; stop_name: string; lat: number; lng: number };
  departure_time: string; arrival_time: string; ride_min: number; wait_min: number; num_stops: number; is_ac: boolean;
  max_crowd_level: CrowdTier; max_load_ratio: number | null; avg_load_ratio: number | null; ticket_count: number; confidence: Confidence; prediction_source: PredictionSource;
  path: [number, number][]; stop_sequence: string[];
}
export interface PlanOption {
  option_id: string; rank: number; tag: 'fastest' | 'most_comfortable' | 'balanced' | 'alternative';
  total_duration_min: number; in_vehicle_min: number; wait_min: number; walk_min: number; transfers: number;
  max_crowd_level: CrowdTier; avg_crowd_level: CrowdTier; max_load_ratio: number | null; avg_load_ratio: number | null;
  confidence: Confidence; prediction_source: PredictionSource; ticket_count: number; legs: PlanLeg[];
}
export interface DepartureShift { shift_minutes: number; departure_time: string; improves_crowding: boolean; previous_crowd_level: CrowdTier; new_crowd_level: CrowdTier; load_ratio_delta: number; summary: string }
/** One row per route-direction from GET /api/routes/summary (busiest qualifying stretch; terminal hops ignored). 'unknown' rows have null load/stretch and confidence 'low'. */
export interface RouteSummaryRow {
  route_id: string; route_short_name: string; direction_id: number; direction: 'Up' | 'Down' | null; route_long_name: string;
  busiest_stretch: string | null; load_ratio_raw: number | null; load_pct: number | null;   // load_pct is capped at 100, load_ratio_raw is not
  crowd_level: CrowdTier; confidence: Confidence; prediction_source: PredictionSource; ticket_count: number; scheduled_buses_hr: number;
}
export interface RoutesSummaryResponse { day_type: DayType; hour: number; count: number; routes: RouteSummaryRow[] }
export interface PlanResponse { query: Record<string, unknown>; resolved_origin: StopHit & { match_method: string }; resolved_destination: StopHit & { match_method: string }; options: PlanOption[]; departure_shifts: DepartureShift[]; note: string | null }

const BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? '';

/** fetch + JSON + timeout (bug fix 3: no request may hang forever). Throws an Error with the backend's message. */
export async function fetchJson<T>(path: string, params: Record<string, string | number | undefined> = {}, timeoutMs = 15000): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)])).toString();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`, { signal: ctrl.signal, headers: { Accept: 'application/json' } });
    const type = res.headers.get('content-type') ?? '';
    if (!type.includes('application/json')) throw new Error(`Backend not reachable at "${BASE || window.location.origin}" (got ${type || 'no content type'} instead of JSON). Is the Python API running?`);
    const body = await res.json();
    if (!res.ok) throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
    return body as T;
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new Error(`Request timed out after ${timeoutMs / 1000}s: ${path}`);
    throw e;
  } finally { clearTimeout(timer); }
}

export const api = {
  health: () => fetchJson<any>('/api/health'),
  stops: (q: string, limit = 15) => q.trim() ? fetchJson<{ stops: StopHit[] }>('/api/stops', { q: q.trim(), limit }) : Promise.resolve({ stops: [] as StopHit[] }),   // bug fix 2: empty text -> no call
  plan: (origin: string, destination: string, time: string, day_type: DayType, preference: 'balanced' | 'fastest' | 'comfortable' = 'balanced') =>
    fetchJson<PlanResponse>('/api/plan', { origin, destination, time, day_type, preference }),
  routes: (q = '', limit = 100, offset = 0) => fetchJson<any>('/api/routes', { q, limit, offset }),
  routeCrowd: (routeId: string, day_type: DayType, hour: number) => fetchJson<any>(`/api/routes/${encodeURIComponent(routeId)}/crowd`, { day_type, hour }),
  hotspots: (day_type: DayType, hour: number | 'all', limit = 20, min_confidence: Confidence = 'medium') => fetchJson<any>('/api/operator/hotspots', { day_type, hour, limit, min_confidence }),
  routesSummary: (day_type: DayType, hour: number) => fetchJson<RoutesSummaryResponse>('/api/routes/summary', { day_type, hour }),
  networkProfile: (day_type: DayType) => fetchJson<any>('/api/operator/network-profile', { day_type }),
  validation: () => fetchJson<any>('/api/validation/summary'),
  mlInsights: () => fetchJson<any>('/api/ml/insights'),
};

/** Words for commuters. Use the API's crowd level directly - do NOT recompute it from the percentage. */
export const TIER_LABEL: Record<CrowdTier, string> = { seats_available: 'Seats available', standing_room: 'Standing room', crowded: 'Crowded', unknown: 'No data' };
export const SOURCE_LABEL: Record<PredictionSource, string> = { observed_tickets: 'Based on e-ticket data', ml_fallback: 'Model estimate (few tickets)', route_average: 'Route average (few tickets)' };
/** load ratio (0-1.5) -> a 0-100 bar width */
export const loadPct = (ratio: number | null) => (ratio == null ? 0 : Math.round(Math.min(ratio, 1) * 100));
