"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import HouseholdMap from "@/components/sim/HouseholdMap";
import { SpeedControl, useRunClock } from "@/components/sim/RunClock";
import SourceBadge from "@/components/sim/SourceBadge";
import { useCountyFeed } from "@/lib/simSource";
import {
  CREW_COUNT,
  OPERATORS,
  RUN_HOURS,
  STATIONS,
  count,
  type CountySim,
  type HouseholdState,
  type SideKey,
  type SimEvent,
} from "@/lib/simulation";

/** Slow enough to talk over at 1×: a full day takes about a minute and a half. */
const STEP_MS = 3600;

const DOT: Record<SimEvent["kind"], string> = {
  call: "#2a78d6",
  dispatch: "#a8441a",
  arrive: "#0e7a54",
  restock: "#2a6fd6",
};

const SWATCH: Record<HouseholdState, { fill: string; ring: boolean }> = {
  reached: { fill: "#0e7a54", ring: false },
  waiting: { fill: "#c4461a", ring: true },
  resupply: { fill: "#2a6fd6", ring: false },
  restocked: { fill: "#9333a8", ring: false },
  unaffected: { fill: "#b8b1a4", ring: false },
};

const STATE_LABEL: Record<HouseholdState, string> = {
  reached: "Reached",
  waiting: "Waiting",
  resupply: "Needs a restock",
  restocked: "Restocked",
  unaffected: "Not yet affected",
};

