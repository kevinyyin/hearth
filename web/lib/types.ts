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
  /** "fields": built from CoStar and Vexcel records with no agent survey; "agent": a live survey. */
  method?: "agent" | "fields";
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
  /** The building's real scan models; empty with fixtures or when CoStar lists none. */
  scan_ids: string[];
  scan_sdk_key: string | null;
};

// --- Home markup shapes (mirrors Patient and Home in hearth/contracts.py). ---

export type Patient = {
  patient_id: string;
  synthetic: true;
  lat: number;
  lon: number;
  zip: string;
  floor: number;
  device: string;
  device_detail: string;
  backup_hours_on_hand: number;
  use_rate: number;
  mobility: string;
  can_self_relocate: boolean;
  temp_sensitive: "heat" | "cold" | "both" | "none";
  risk_weight: number;
  supplier_id: string;
  building_id: string | null;
  phone_status: "verified" | "unverified" | "missing";
  profile_status: "complete" | "partial" | "none";
  phone: string | null;
};

export type Vec3 = { x: number; y: number; z: number };
export type OutsideKind = "park" | "entrance" | "blocked" | "route";
export type InsideKind = "machine" | "blocked" | "route";
export type SizeId = "shoebox" | "microwave" | "carry_on" | "mini_fridge" | "custom";

/** x and y are fractions of the aerial image's width and height. */
export type OutsidePin = { kind: OutsideKind; x: number; y: number };
/** A point on a surface in the scan's own frame, in metres. */
export type InsidePin = { kind: InsideKind; position: Vec3; normal: Vec3 };

export type Home = {
  patient_id: string;
  building_id: string;
  ok_without_h: number;
  /** The device as the resident names it. */
  device_name: string;
  /** Can the device leave with the person? null: not answered. */
  movable: boolean | null;
  /** No longer asked on the resident page; older saved homes may carry one. */
  backup_plan: string;
  /** null: not asked (a home registered by phone). */
  size: SizeId | null;
  /** Width, depth, height in cm; only for a custom size. */
  size_cm: [number, number, number] | null;
  /** The scan the resident says is laid out like their home; null: none of them. */
  scan_id: string | null;
  note: string;
  outside: OutsidePin[];
  inside: InsidePin[];
  /** Family or trusted people to reach as well. Shown to the responder, never messaged. */
  contacts: Person[];
  /** People who live with the resident and can help before a crew arrives. */
  helpers: Person[];
  /** What a caller said by phone; a home saved on the resident page keeps the defaults. */
  source: "web" | "phone";
  unit: string | null;
  complex_building: string | null;
  door: string;
  door_from_aerial: boolean;
  room: string;
  scan_room: string | null;
  has_elevator: boolean | null;
  mobility_asked: boolean;
  said_at: string | null;
};

/** Someone the resident names. Invented, like the resident. */
export type Person = { name: string; relation: string; phone: string; note: string };

export type HomeRow = { home: Home; patient: Patient; address: string };

/** Phone registrations, newest first, and registration calls that ended before anyone was registered. */
export type Registrations = {
  registered: { patient: Patient; home: Home; address: string | null; call_id: string | null; call_status: string | null }[];
  needs_person: { call_id: string; phone: string | null; facts: Record<string, unknown>; status: string; started_at: number | null }[];
};

export type Vehicle = "car" | "van" | "wheelchair_van" | "ambulance";
export type Equipment = "oxygen" | "power" | "wheelchair_lift" | "stretcher";
export type HelpState = "waiting" | "offered" | "accepted" | "at_door" | "riding" | "dropped_off" | "safe" | "handled";

/** A crew persona's setup. Mirrors Responder in hearth/contracts.py. */
export type Responder = {
  crew_id: string;
  base_building_id: string;
  lat: number;
  lon: number;
  vehicle: Vehicle;
  equipment: Equipment[];
  on_duty: boolean;
};

/** A resident's request for help, as crews and dispatchers see it. `reason` is a model's line and never reaches the resident. */
export type HelpRequest = {
  patient_id: string;
  state: HelpState;
  times: Partial<Record<HelpState, string>>;
  rank: number | null;
  reason: string;
  ranked_by: "model" | "rule" | null;
  blocked: string;
  declined_by: string[];
  refuge: RefugeOption | null;
  job: { job_id: string; org_id: string; status: string; eta: string | null } | null;
};

/** What the resident reads: fixed lines chosen by the API. The accepted line carries a {window} slot for local times. */
export type Tracker = {
  state: HelpState | null;
  steps: { text: string; at: string | null; done: boolean }[];
  window: [string, string] | null;
  refuge_note: string | null;
};

export type CrewJob = {
  crew: Responder | null;
  job: { request: HelpRequest; patient: Patient; home: Home | null; address: string | null; building_id: string | null; km: number } | null;
};

export type DispatchView = {
  requests: { request: HelpRequest; device: string; mobility: string; address: string | null }[];
  crews: { crew: Responder; patient_id: string | null }[];
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
  phone_call?: string | null;
};
