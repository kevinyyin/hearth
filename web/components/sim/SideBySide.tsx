"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import HouseholdMap from "@/components/sim/HouseholdMap";
import {
  CREW_COUNT,
  HOUSEHOLDS,
  RUN_HOURS,
  STATIONS,
  count,
  outNow,
  tallyAt,
  toursBy,
  vehiclesAt,
  type HouseholdState,
  type SideKey,
} from "@/lib/simulation";

const STEP_MS = 1100;

const SWATCH: Record<HouseholdState, { fill: string; ring: boolean }> = {
  reached: { fill: "#0e7a54", ring: false },
  waiting: { fill: "#c4461a", ring: true },
  unaffected: { fill: "#b8b1a4", ring: false },
};

const STATE_LABEL: Record<HouseholdState, string> = {
  reached: "Reached",
  waiting: "Waiting for help",
  unaffected: "Not yet affected",
};

function Tally({ which, hour, time }: { which: SideKey; hour: number; time: number }) {
  const t = tallyAt(hour, which);
  return (
    <dl className="mt-3 grid grid-cols-4 gap-3">
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
          Deployments
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold">{count.format(toursBy(time, which))}</dd>
      </div>
      <div>
        <dt className="text-xs" style={{ color: "var(--text-muted)" }}>
          Crews out
        </dt>
        <dd className="tnum m-0 text-2xl font-semibold">
          {count.format(outNow(time, which))}
          <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>
            /{CREW_COUNT}
          </span>
        </dd>
      </div>
    </dl>
  );
}

export default function SideBySide() {
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

  const start = () => {
    setHour(0);
    setProgress(0);
    setRunning(true);
  };

  const time = hour + (running ? progress : 0);
  const endHearth = tallyAt(RUN_HOURS, "hearthAt");
  const endToday = tallyAt(RUN_HOURS, "todayAt");
  const toursHearth = toursBy(RUN_HOURS + 1, "hearthAt");
  const toursToday = toursBy(RUN_HOURS + 1, "todayAt");

  return (
    <section
      className="rounded-xl border p-5"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold">Side by side, over one outage</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Harris County, the ground Beryl crossed. One dot is one household; dark dots are crews
            running a round from one of {STATIONS.length} stations and back. Both sides field the
            same {CREW_COUNT} crews. The maps pan and zoom together.
          </p>
        </div>

        <p className="tnum text-sm" style={{ color: "var(--text-secondary)" }}>
          Hour {hour} of {RUN_HOURS}
        </p>
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

      <div className="grid gap-7 lg:grid-cols-2">
        <figure className="m-0">
          <figcaption className="mb-0.5 text-sm font-semibold">With Hearth</figcaption>
          <p className="mb-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
            Knows who needs help, so a crew plans a round
          </p>
          <HouseholdMap
            which="hearthAt"
            hour={hour}
            vehicles={running ? vehiclesAt(time, "hearthAt") : []}
            onMap={register("a")}
            ariaLabel={`With Hearth at hour ${hour}: ${tallyAt(hour, "hearthAt").reached} of ${HOUSEHOLDS.length} households reached.`}
          />
          <Tally which="hearthAt" hour={hour} time={time} />
        </figure>

        <figure className="m-0">
          <figcaption className="mb-0.5 text-sm font-semibold">Today</figcaption>
          <p className="mb-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
            Finds out when the call reaches the front of the queue
          </p>
          <HouseholdMap
            which="todayAt"
            hour={hour}
            vehicles={running ? vehiclesAt(time, "todayAt") : []}
            onMap={register("b")}
            ariaLabel={`Today at hour ${hour}: ${tallyAt(hour, "todayAt").reached} of ${HOUSEHOLDS.length} households reached.`}
          />
          <Tally which="todayAt" hour={hour} time={time} />
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
          a single address and straight back — {toursToday} deployments, {endToday.reached}{" "}
          households.
        </p>
        <p className="m-0">
          <strong style={{ color: "var(--text-primary)" }}>The lever, stated plainly:</strong> the
          right-hand side learns of about two households an hour, because a call has to reach the
          front of a queue; the left-hand side knows all {HOUSEHOLDS.length} the moment their power
          goes. That rate is an assumption, not a measurement, and almost the whole gap above rests
          on it — argue with that number and you are arguing with the panel. It is also why the
          right-hand crews are idle rather than slow: they are not being outrun, they are waiting to
          be told where to go.
        </p>
        <p className="m-0">
          <strong style={{ color: "var(--text-primary)" }}>
            {endHearth.waiting === 0
              ? "Clearing the county here is a result of these numbers, not a property of Hearth."
              : "Hearth does not reach everyone either."}
          </strong>{" "}
          {endHearth.waiting === 0
            ? `${CREW_COUNT} crews is enough for ${HOUSEHOLDS.length} households in twelve hours. Raise the demand, cut the crews or shorten the window and the right-hand picture is what both sides look like — nothing here says the fleet is always big enough.`
            : `${endHearth.waiting} households are still waiting when the twelve hours close, because crews are finite.`}
        </p>
        <p className="m-0">
          <strong style={{ color: "var(--text-primary)" }}>
            The county is real; these {HOUSEHOLDS.length} households are drawn, not replayed.
          </strong>{" "}
          The simulation in this repository reports patient-hours at risk and has never modelled
          crews, stations or a call queue, so no run produces these dots.
        </p>
      </div>
    </section>
  );
}
