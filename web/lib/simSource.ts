"use client";

// Where the simulation's data comes from.
//
// The CoStar kit, the Vexcel key and the Matterport token live on the API, never
// in this bundle — the web app only ever needs NEXT_PUBLIC_API pointing at it.
// That makes three environments the same code path:
//
//   laptop, no API        NEXT_PUBLIC_API unset   -> drawn fixture, labelled as such
//   teammate's machine    NEXT_PUBLIC_API=http://localhost:8000   -> the real replay
//   Vercel                NEXT_PUBLIC_API=https://<hearth-api>    -> the real replay
//
// Nothing here throws into the page: every call falls back to the fixture and
// reports which one it got, so a missing key degrades to a working demo rather
// than a blank screen.

import { useEffect, useState } from "react";
import { API, getJson } from "@/lib/api";
import {
  COUNTY_CENTER,
  FIXTURE_COUNTY,
  RUN_HOURS,
  buildCounty,
  type CountySim,
  type Household,
} from "@/lib/simulation";
import { RESIDENT, type SimResident } from "@/lib/simulation";

export type SourceKind = "fixture" | "api";

export type CountyFeed = {
  county: CountySim;
  center: [number, number];
  source: SourceKind;
  /** One line for the badge: what answered, and what it was. */
  detail: string;
};

export const FIXTURE_FEED: CountyFeed = {
  county: FIXTURE_COUNTY,
  center: COUNTY_CENTER,
  source: "fixture",
  detail: "Drawn households — no API configured",
};

/** Shapes we read. Declared here so this file does not depend on the shared types module. */
type RunRow = { run_id: string; policy?: string; crews?: number };
type Meta = { center: [number, number] }; // [lat, lon] from the API
type Snap = {
  patients: { lon: number; lat: number; backup_hours: number; unpowered: boolean }[];
};

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return (await res.json()) as T;
}

/**
 * A patient's hour of need is their own backup time: the real record already says
 * how long their device runs once the power stops, so the demand curve is theirs
 * rather than something this file invented.
 */
function toHousehold(p: Snap["patients"][number]): Household {
  const hours = Number.isFinite(p.backup_hours) ? p.backup_hours : 0;
  return {
    lon: p.lon,
    lat: p.lat,
    needsAt: Math.max(0, Math.min(RUN_HOURS, Math.floor(p.unpowered ? hours : hours + 1))),
    // a short battery is the one that runs down again inside the same day
    repeats: hours <= 6,
  };
}

/** Caps the population so a county replay does not put 23,000 circles on one map. */
const MAX_DOTS = 400;

export async function loadCounty(signal: AbortSignal): Promise<CountyFeed> {
  if (!API) return FIXTURE_FEED;

  const runs = await get<RunRow[]>("/api/runs", signal);
  if (!runs.length) throw new Error("the API has no runs");

  // prefer a Hearth run; any run is better than none
  const run = runs.find((r) => r.policy === "p3") ?? runs[0];
  const [meta, snap] = await Promise.all([
    get<Meta>(`/api/runs/${run.run_id}/meta`, signal),
    get<Snap>(`/api/runs/${run.run_id}/snapshots/0`, signal),
  ]);

  const patients = snap.patients ?? [];
  if (!patients.length) throw new Error("the first snapshot has no patients");

  // even stride, so thinning keeps the county's shape instead of one corner of it
  const stride = Math.max(1, Math.ceil(patients.length / MAX_DOTS));
  const households = patients.filter((_, i) => i % stride === 0).map(toHousehold);

  const [lat, lon] = meta.center; // the API sends [lat, lon]; MapLibre wants [lon, lat]
  return {
    county: buildCounty(households),
    center: [lon, lat],
    source: "api",
    detail: `${households.length} of ${patients.length} simulated patients from run ${run.run_id}`,
  };
}

/**
 * The fixture first, then the real replay if one answers. The panel is usable
 * from the first paint either way, which matters on a demo laptop.
 */
export function useCountyFeed(): CountyFeed & { error: string | null } {
  const [feed, setFeed] = useState<CountyFeed>(FIXTURE_FEED);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!API) return;
    const ac = new AbortController();
    loadCounty(ac.signal)
      .then((f) => {
        if (!ac.signal.aborted) setFeed(f);
      })
      .catch((e: unknown) => {
        if (ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => ac.abort();
  }, []);

  return { ...feed, error };
}

// --- The resident the simulation walks through ------------------------------

export type ResidentFeed = {
  resident: SimResident;
  source: SourceKind;
  detail: string;
  /** For the real building views: the id, and the resident's own markup as saved. */
  buildingId: string | null;
  /** The scan the resident picked, which is the one to open. */
  scanId: string | null;
  outside: import("@/lib/types").OutsidePin[];
  inside: import("@/lib/types").InsidePin[];
};

type DemoPatient = { patient_id: string; device?: string; building_id?: string | null };
type HomeDoc = {
  /** The building the resident actually chose. demo-patients often has none. */
  building_id?: string | null;
  /** The scan the resident said is laid out like their home. */
  scan_id?: string | null;
  outside?: import("@/lib/types").OutsidePin[];
  inside?: import("@/lib/types").InsidePin[];
};
type BuildingRec = {
  numStoriesAboveGrade?: number;
  propertyApartment?: { isWalkup?: boolean };
};

