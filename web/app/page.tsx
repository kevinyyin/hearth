"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import BuildingPanel from "@/components/BuildingPanel";
import PatientPanel from "@/components/PatientPanel";
import TimeSlider from "@/components/TimeSlider";
import { getJson } from "@/lib/api";
import { countByState, PLAN_STATES, stateColor } from "@/lib/snapshots";
import type { HearthEvent, Meta, PlanState, Run, Snapshot } from "@/lib/types";

// MapLibre touches `window` on import, so it must not render on the server.
const PatientMap = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => <div className="h-full w-full" style={{ background: "var(--surface-0)" }} />,
});

/** How far ahead to fetch, so scrubbing does not stall on the next tick. */
const PRELOAD = 10;

export default function HomePage() {
  const [run, setRun] = useState<Run | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [events, setEvents] = useState<HearthEvent[]>([]);
  const [index, setIndex] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isolated, setIsolated] = useState<PlanState | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const cache = useRef(new Map<number, Snapshot>());
  const inFlight = useRef(new Map<number, Promise<Snapshot>>());

  const fetchSnapshot = useCallback(
    (runId: string, i: number): Promise<Snapshot> => {
      const hit = cache.current.get(i);
      if (hit) return Promise.resolve(hit);

      const pending = inFlight.current.get(i);
      if (pending) return pending;

      const p = getJson<Snapshot>(`/api/runs/${runId}/snapshots/${i}`)
        .then((snap) => {
          cache.current.set(i, snap);
          inFlight.current.delete(i);
          return snap;
        })
        .catch((e: unknown) => {
          inFlight.current.delete(i);
          throw e;
        });

      inFlight.current.set(i, p);
      return p;
    },
    [],
  );

  // Load the run, its meta and its events once.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const runs = await getJson<Run[]>("/api/runs");
        if (runs.length === 0) throw new Error("No runs available.");
        const first = runs[0];
        const [m, ev] = await Promise.all([
          getJson<Meta>(`/api/runs/${first.run_id}/meta`),
          getJson<HearthEvent[]>(`/api/runs/${first.run_id}/events`).catch(() => [] as HearthEvent[]),
        ]);
        if (cancelled) return;
        setRun(first);
        setMeta(m);
        setEvents(ev);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // Show the current tick, then warm the next ten in the background.
  useEffect(() => {
    if (!run || !meta) return;
    let cancelled = false;

    const cached = cache.current.get(index);
    if (cached) {
      setSnapshot(cached);
      setLoading(false);
    } else {
      setLoading(true);
      fetchSnapshot(run.run_id, index)
        .then((snap) => {
          if (!cancelled) {
            setSnapshot(snap);
            setLoading(false);
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
            setLoading(false);
          }
        });
    }

    const last = meta.ticks.length - 1;
    for (let i = index + 1; i <= Math.min(index + PRELOAD, last); i++) {
      // Missing ticks must not surface as an error; this is only warming the cache.
      void fetchSnapshot(run.run_id, i).catch(() => {});
    }

    return () => {
      cancelled = true;
    };
  }, [run, meta, index, fetchSnapshot]);

  const counts = useMemo(
    () => (snapshot ? countByState(snapshot) : null),
    [snapshot],
  );

  const selected = useMemo(
    () => snapshot?.patients.find((p) => p.id === selectedId) ?? null,
    [snapshot, selectedId],
  );

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-lg font-semibold">Could not load the run.</h1>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          {error}
        </p>
        <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
          With no <code>NEXT_PUBLIC_API</code> set the page reads the dev files under{" "}
          <code>public/dev/api/</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <header
        className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b px-5 py-3"
        style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
      >
        <h1 className="text-sm font-semibold">Hearth</h1>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {run ? `${run.scenario} · policy ${run.policy} · ${run.crews} crews · seed ${run.seed}` : "Loading the run…"}
        </p>
        <a
          href="/results"
          className="ml-auto text-xs underline underline-offset-2"
          style={{ color: "var(--text-secondary)" }}
        >
          Results
        </a>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {meta && (
            <PatientMap
              meta={meta}
              snapshot={snapshot}
              isolated={isolated}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}

          {/* Legend with a count per state for the current tick; hovering isolates one state. */}
          <div
            className="absolute top-3 left-3 rounded-lg border p-3 shadow-sm"
            style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
            onMouseLeave={() => setIsolated(null)}
          >
            <div className="mb-2 text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
              Patients by plan state
            </div>
            <ul className="space-y-1">
              {PLAN_STATES.map((state) => (
                <li key={state}>
                  <button
                    type="button"
                    onMouseEnter={() => setIsolated(state)}
                    onFocus={() => setIsolated(state)}
                    onBlur={() => setIsolated(null)}
                    className="flex w-full items-center gap-2 text-left text-xs transition-opacity"
                    style={{ opacity: isolated && isolated !== state ? 0.4 : 1 }}
                  >
                    <span
                      aria-hidden
                      className="inline-block size-2.5 shrink-0 rounded-full"
                      style={{
                        background: stateColor(state),
                        outline: state === "URGENT" ? "1.5px solid #0b0b0b" : undefined,
                      }}
                    />
                    <span className="flex-1" style={{ color: "var(--text-secondary)" }}>
                      {state.replace(/_/g, " ").toLowerCase()}
                    </span>
                    <span className="tnum font-medium">{counts?.[state] ?? "—"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {selected && (
          <aside
            className="w-[380px] shrink-0 overflow-y-auto border-l"
            style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
          >
            <PatientPanel
              patient={selected}
              events={events}
              onClose={() => setSelectedId(null)}
            />
            {selected.building_id && <BuildingPanel buildingId={selected.building_id} patientId={selected.id} />}
          </aside>
        )}
      </div>

      {meta && (
        <TimeSlider
          ticks={meta.ticks}
          index={index}
          onChange={setIndex}
          loading={loading}
        />
      )}
    </div>
  );
}