/** A log that sits under its map and folds away to a single bar. */
function LogPanel({
  title,
  note,
  events,
  badge,
  badgeTone,
  open,
  onToggle,
}: {
  title: string;
  note: string;
  events: SimEvent[];
  badge?: string;
  badgeTone?: "warn" | "ok";
  open: boolean;
  onToggle: () => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [events.length, open]);

  return (
    <div
      className="flex min-w-0 flex-col overflow-hidden rounded-xl border"
      style={{ background: "var(--surface-0)", borderColor: "var(--border)" }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        style={{ minHeight: 40 }}
      >
        <span className="text-xs font-semibold">{title}</span>
        <span className="flex-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
          {note}
        </span>
        {badge && (
          <span
            className="tnum rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={
              badgeTone === "warn"
                ? { background: "#f6e0d6", color: "#7a2e12" }
                : { background: "#def0e6", color: "#0b5c3e" }
            }
          >
            {badge}
          </span>
        )}
        <span aria-hidden="true" className="text-xs" style={{ color: "var(--text-muted)" }}>
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div
          ref={listRef}
          className="max-h-40 overflow-y-auto overscroll-contain border-t px-3 py-2"
          style={{ borderColor: "var(--border)" }}
        >
          {events.length === 0 ? (
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              Nothing yet.
            </p>
          ) : (
            <ul className="m-0 list-none space-y-1 p-0">
              {events.map((e, i) => (
                <li key={`${e.t}-${i}`} className="flex items-start gap-2 text-[11px] leading-snug">
                  <span
                    aria-hidden="true"
                    className="mt-1 inline-block size-1.5 shrink-0 rounded-full"
                    style={{ background: DOT[e.kind] }}
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
      )}
    </div>
  );
}

function Side({
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
  const [callsOpen, setCallsOpen] = useState(true);
  const [dispatchOpen, setDispatchOpen] = useState(true);

  const t = county.tallyAt(time, which);
  const backlog = county.backlogAt(time, which);
  const onHold = county.queueAt(time, which);
  const chained = Math.round(county.chainedShare(which) * 100);

  return (
    <section className="flex min-w-0 flex-col">
      <div className="mb-2">
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {blurb}
        </p>
      </div>

      <HouseholdMap
        county={county}
        center={center}
        which={which}
        time={time}
        vehicles={running ? county.vehiclesAt(time, which) : []}
        height="min(44vh, 440px)"
        onMap={onMap}
        ariaLabel={`${title} at hour ${hour}: ${t.reached} reached, ${t.waiting} waiting, ${t.resupply} needing a restock.`}
      />

      {/* the two logs sit under their own map, side by side, so a column reads
          as one thing: the ground, then what was heard, then what was sent */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <LogPanel
          title={hearth ? "Agent calls" : "Operator calls"}
          note={hearth ? "in parallel" : "in order"}
          events={county.logAt(time, which, 20, ["call"])}
          badge={`${count.format(onHold)} on hold`}
          badgeTone={onHold > 0 ? "warn" : "ok"}
          open={callsOpen}
          onToggle={() => setCallsOpen((v) => !v)}
        />
        <LogPanel
          title="Dispatch"
          note={`${chained}% chained`}
          events={county.logAt(time, which, 20, ["dispatch", "arrive", "restock"])}
          badge={`${count.format(backlog)} open`}
          badgeTone={backlog > 0 ? "warn" : "ok"}
          open={dispatchOpen}
          onToggle={() => setDispatchOpen((v) => !v)}
        />
      </div>

      <dl className="mt-3 grid grid-cols-5 gap-2">
        {[
          ["Reached", count.format(t.reached), "#0e7a54"],
          ["Waiting", count.format(t.waiting), "#c4461a"],
          ["Need restock", count.format(t.resupply), "#2a6fd6"],
          ["Restocked", count.format(county.restocksBy(time, which)), undefined],
          ["Out now", `${county.outNow(time, which)}/${CREW_COUNT}`, undefined],
        ].map(([label, value, color]) => (
          <div key={label as string}>
            <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {label}
            </dt>
            <dd
              className="tnum m-0 text-xl font-semibold"
              style={color ? { color: color as string } : undefined}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Stage 3: the whole county, both ways at once, over a full day. */
export default function FullRun() {
  const feed = useCountyFeed();
  const { county, center } = feed;

  const { time, hour, running, start, speed, setSpeed } = useRunClock(STEP_MS, county);

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

  const restocksH = county.restocksBy(RUN_HOURS + 1, "hearthAt");
  const restocksT = county.restocksBy(RUN_HOURS + 1, "todayAt");

  return (
    <section
      className="rounded-xl border p-5"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold">The whole county, both ways, over a day</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Same {CREW_COUNT} crews out of {STATIONS.length} stations, same speed. A delivery only
            buys so many hours, so households that were helped turn blue when they need another.
          </p>
        </div>
        <p className="tnum text-sm" style={{ color: "var(--text-secondary)" }}>
          Hour {hour} of {RUN_HOURS}
        </p>
        <SpeedControl speed={speed} onChange={setSpeed} />
        <button
          type="button"
          onClick={start}
          disabled={running}
          className="rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
          style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
        >
          {running ? "Running…" : hour > 0 ? "Run again" : "Run the full simulation"}
        </button>
      </div>

      <SourceBadge source={feed.source} detail={feed.detail} error={feed.error} className="mb-4" />

      <div
        className="mb-5 h-1 w-full overflow-hidden rounded-full"
        style={{ background: "var(--border)" }}
        role="presentation"
      >
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-linear"
          style={{ width: `${(hour / RUN_HOURS) * 100}%`, background: "var(--accent, #a8441a)" }}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Side
          county={county}
          center={center}
          which="hearthAt"
          title="Hearth"
          blurb="Calls out in parallel, chains nearby stops, and sees a delivery run down"
          time={time}
          hour={hour}
          running={running}
          onMap={register("a")}
        />
        <Side
          county={county}
          center={center}
          which="todayAt"
          title="Today"
          blurb="Waits to be called, sends one van, and has to be told again when it runs down"
          time={time}
          hour={hour}
          running={running}
          onMap={register("b")}
        />
      </div>

      <ul
        className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        {(Object.keys(STATE_LABEL) as HouseholdState[]).map((k) => (
          <li key={k} className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true">
              {SWATCH[k].ring ? (
                <circle r={4} fill="none" stroke={SWATCH[k].fill} strokeWidth={1.8} />
              ) : (
                <circle r={k === "unaffected" ? 2.6 : 4.4} fill={SWATCH[k].fill} />
              )}
            </svg>
            {STATE_LABEL[k]}
          </li>
        ))}
      </ul>

      <p
        className="mt-5 rounded-lg border px-4 py-3 text-xs leading-relaxed"
        style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
      >
        <strong style={{ color: "var(--text-primary)" }}>Same fleet, different information.</strong>{" "}
        The call logs are where the two part: on the left the agent works the registry in parallel,
        so every crew has a round to drive; on the right households queue to be heard, {OPERATORS} operators
        taking calls in the order they rang, and every free van goes to whoever reached the front. Over a full day that gap compounds, because a delivery runs
        down — {restocksH} restocks were made on the left against {restocksT} on the right, and a
        blue dot is someone who was already helped once. The queue rate, the crew model and how long
        a delivery lasts are this panel&rsquo;s assumptions, not results from the repository.
      </p>
    </section>
  );
}
