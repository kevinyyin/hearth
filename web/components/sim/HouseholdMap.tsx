"use client";

import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  COUNTY_ZOOM,
  type CountySim,
  type HouseholdState,
  type SideKey,
  type Vehicle,
} from "@/lib/simulation";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const HOMES = "households";
const HOMES_LAYER = "households-circles";
const CREWS = "crews";
const CREWS_LAYER = "crews-vans";

const FILL: Record<HouseholdState, string> = {
  reached: "#0e7a54",
  waiting: "#c4461a",
  /** Blue: helped once, and the delivery has run down. A different problem from never reached. */
  resupply: "#2a6fd6",
  /** Purple: a second delivery has been made. Carries a halo, because blue and
   *  purple sit close enough that colour alone is not enough to tell them apart. */
  restocked: "#9333a8",
  unaffected: "#b8b1a4",
};

/** A van seen from above, nose pointing up, so icon-rotate can aim it. */
const CAR_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="54" viewBox="0 0 34 54">
  <g>
    <rect x="4" y="2" width="26" height="50" rx="7" fill="#3d382e"/>
    <path d="M9 12 h16 v9 h-16 z" fill="#cfd6da" opacity="0.95"/>
    <rect x="8" y="30" width="18" height="12" rx="3" fill="#2a2520"/>
    <circle cx="17" cy="7" r="2.2" fill="#ffd9a0"/>
  </g>
</svg>`;

/** Waiting is drawn as a ring, so the three states differ in shape as well as colour. */
const STATE_MATCH = [
  "match", ["get", "state"],
  "reached", FILL.reached,
  "waiting", FILL.waiting,
  "resupply", FILL.resupply,
  "restocked", FILL.restocked,
  FILL.unaffected,
];

/** Waiting is a ring and resupply is a filled blue, so the three read apart by shape too. */
const HOME_PAINT = {
  "circle-color": STATE_MATCH,
  "circle-opacity": [
    "match", ["get", "state"],
    "reached", 1,
    "resupply", 0.95,
    "restocked", 1,
    "waiting", 0.12,
    0.85,
  ],
  "circle-radius": [
    "interpolate", ["linear"], ["zoom"],
    7, ["match", ["get", "state"], "unaffected", 2, 3.4],
    12, ["match", ["get", "state"], "unaffected", 4, 7],
  ],
  "circle-stroke-color": STATE_MATCH,
  // the halo on restocked is the secondary encoding that separates it from blue
  "circle-stroke-width": [
    "match", ["get", "state"],
    "waiting", 2,
    "restocked", 3,
    "resupply", 1.4,
    0.6,
  ],
  "circle-stroke-opacity": ["match", ["get", "state"], "restocked", 0.35, 1],
} as const;

/** The van icon, aimed along its leg. */
const CREW_LAYOUT = {
  "icon-image": "hearth-van",
  "icon-size": ["interpolate", ["linear"], ["zoom"], 7, 0.3, 12, 0.62],
  "icon-rotate": ["get", "bearing"],
  "icon-rotation-alignment": "map",
  "icon-allow-overlap": true,
  "icon-ignore-placement": true,
} as const;

function homes(
  county: CountySim,
  which: SideKey,
  time: number,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: county.households.map((h, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [h.lon, h.lat] },
      properties: { state: county.stateAt(i, time, which) },
    })),
  };
}

function crews(vans: Vehicle[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: vans.map((v, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [v.lon, v.lat] },
      properties: { bearing: v.bearing },
    })),
  };
}

/** Rasterises the van once per map, so the symbol layer has something to place. */
function addVanIcon(m: MapLibreMap): Promise<void> {
  return new Promise((resolve) => {
    if (m.hasImage("hearth-van")) return resolve();
    const img = new Image(34, 54);
    img.onload = () => {
      if (!m.hasImage("hearth-van")) m.addImage("hearth-van", img, { pixelRatio: 2 });
      resolve();
    };
    img.onerror = () => resolve(); // no icon is better than a dead map
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(CAR_SVG)}`;
  });
}

export default function HouseholdMap({
  county,
  center,
  which,
  time,
  vehicles = [],
  interactive = true,
  height = 320,
  onMap,
  ariaLabel,
}: {
  /** The population and its two runs; swapped when the API answers. */
  county: CountySim;
  center: [number, number];
  which: SideKey;
  /** Continuous hours, so a dot turns green the moment its van arrives. */
  time: number;
  /** Crew positions this frame; empty when nothing is moving. */
  vehicles?: Vehicle[];
  /** False for the small panel on the simulation page: same picture, no controls. */
  interactive?: boolean;
  /** A CSS length: a number of px, or something like "min(62vh, 620px)". */
  height?: number | string;
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
      center,
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

    m.on("load", async () => {
      m.addSource(HOMES, { type: "geojson", data: homes(county, which, 0) });
      m.addSource(CREWS, { type: "geojson", data: crews([]) });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      m.addLayer({ id: HOMES_LAYER, type: "circle", source: HOMES, paint: HOME_PAINT as any });
      await addVanIcon(m);
      if (!m.getLayer(CREWS_LAYER)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        m.addLayer({ id: CREWS_LAYER, type: "symbol", source: CREWS, layout: CREW_LAYOUT as any });
      }
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

  // Repaint on a 0.05h quantum rather than every animation frame: that is fine
  // enough that a dot flips as its van pulls up, and about twenty rebuilds a
  // simulated hour instead of sixty a second.
  const tick = Math.round(time * 20) / 20;

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      (m.getSource(HOMES) as GeoJSONSource | undefined)?.setData(homes(county, which, tick));
    };
    if (ready.current) apply();
    else m.once("load", apply);
  }, [county, which, tick]);

  // the real replay recentres the map on the county the run actually covers
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    const c = m.getCenter();
    if (Math.abs(c.lng - center[0]) < 1e-6 && Math.abs(c.lat - center[1]) < 1e-6) return;
    m.jumpTo({ center });
  }, [center]);

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
