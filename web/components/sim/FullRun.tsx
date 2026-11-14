"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import HouseholdMap from "@/components/sim/HouseholdMap";
import SourceBadge from "@/components/sim/SourceBadge";
import { useCountyFeed } from "@/lib/simSource";
import {
  CREW_COUNT,
  RUN_HOURS,
  STATIONS,
  count,
  type CountySim,
  type SideKey,
  type SimEvent,
} from "@/lib/simulation";

const STEP_MS = 1400;

const KIND_STYLE: Record<SimEvent["kind"], { dot: string; label: string }> = {
  call: { dot: "#2a78d6", label: "call" },
  dispatch: { dot: "#a8441a", label: "dispatch" },
  arrive: { dot: "#0e7a54", label: "arrived" },
};

function Log({
  title,
  subtitle,
  events,
  backlog,
  backlogLabel,
}: {
  title: string;
  subtitle: string;
  events: SimEvent[];
  backlog: number | null;
  backlogLabel: string;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);

  // scroll the log itself, never the page
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  return (
    <div
      className="flex h-[220px] flex-col overflow-hidden rounded-xl border"
      style={{ background: "var(--surface-0)", borderColor: "var(--border)" }}
    >
      <div
        className="flex shrink-0 items-baseline gap-2 border-b px-3 py-2"
        style={{ borderColor: "var(--border)" }}
      >
        <h4 className="text-xs font-semibold">{title}</h4>
        <p className="flex-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
          {subtitle}
        </p>
        {backlog != null && (
          <span
            className="tnum rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={
              backlog > 0
                ? { background: "#f6e0d6", color: "#7a2e12" }
                : { background: "#def0e6", color: "#0b5c3e" }
            }
          >
            {count.format(backlog)} {backlogLabel}
          </span>
        )}
      </div>

      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2">
        {events.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Nothing yet.
          </p>
        ) : (
          <ul className="m-0 list-none space-y-1.5 p-0">
            {events.map((e, i) => (
              <li key={`${e.t}-${i}`} className="flex items-start gap-2 text-xs leading-snug">
                <span
                  aria-hidden="true"
                  className="mt-1 inline-block size-1.5 shrink-0 rounded-full"
                  style={{ background: KIND_STYLE[e.kind].dot }}
                />
                <span className="tnum shrink-0" style={{ color: "var(--text-muted)" }}>
                  {e.t.toFixed(1)}h
                </span>
                <span style={{ color: "var(--text-secondary)" }}>{e.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Column({
  county,
  center,
  which,
  title,
  blurb,
  time,
  hour,
  running,
  onMap,
}: {
  county: CountySim;
  center: [number, number];
  which: SideKey;
  title: string;
  blurb: string;
  time: number;
  hour: number;
  running: boolean;
  onMap: (m: MapLibreMap | null) => void;
}) {
  const hearth = which === "hearthAt";
  const t = county.tallyAt(hour, which);
  const chained = Math.round(county.chainedShare(which) * 100);

  return (
    <section className="min-w-0">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-0.5 mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
        {blurb}
      </p>

      <Log
        title={hearth ? "Agent call log" : "Operator call log"}
        subtitle={hearth ? "many at once" : "one at a time"}
        events={county.logAt(time, which, 7, ["call"])}
        backlog={county.backlogAt(time, which)}
        backlogLabel="waiting to be heard"
      />

      <div className="mt-3">
        <Log
          title="Dispatch"
          subtitle={`${chained}% of rounds chained`}
          events={county.logAt(time, which, 9, ["dispatch", "arrive"])}
          backlog={null}
          backlogLabel=""
        />
      </div>

      <div className="mt-3">
        <HouseholdMap
          county={county}
          center={center}
          which={which}
          hour={hour}
          vehicles={running ? county.vehiclesAt(time, which) : []}
          height={260}
          onMap={onMap}
          ariaLabel={`${title} at hour ${hour}: ${t.reached} reached, ${t.waiting} waiting.`}
        />
      </div>

      <dl className="mt-3 grid grid-cols-4 gap-2">
        <div>
          <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Reached
          </dt>
          <dd className="tnum m-0 text-xl font-semibold" style={{ color: "#0e7a54" }}>
            {count.format(t.reached)}
          </dd>
        </div>
        <div>
          <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Waiting
          </dt>
          <dd className="tnum m-0 text-xl font-semibold" style={{ color: "#c4461a" }}>
            {count.format(t.waiting)}
          </dd>
        </div>
        <div>
          <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Rounds
          </dt>
          <dd className="tnum m-0 text-xl font-semibold">
            {count.format(county.toursBy(time, which))}
          </dd>
        </div>
        <div>
          <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Out now
          </dt>
          <dd className="tnum m-0 text-xl font-semibold">
            {count.format(county.outNow(time, which))}
            <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>
              /{CREW_COUNT}
            </span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

/** Stage 3: the whole county, both ways at once, with the logs that explain the gap. */
export default function FullRun() {
  const feed = useCountyFeed();
  const { county, center } = feed;

  const [hour, setHour] = useState(0);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const raf = useRef<number | null>(null);
  const hourStart = useRef(0);

  const maps = useRef<{ a: MapLibreMap | null; b: MapLibreMap | null }>({ a: null, b: null });
  const syncing = useRef(false);

  const register = useCallback(
    (key: "a" | "b") => (m: MapLibreMap | null) => {
      maps.current[key] = m;
      if (!m) return;
      m.on("move", () => {
        if (syncing.current) return;
        const other = key === "a" ? maps.current.b : maps.current.a;
        if (!other) return;
        syncing.current = true;
        other.jumpTo({ center: m.getCenter(), zoom: m.getZoom() });
        syncing.current = false;
      });
    },
    [],
  );

  useEffect(() => {
    if (!running) return;
    hourStart.current = performance.now();

    timer.current = setInterval(() => {
      hourStart.current = performance.now();
      setHour((h) => {
        if (h >= RUN_HOURS) {
          setRunning(false);
          return h;
        }
        return h + 1;
      });
    }, STEP_MS);

    const tick = () => {
      setProgress(Math.min((performance.now() - hourStart.current) / STEP_MS, 1));
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);

    return () => {
      if (timer.current) clearInterval(timer.current);
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [running]);

  useEffect(() => {
    setHour(0);
    setProgress(0);
    setRunning(false);
  }, [county]);

  const time = hour + (running ? progress : 0);

  return (
    <section
      className="rounded-xl border p-5"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold">The whole county, both ways at once</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Same {CREW_COUNT} crews out of {STATIONS.length} stations, same speed. Watch where the
            calls come from and how far a van gets before it turns round.
          </p>
        </div>
        <p className="tnum text-sm" style={{ color: "var(--text-secondary)" }}>
          Hour {hour} of {RUN_HOURS}
        </p>
        <button
          type="button"
          onClick={() => {
            setHour(0);
            setProgress(0);
            setRunning(true);
          }}
          disabled={running}
          className="rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
          style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
        >
          {running ? "Running…" : hour > 0 ? "Run again" : "Run the full simulation"}
        </button>
      </div>

      <SourceBadge
        source={feed.source}
        detail={feed.detail}
        error={feed.error}
        className="mb-4"
      />

      <div
        className="mb-5 h-1 w-full overflow-hidden rounded-full"
        style={{ background: "var(--border)" }}
        role="presentation"
      >
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-linear"
          style={{ width: `${(hour / RUN_HOURS) * 100}%`, background: "var(--accent, #a8441a)" }}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Column
          county={county}
          center={center}
          which="hearthAt"
          title="Hearth"
          blurb="Calls out in parallel from the registry, then chains nearby stops into one round"
          time={time}
          hour={hour}
          running={running}
          onMap={register("a")}
        />
        <Column
          county={county}
          center={center}
          which="todayAt"
          title="Today"
          blurb="Waits for people to get through, then sends a van to the one address that called"
          time={time}
          hour={hour}
          running={running}
          onMap={register("b")}
        />
      </div>

      <p
        className="mt-5 rounded-lg border px-4 py-3 text-xs leading-relaxed"
        style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
      >
        <strong style={{ color: "var(--text-primary)" }}>Same fleet, different information.</strong>{" "}
        The call logs are where the two sides part: on the left the agent works the registry in
        parallel, so every crew has a round to drive; on the right households queue to be heard, and
        a van is sent to whoever reached the front. The queue rate and the crew model are this
        panel&rsquo;s assumptions, not results from the repository.
      </p>
    </section>
  );
}