const FIXTURE_RESIDENT: ResidentFeed = {
  resident: RESIDENT,
  source: "fixture",
  detail: "Placeholder record — no API configured",
  // the dev fixture under public/dev/api/buildings, so the panels draw something
  buildingId: "B-SAMPLE",
  scanId: null,
  outside: [],
  inside: [],
};

/**
 * Pulls the parts of the record that really exist behind the API: the patient,
 * their own markup, and the CoStar facts for their building. Anything the kit
 * cannot supply (the call transcript, the room layout) stays the placeholder.
 */
export async function loadResident(signal: AbortSignal): Promise<ResidentFeed> {
  if (!API) return FIXTURE_RESIDENT;

  const patients = await get<DemoPatient[]>("/api/demo-patients", signal);
  const p = patients[0];
  if (!p) throw new Error("the API has no demo patients");

  const home = await get<HomeDoc | null>(`/api/patients/${p.patient_id}/home`, signal).catch(
    () => null,
  );

  let floor = RESIDENT.floor;
  let elevator = RESIDENT.elevator;
  let buildingLabel = RESIDENT.buildingLabel;

  // The home doc is the authority: demo-patients usually carries no building,
  // because the resident picks one on their own screen. This is how /resident
  // finds a scan, and reading it anywhere else was why these panels came up empty.
  const buildingId = home?.building_id ?? p.building_id ?? null;

  if (buildingId) {
    const b = await get<BuildingRec>(`/api/buildings/${buildingId}`, signal).catch(() => null);
    if (b) {
      floor = b.numStoriesAboveGrade ?? floor;
      elevator = b.propertyApartment?.isWalkup === true ? false : elevator;
      buildingLabel = `CoStar ${buildingId}`;
    }
  }

  // the crew-facing notes are the placeholder's; the pins themselves are the
  // resident's own, and go straight onto the aerial tile
  const pins = RESIDENT.pins;

  return {
    resident: {
      ...RESIDENT,
      id: p.patient_id,
      device: p.device ?? RESIDENT.device,
      buildingLabel,
      floor,
      elevator,
      pins: pins.length ? pins : RESIDENT.pins,
    },
    source: "api",
    detail: `Patient ${p.patient_id}${p.building_id ? `, building ${p.building_id}` : ""}`,
    buildingId,
    scanId: home?.scan_id ?? null,
    outside: home?.outside ?? [],
    inside: home?.inside ?? [],
  };
}

export function useResidentFeed(): ResidentFeed & { error: string | null } {
  const [feed, setFeed] = useState<ResidentFeed>(FIXTURE_RESIDENT);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!API) return;
    const ac = new AbortController();
    loadResident(ac.signal)
      .then((f) => {
        if (!ac.signal.aborted) setFeed(f);
      })
      .catch((e: unknown) => {
        if (ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => ac.abort();
  }, []);

  return { ...feed, error };
}

// --- Loaders any panel can use, on either source -----------------------------
//
// These go through getJson, which already falls back from `${API}${path}` to
// `/dev${path}.json`. With the fixtures under web/public/dev/api that means a
// panel built on them renders on a laptop with no API at all — which is the
// difference between a demo that degrades and one that shows an error box.

export type Feed<T> = { data: T | null; source: SourceKind; detail: string; error: string | null };

function useFeed<T>(path: string | null, describe: (d: T) => string): Feed<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!path) return;
    let live = true;
    setData(null);
    setError(null);
    getJson<T>(path)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, [path]);

  return {
    data,
    source: API ? "api" : "fixture",
    detail: data ? describe(data) : error ? "nothing answered" : "loading…",
    error,
  };
}

export type ReplayRun = { run_id: string; scenario?: string; policy?: string; crews?: number };
export type ReplayMeta = { ticks: string[]; center: [number, number] };
export type BuildingBrief = {
  building_id: string;
  name: string | null;
  address?: string;
  /** Vexcel's top-down tile, served by the API behind the password. */
  image_url?: string;
  /** Matterport models CoStar lists for this building. Empty with fixtures. */
  scan_ids?: string[];
  scan_sdk_key?: string | null;
  embed_url?: string | null;
};

/** The replays the API, or the dev fixtures, can serve. */
export function useRunsFeed(): Feed<ReplayRun[]> {
  return useFeed<ReplayRun[]>("/api/runs", (r) => `${r.length} run${r.length === 1 ? "" : "s"}`);
}

/** One replay's meta: its ticks, and the centre the map should open on. */
export function useReplayMeta(runId: string | null): Feed<ReplayMeta> {
  return useFeed<ReplayMeta>(
    runId ? `/api/runs/${runId}/meta` : null,
    (m) => `${m.ticks?.length ?? 0} ticks`,
  );
}

/** One tick of a replay. */
export function useSnapshotFeed(runId: string | null, i: number): Feed<unknown> {
  return useFeed<unknown>(runId ? `/api/runs/${runId}/snapshots/${i}` : null, () => `tick ${i}`);
}

/**
 * A building's detail: CoStar facts, the access brief once surveyed, scan ids.
 * Falls back to web/public/dev/api/buildings/<id>.json, so a building panel has
 * something to draw without the kit on the machine.
 */
export function useBuildingFeed(buildingId: string | null): Feed<BuildingBrief> {
  return useFeed<BuildingBrief>(
    buildingId ? `/api/buildings/${buildingId}` : null,
    (b) => b.name ?? b.building_id,
  );
}
