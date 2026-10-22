export interface Weather {
  temp_f: number
  feels_like_f: number | null
  humidity: number | null
  dew_point_f: number | null
  wind_mph: number | null
  condition: string
  weather_code: number | null
}

export interface Zones {
  light_sec: number
  moderate_sec: number
  vigorous_sec: number
  peak_sec: number
}

export interface Run {
  id: string
  date: string
  time: string
  local_datetime: string
  start_time: string
  distance_mi: number
  duration_sec: number | null
  duration_str: string | null
  pace_sec_mi: number | null
  pace_str: string | null
  avg_hr: number | null
  calories: number | null
  cadence_spm: number | null
  stride_cm: number | null
  elevation_gain_ft: number | null
  altitude_ft: number | null
  has_gps: boolean
  has_route: boolean
  has_hr: boolean
  has_splits: boolean
  start_lat: number | null
  start_lon: number | null
  start_bearing_deg: number | null
  heading: string | null
  location_inferred: boolean
  excluded_from_model: boolean
  n_comments: number
  zones: Zones
  weather: Weather | null
  group_id: number | null
  group_name: string | null
  same_direction: number | null
  source: string | null
}

export interface Split {
  index: number
  distance_mi: number
  cumulative_mi: number
  duration_sec: number | null
  pace_sec_mi: number | null
  pace_str: string | null
}

export interface LatLon {
  lat: number
  lon: number
  alt_m?: number | null
}

export interface RunComment {
  id: number
  body: string
  created_at: string
}

export interface RunDetail extends Run {
  comments: RunComment[]
  splits: Split[]
  hr: { sec: number; bpm: number }[]
  route: LatLon[]
  pace_curve: { sec: number; dist_mi: number; pace_sec_mi: number }[]
}

export interface Group {
  group_id: number
  name: string
  auto_name: string
  custom_name: string | null
  n_runs: number
  reference_id: string
  headings: string[]
  distance_range_mi: [number, number]
  median_distance_mi: number
  last_date: string
  member_ids: string[]
}

export interface GroupMember extends Run {
  overlap: number
  coverage_of_focus: number
  splits: Split[]
}

export interface GroupDetail {
  group: Group
  focus_id: string
  members: GroupMember[]
  reference_route: LatLon[]
  focus_route: LatLon[]
}

export interface FeatureRow {
  key: string
  label: string
  unit: string
  description: string
  active: boolean
  coef_sec_per_unit: number
  ci_low: number
  ci_high: number
  typical_swing_sec: number
  iqr: number
  baseline: number
  range: [number, number]
  observed: [number, number]
}

export interface TimelineRun {
  id: string
  date: string
  distance_mi: number
  actual_sec: number
  adjusted_sec: number
  smoothed_sec: number
  trend_sec: number
  predicted_sec: number
  adjustments: Record<string, number>
}

export interface ModelSummary {
  ok: boolean
  reason?: string
  variant: 'conditions' | 'effort'
  n_runs: number
  n_excluded: number
  alpha: number
  r2_in_sample: number
  r2_loo: number
  mae_loo_sec: number
  baseline: Record<string, number>
  baseline_pace_sec: number
  features: FeatureRow[]
  timeline: { runs: TimelineRun[]; trend_sec_per_month: number; trend_total_sec: number }
  last_run: Record<string, number>
}

export interface Prediction {
  ok: boolean
  reason?: string
  inputs: Record<string, number>
  pace_sec: number
  pace_str: string
  low_sec: number
  high_sec: number
  baseline_pace_sec: number
  contributions: Record<string, number>
  curves: Record<string, { x: number; pace_sec: number; observed: boolean }[]>
}

export interface Conditions {
  date: string
  local_hour: number
  temp_f: number | null
  humidity: number | null
  days_since_last_run: number | null
  recent_7d_miles: number
  elev_gain_ft_per_mi: number | null
  distance_mi: number | null
  location: { lat: number; lon: number } | null
}

export interface SyncStatus {
  running: boolean
  phase: string
  message: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  new_activities: number
  log: string[]
  last_sync: { started_at: string; finished_at: string | null; status: string; message: string; new_activities: number } | null
}

export interface AuthStatus {
  has_client: boolean
  has_refresh_token: boolean
}

export type Settings = Record<string, string>

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  runs: () => request<Run[]>('/api/runs'),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  setExcluded: (id: string, excluded: boolean) =>
    request<{ ok: boolean; excluded_from_model: boolean }>(`/api/runs/${id}/exclude`, { method: 'PUT', body: JSON.stringify({ excluded }) }),
  addComment: (id: string, body: string) => request<RunComment>(`/api/runs/${id}/comments`, { method: 'POST', body: JSON.stringify({ body }) }),
  deleteComment: (id: string, commentId: number) => request<{ ok: boolean }>(`/api/runs/${id}/comments/${commentId}`, { method: 'DELETE' }),
  groups: () => request<Group[]>('/api/groups'),
  group: (id: number, focus?: string) => request<GroupDetail>(`/api/groups/${id}${focus ? `?focus=${focus}` : ''}`),
  renameGroup: (id: number, name: string) => request<{ ok: boolean }>(`/api/groups/${id}/name`, { method: 'PUT', body: JSON.stringify({ name }) }),
  model: (variant: string) => request<ModelSummary>(`/api/model?variant=${variant}`),
  predict: (variant: string, inputs: Record<string, number>) =>
    request<Prediction>('/api/model/predict', { method: 'POST', body: JSON.stringify({ variant, inputs }) }),
  conditions: () => request<Conditions>('/api/conditions'),
  sync: (full = false) => request<SyncStatus & { started: boolean }>(`/api/sync?full=${full}`, { method: 'POST' }),
  syncStatus: () => request<SyncStatus>('/api/sync/status'),
  authStatus: () => request<AuthStatus>('/api/auth/status'),
  saveToken: (refresh_token: string) => request<{ ok: boolean }>('/api/auth/token', { method: 'POST', body: JSON.stringify({ refresh_token }) }),
  saveClient: (client_id: string, client_secret: string) =>
    request<{ ok: boolean }>('/api/auth/client', { method: 'POST', body: JSON.stringify({ client_id, client_secret }) }),
  settings: () => request<Settings>('/api/settings'),
  saveSettings: (s: Settings) => request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(s) }),
}
