"use client";

import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  COUNTY_CENTER,
  COUNTY_ZOOM,
  HOUSEHOLDS,
  stateAt,
  type HouseholdState,
  type SideKey,
} from "@/lib/simulation";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const HOMES = "households";
const HOMES_LAYER = "households-circles";
const CREWS = "crews";
const CREWS_LAYER = "crews-circles";

const FILL: Record<HouseholdState, string> = {
  reached: "#0e7a54",
  waiting: "#c4461a",
  unaffected: "#b8b1a4",
};

/** Waiting is drawn as a ring, so the three states differ in shape as well as colour. */
const HOME_PAINT = {
  "circle-color": [
    "match", ["get", "state"],
    "reached", FILL.reached,
    "waiting", FILL.waiting,
    FILL.unaffected,
  ],
  "circle-opacity": ["match", ["get", "state"], "reached", 1, "waiting", 0.12, 0.85],
  "circle-radius": [
    "interpolate", ["linear"], ["zoom"],
    7, ["match", ["get", "state"], "unaffected", 2, 3.4],
    12, ["match", ["get", "state"], "unaffected", 4, 7],
  ],
  "circle-stroke-color": [
    "match", ["get", "state"],
    "reached", FILL.reached,
    "waiting", FILL.waiting,
    FILL.unaffected,
  ],
  "circle-stroke-width": ["match", ["get", "state"], "waiting", 2, 0.6],
  "circle-stroke-opacity": 1,
} as const;

/** Deliberately quiet: the vans show motion without competing with the dots. */
const CREW_PAINT = {
  "circle-color": "#3d382e",
  "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 2.6, 12, 5],
  "circle-stroke-color": "#fbf9f4",
  "circle-stroke-width": 1.2,
  "circle-opacity": 0.9,
} as const;

function homes(which: SideKey, hour: number): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: HOUSEHOLDS.map((h, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [h.lon, h.lat] },
      properties: { state: stateAt(i, hour, which) },
    })),
  };
}

function crews(points: [number, number][]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: points.map((p, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: p },
      properties: {},
    })),
  };
}

export default function HouseholdMap({
  which,
  hour,
  vehicles = [],
  interactive = true,
  height = 320,
  onMap,
  ariaLabel,
}: {
  which: SideKey;
  hour: number;
  /** Crew positions this frame; empty when nothing is moving. */
  vehicles?: [number, number][];
  /** False for the small panel on the simulation page: same picture, no controls. */
  interactive?: boolean;
  height?: number;
  /** Hands the map instance up, so a parent can wire two of them together. */
  onMap?: (m: MapLibreMap | null) => void;
  ariaLabel: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  const onMapRef = useRef(onMap);
  onMapRef.current = onMap;

  useEffect(() => {
    if (!container.current || map.current) return;

    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: COUNTY_CENTER,
      zoom: COUNTY_ZOOM,
      interactive,
      // added by hand below, so it starts as the "i" and opens only when asked
      attributionControl: false,
    });
    map.current = m;
    m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    if (interactive) {
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    }

    m.on("load", () => {
      m.addSource(HOMES, { type: "geojson", data: homes(which, 0) });
      m.addSource(CREWS, { type: "geojson", data: crews([]) });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      m.addLayer({ id: HOMES_LAYER, type: "circle", source: HOMES, paint: HOME_PAINT as any });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      m.addLayer({ id: CREWS_LAYER, type: "circle", source: CREWS, paint: CREW_PAINT as any });
      ready.current = true;
      // MapLibre renders the compact attribution open on first paint; collapse it
      // back to the "i" so it is opt-in rather than opt-out.
      container.current
        ?.querySelector(".maplibregl-ctrl-attrib")
        ?.classList.remove("maplibregl-compact-show");
      onMapRef.current?.(m);
    });

    return () => {
      onMapRef.current?.(null);
      m.remove();
      map.current = null;
      ready.current = false;
    };
  }, [which, interactive]);

  // repaint the dots as the hour advances
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      (m.getSource(HOMES) as GeoJSONSource | undefined)?.setData(homes(which, hour));
    };
    if (ready.current) apply();
    else m.once("load", apply);
  }, [which, hour]);

  // the vans; this runs every animation frame, so it only touches the one source
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource(CREWS) as GeoJSONSource | undefined)?.setData(crews(vehicles));
  }, [vehicles]);

  return (
    <div
      ref={container}
      className="w-full overflow-hidden rounded-xl border"
      style={{ borderColor: "var(--border)", height }}
      role="img"
      aria-label={ariaLabel}
    />
  );
}
