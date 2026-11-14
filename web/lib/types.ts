// Shapes returned by the Hearth API. Mirrored by the hand-written dev files in public/dev/.

export type SweepRow = {
  policy: string;
  crews: number;
  median: number;
  p5: number;
  p95: number;
  unweighted_median: number;
};

/** Policy ids in the order the results page shows them. */
export const POLICY_ORDER = ["p0", "p3", "p3__nobld", "p3__nomove", "p3__aid"] as const;

export type PolicyId = (typeof POLICY_ORDER)[number];

export const POLICY_LABELS: Record<PolicyId, string> = {
  p0: "Phone tree (today)",
  p3: "Hearth",
  p3__nobld: "Hearth without building data",
  p3__nomove: "Hearth without moves",
  p3__aid: "Hearth with supplier mutual aid",
};

/** The three policies drawn when the page loads; the other two are toggles. */
export const DEFAULT_POLICIES: PolicyId[] = ["p0", "p3", "p3__nobld"];

export const OPTIONAL_POLICIES: PolicyId[] = ["p3__nomove", "p3__aid"];

export function policyLabel(policy: string): string {
  return POLICY_LABELS[policy as PolicyId] ?? policy;
}

// --- Part 2 (map) shapes. Declared here so the API helper and the map share one source. ---

export type PlanState =
  | "NOT_AFFECTED"
  | "OWN_BACKUP"
  | "RESUPPLY"
  | "MOVE"
  | "MOVED"
  | "URGENT"
  | "UNREACHABLE"
  | "RESTORED";

export type PatientSnap = {
  id: string;
  lat: number;
  lon: number;
  device: string;
  state: PlanState;
  backup_hours: number;
  indoor_temp_c: number;
  unpowered: boolean;
  building_id: string | null;
};

export type Snapshot = {
  t: string;
  patients: PatientSnap[];
  crews: object[];
  depots: object[];
};

export type Run = {
  run_id: string;
  scenario: string;
  policy: string;
  crews: number;
  seed: number;
};

export type Meta = {
  ticks: string[];
  /** [lat, lon] — note the order; MapLibre wants [lon, lat]. */
  center: [number, number];
};

export type HearthEvent = {
  t: string;
  type: string;
  patient_id: string | null;
  data: object;
};

// --- Building agent shapes (mirrors hearth/contracts.py and api/main.py). ---

export type Sourced = { value: unknown; source: "costar" | "matterport" | "vexcel" | "default"; confidence: number };

export type Evidence = { field: string; layer: string; ref: string; note: string };

export const PROFILE_FIELDS = [
  "floors", "units", "year_built", "construction", "property_type", "elevator_count", "roof_tone",
  "tree_cover_fraction", "step_free_entrance", "entrance_steps", "stair_width_m", "min_door_width_m", "van_dropoff",
  "unit_type", "unit_rooms", "hallway_width_m", "interior_steps",
] as const;

export type BuildingProfile = { [K in (typeof PROFILE_FIELDS)[number]]: Sourced } & {
  building_id: string;
  address: string;
  heat_time_constant_h: number;
  cold_time_constant_h: number;
  layers_missing: string[];
  evidence: Evidence[];
  conflicts: string[];
  cached: boolean;
  error: string | null;
};

/** Two parts (design amendment Nov 13): getting to the door, and inside the scanned unit type. */
export type AccessBrief = {
  unit_type: string | null;
  to_door: string[];
  inside_unit: string[];
  frames: Evidence[];
  missing: string[];
};

export type BuildingDetail = {
  building_id: string;
  name: string | null;
  address: string;
  profile: BuildingProfile | null;
  brief: AccessBrief | null;
  layer_effects: Record<string, number> | null;
  hours_to_unsafe: number | null;
  embed_url: string | null;
  image_url: string;
};

export type TraceEvent = {
  seq: number;
  t: number;
  kind: "todo" | "subagent" | "tool" | "file" | "conflict" | "profile" | "interrupt" | "done";
  agent: string;
  text: string;
  data: Record<string, unknown>;
};

export type RefugeOption = { building_id: string; name: string; lat: number; lon: number; reasons: string[]; sources: string[]; score: number };

export type RefugeProposal = {
  proposal_id: string;
  patient_id: string;
  options: RefugeOption[];
  status: "pending" | "approved" | "rejected";
  reason: string | null;
  thread_id: string;
  call_id?: string;
  call_error?: string;
};
