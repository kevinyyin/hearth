"use client";

import maplibregl, { type GeoJSONSource, type Map as MapLibreMap, type Marker } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { cumulative, LEGS, OBSTACLE_STYLE, pointAt } from "@/lib/routeSim";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
/** Demo pacing, not real drive times. */
const DRIVE_MS = 11000;
const TASK_MS = 3500;
const ASSIGN_MS = 2000;

type Phase = "driving" | "task" | "assign" | "done";

/** An EMS van from above, nose up, so the marker's rotation aims it along the road. */
const EMS_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="38" viewBox="0 0 34 58" aria-hidden="true">
  <rect x="3" y="2" width="28" height="54" rx="6" fill="#ffffff" stroke="#3d382e" stroke-width="2"/>
  <path d="M8 10 h18 v8 h-18 z" fill="#9fb3bd"/>
  <rect x="9" y="22" width="16" height="4" rx="1" fill="#c0262d"/><rect x="9" y="22" width="5" height="4" fill="#2a6fd6"/>
  <rect x="14" y="31" width="6" height="16" fill="#c0262d"/><rect x="9" y="36" width="16" height="6" fill="#c0262d"/>
</svg>`;

const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const line = (coords: [number, number][]): GeoJSON.Feature => ({
  type: "Feature",
  properties: {},
  geometry: { type: "LineString", coordinates: coords },
});

function pill(text: string, color: string, filled: boolean) {
  const el = document.createElement("div");
  el.textContent = text; // textContent: these labels will come from another lane's algorithm
  el.style.cssText = `font: 600 11px/1.2 system-ui, sans-serif; padding: 3px 7px; border-radius: 999px; white-space: nowrap;
    border: 1.5px solid ${color}; background: ${filled ? color : "#fff"}; color: ${filled ? "#fff" : color};
    box-shadow: 0 1px 3px rgba(0,0,0,.18)`;
  return el;
}

/**
 * The accepted job, driven: a van follows the road to the household, does the
 * task, takes the next assignment and goes again. Obstacles on each route are
 * labelled on the map and listed below it, so the map is never the only place
 * they are said.
 */
export default function RouteSim({ onArrive }: { onArrive: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const van = useRef<Marker | null>(null);
  const pins = useRef<Marker[]>([]);
  const onArriveRef = useRef(onArrive);
  onArriveRef.current = onArrive;

  const [ready, setReady] = useState(false);
  const [leg, setLeg] = useState(0);
  const [phase, setPhase] = useState<Phase>("driving");
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: LEGS[0].path[0],
      zoom: 14,
      interactive: false,
      attributionControl: false,
    });
    map.current = m;
    m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    m.on("load", () => {
      m.addSource("route", { type: "geojson", data: empty });
      m.addSource("driven", { type: "geojson", data: empty });
      m.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#3d382e", "line-width": 4, "line-opacity": 0.35, "line-dasharray": [1.5, 1.2] } });
      m.addLayer({ id: "driven", type: "line", source: "driven", layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#c0262d", "line-width": 5 } });
      const el = document.createElement("div");
      el.innerHTML = EMS_SVG;
      van.current = new maplibregl.Marker({ element: el, rotationAlignment: "map" }).setLngLat(LEGS[0].path[0]).addTo(m);
      container.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      setReady(true);
    });
    return () => {
      m.remove();
      map.current = null;
      van.current = null;
    };
  }, []);

  // one effect walks the loop: drive, do the task, take the next job
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const L = LEGS[leg];

    if (phase === "task") {
      const t = setTimeout(() => setPhase(leg < LEGS.length - 1 ? "assign" : "done"), TASK_MS);
      return () => clearTimeout(t);
    }
    if (phase === "assign") {
      const t = setTimeout(() => {
        setLeg(leg + 1);
        setPhase("driving");
      }, ASSIGN_MS);
      return () => clearTimeout(t);
    }
    if (phase !== "driving") return;

    // draw this leg: the road, its obstacles, the destination
    (m.getSource("route") as GeoJSONSource).setData(line(L.path));
    (m.getSource("driven") as GeoJSONSource).setData(empty);
    pins.current.forEach((p) => p.remove());
    pins.current = [
      ...L.obstacles.map((o) =>
        new maplibregl.Marker({ element: pill(`⚠ ${OBSTACLE_STYLE[o.kind].label}`, OBSTACLE_STYLE[o.kind].color, false) })
          .setLngLat(o.at).addTo(m)),
      new maplibregl.Marker({ element: pill(L.job.split(" · ")[0], "#0e7a54", true), anchor: "bottom", offset: [0, -6] })
        .setLngLat(L.path[L.path.length - 1]).addTo(m),
    ];
    const bounds = L.path.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(L.path[0], L.path[0]));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    m.fitBounds(bounds, { padding: 48, duration: reduce ? 0 : 900 });

    const cum = cumulative(L.path);
    const start = performance.now();
    let raf = 0;
    const frame = (now: number) => {
      const p = (now - start) / DRIVE_MS;
      const { at, bearing, passed } = pointAt(L.path, cum, p);
      van.current?.setLngLat(at).setRotation(bearing);
      (m.getSource("driven") as GeoJSONSource).setData(line([...L.path.slice(0, passed), at]));
      if (p < 1) raf = requestAnimationFrame(frame);
      else {
        setPhase("task");
        if (leg === 0) onArriveRef.current();
      }
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [ready, leg, phase, run]);

  const L = LEGS[leg];
  const status =
    phase === "driving"
      ? `Driving to ${L.job} · ${L.km} km`
      : phase === "task"
        ? `On site: ${L.task}`
        : phase === "assign"
          ? `New assignment: ${LEGS[leg + 1].job}`
          : "All three jobs done. Queue clear.";

  return (
    <section
      className="rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
      aria-label="Crew route"
    >
      <div className="mb-3 flex items-center gap-3">
        <p aria-live="polite" className="flex-1 text-sm font-semibold">
          {status}
        </p>
        {phase === "done" && (
          <button
            type="button"
            onClick={() => {
              setLeg(0);
              setPhase("driving");
              setRun((r) => r + 1);
            }}
            className="rounded-lg border px-3 py-1.5 text-sm font-medium"
            style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
          >
            Replay
          </button>
        )}
      </div>

      <div className="relative">
        <div
          ref={container}
          className="w-full overflow-hidden rounded-xl border"
          style={{ borderColor: "var(--border)", height: 300 }}
          role="img"
          aria-label={`Map of the route to ${L.job}, ${L.km} km, with ${L.obstacles.length} obstacles marked.`}
        />
        {phase === "assign" && (
          <div
            className="absolute inset-x-4 top-4 rounded-xl border-2 p-3 shadow-lg"
            style={{ background: "var(--surface-1)", borderColor: "var(--accent)" }}
          >
            <p className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: "var(--accent)" }}>
              New assignment
            </p>
            <p className="text-sm font-semibold">{LEGS[leg + 1].job}</p>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {LEGS[leg + 1].task} · {LEGS[leg + 1].km} km
            </p>
          </div>
        )}
      </div>

      <h4 className="mt-4 mb-2 text-[11px] font-semibold tracking-wide uppercase" style={{ color: "var(--text-muted)" }}>
        On this route
      </h4>
      <ul className="space-y-2">
        {L.obstacles.map((o) => (
          <li key={o.street + o.kind} className="flex gap-3 text-sm">
            <span
              className="shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase"
              style={{ border: `1.5px solid ${OBSTACLE_STYLE[o.kind].color}`, color: OBSTACLE_STYLE[o.kind].color }}
            >
              {OBSTACLE_STYLE[o.kind].label}
            </span>
            <span style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{o.street}.</strong> {o.note}
            </span>
          </li>
        ))}
      </ul>

      <ol className="mt-4 space-y-1.5 border-t pt-3 text-sm" style={{ borderColor: "var(--border)" }}>
        {LEGS.map((l, i) => {
          const done = i < leg || (i === leg && phase !== "driving");
          return (
            <li key={l.job} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="inline-block size-2.5 shrink-0 rounded-full"
                style={{ background: done ? "#0e7a54" : i === leg ? "#c0262d" : "var(--border)" }}
              />
              <span style={{ color: i <= leg ? "var(--text-primary)" : "var(--text-muted)" }}>
                {l.job}
                <span className="sr-only">{done ? " (done)" : i === leg ? " (current)" : " (queued)"}</span>
              </span>
            </li>
          );
        })}
      </ol>

      <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Roads from OpenStreetMap via the OSRM router, saved once. Obstacle labels are placeholders until the
        obstacle algorithm is connected; the next two households are synthetic.
      </p>
    </section>
  );
}
