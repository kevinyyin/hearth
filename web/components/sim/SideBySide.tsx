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

const STEP_MS = 1100;

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
  waiting: "Waiting for help",
  resupply: "Needs a restock",
  restocked: "Restocked",
  unaffected: "Not yet affected",
};

function Tally({
  county,
  which,
  hour,
  time,
}: {
  county: CountySim;
  which: SideKey;
  hour: number;
  time: number;
}) {
  const t = county.tallyAt(time, which);
  return (
    <dl className="mt-3 grid grid-cols-5 gap-3">
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          Reached
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold" style={{ color: "#0e7a54" }}>
          {count.format(t.reached)}
        </dd>
      </div>
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          Waiting
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold" style={{ color: "#c4461a" }}>
          {count.format(t.waiting)}
        </dd>
      </div>
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          On hold
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold">
          {count.format(county.queueAt(time, which))}
        </dd>
      </div>
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          Deployments
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold">
          {count.format(county.toursBy(time, which))}
        </dd>
      </div>
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          Crews out
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold">
          {count.format(county.outNow(time, which))}
          <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>
            /{CREW_COUNT}
          </span>
        </dd>
      </div>
    </dl>
  );
}

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

/** What was heard and what was sent, under each map: the logs are where the two sides part. */
function Logs({ county, which, time }: { county: CountySim; which: SideKey; time: number }) {
  const hearth = which === "hearthAt";
  const [callsOpen, setCallsOpen] = useState(true);
  const [dispatchOpen, setDispatchOpen] = useState(true);

  const onHold = county.queueAt(time, which);
  const backlog = county.backlogAt(time, which);
  const chained = Math.round(county.chainedShare(which) * 100);

  return (
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
  );
}

export default function SideBySide() {
  const feed = useCountyFeed();
  const { county, center } = feed;

  const { time, hour, running, start, speed, setSpeed } = useRunClock(STEP_MS, county);

  const maps = useRef<{ a: MapLibreMap | null; b: MapLibreMap | null }>({ a: null, b: null });
  const syncing = useRef(false);

  const register = useCallback(
    (key: "a" | "b") => (m: MapLibreMap | null) => {
      maps.current[key] = m;
      if (!m) return;
      // wired map to map, so a drag moves both in the same frame rather than a state round trip
      m.on("move", () => {
        if (syncing.current) return;
        const other = key === "a" ? maps.current.b : maps.current.a;
        if (!other) return;
        syncing.current = true; // the echo from `other` lands inside this flag and is dropped
        other.jumpTo({
          center: m.getCenter(),
          zoom: m.getZoom(),
          bearing: m.getBearing(),
          pitch: m.getPitch(),
        });
        syncing.current = false;
      });
    },
    [],
  );

  const total = county.households.length;
  const endHearth = county.tallyAt(RUN_HOURS, "hearthAt");
  const endToday = county.tallyAt(RUN_HOURS, "todayAt");
  const toursHearth = county.toursBy(RUN_HOURS + 1, "hearthAt");
  const toursToday = county.toursBy(RUN_HOURS + 1, "todayAt");


  return (
    <section
      className="rounded-xl border p-5"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold">Side by side, over one outage</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            One dot is one household; dark dots are crews running a round from one of{" "}
            {STATIONS.length} stations and back. Both sides field the same {CREW_COUNT} crews. The
            maps pan and zoom together.
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
          {running ? "Running…" : hour > 0 ? "Run again" : "Run the side-by-side"}
        </button>
      </div>

      {/* which data answered, said plainly rather than left to be guessed */}
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
          className="h-full rounded-full"
          style={{ width: `${(time / RUN_HOURS) * 100}%`, background: "var(--accent, #a8441a)" }}
        />
      </div>

      <div className="grid gap-7 lg:grid-cols-2">
        <figure className="m-0">
          <figcaption className="mb-0.5 text-sm font-semibold">With Hearth</figcaption>
          <p className="mb-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
            Knows who needs help, so a crew plans a round
          </p>
          <HouseholdMap
            county={county}
            center={center}
            which="hearthAt"
            time={time}
            vehicles={running ? county.vehiclesAt(time, "hearthAt") : []}
            onMap={register("a")}
            ariaLabel={`With Hearth at hour ${hour}: ${county.tallyAt(hour, "hearthAt").reached} of ${total} households reached.`}
          />
          <Tally county={county} which="hearthAt" hour={hour} time={time} />
          <Logs county={county} which="hearthAt" time={time} />
        </figure>

        <figure className="m-0">
          <figcaption className="mb-0.5 text-sm font-semibold">Today</figcaption>
          <p className="mb-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
            Finds out when the call reaches the front of the queue
          </p>
          <HouseholdMap
            county={county}
            center={center}
            which="todayAt"
            time={time}
            vehicles={running ? county.vehiclesAt(time, "todayAt") : []}
            onMap={register("b")}
            ariaLabel={`Today at hour ${hour}: ${county.tallyAt(hour, "todayAt").reached} of ${total} households reached.`}
          />
          <Tally county={county} which="todayAt" hour={hour} time={time} />
          <Logs county={county} which="todayAt" time={time} />
        </figure>
      </div>

      <ul
        className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm"
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
        <li className="flex items-center gap-2">
          <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true">
            <circle r={3.4} fill="#3d382e" stroke="#fbf9f4" strokeWidth={1.2} />
          </svg>
          Crew out on a round
        </li>
      </ul>

      <div
        className="mt-5 space-y-2.5 rounded-lg border px-4 py-3 text-xs leading-relaxed"
        style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
      >
        <p className="m-0">
          <strong style={{ color: "var(--text-primary)" }}>
            Same vans, same speed, same time at the door.
          </strong>{" "}
          Both sides run {CREW_COUNT} crews out of {STATIONS.length} stations, and a van covers the
          same ground per hour on either map. One thing differs: whether the dispatcher already
          knows who needs help. With the registry every crew has somewhere useful to be and can
          chain four nearby stops into a round — {toursHearth} deployments, {endHearth.reached}{" "}
          households. Without it most vans have nowhere to go, and the one that moves drives out to
          a single address and almost always straight back — {toursToday} deployments,{" "}
          {endToday.reached} households.
        </p>
        <p className="m-0">
          <strong style={{ color: "var(--text-primary)" }}>The lever, stated plainly:</strong> the
          right-hand side learns of about six households an hour, because calls wait in one queue and{" "}
          {OPERATORS} operators take them in the order they rang; the left-hand side knows all {total} the moment their power goes. That
          rate is an assumption, not a measurement, and almost the whole gap above rests on it —
          argue with that number and you are arguing with the panel. It is also why the right-hand
          crews are idle rather than slow: they are not being outrun, they are waiting to be told
          where to go.
        </p>
      </div>
    </section>
  );
}
