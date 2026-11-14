"use client";

import maplibregl, {
  type DataDrivenPropertyValueSpecification,
  type GeoJSONSource,
  type Map as MapLibreMap,
} from "maplibre-gl";
import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { PLAN_STATES, stateColor, stateRadius } from "@/lib/snapshots";
import type { Meta, PatientSnap, PlanState, Snapshot } from "@/lib/types";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const SOURCE = "patients";
const LAYER = "patients-circles";

/**
 * Builds `["match", ["get","state"], STATE, value, ..., fallback]`. The spread makes the
 * tuple variadic, which MapLibre's expression types cannot express, so it is cast once here.
 */
function matchState<T extends string | number>(
  fn: (state: PlanState) => T,
  fallback: T,
): DataDrivenPropertyValueSpecification<T> {
  const pairs = PLAN_STATES.flatMap((state) => [state, fn(state)]);
  return ["match", ["get", "state"], ...pairs, fallback] as unknown as
    DataDrivenPropertyValueSpecification<T>;
}

function toFeatureCollection(
  patients: PatientSnap[],
  isolated: PlanState | null,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: patients.map((p) => ({
      type: "Feature",
      id: Number(p.id.replace(/\D/g, "")) || undefined,
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: {
        id: p.id,
        state: p.state,
        device: p.device,
        dimmed: isolated !== null && p.state !== isolated ? 1 : 0,
      },
    })),
  };
}

export default function Map({
  meta,
  snapshot,
  isolated,
  selectedId,
  onSelect,
}: {
  meta: Meta;
  snapshot: Snapshot | null;
  isolated: PlanState | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  // The click handler is registered once, so read the latest callback through a ref.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;

    const [lat, lon] = meta.center; // meta.center is [lat, lon]; MapLibre wants [lon, lat].
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [lon, lat],
      zoom: 11,
      attributionControl: { compact: true },
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    m.on("load", () => {
      m.addSource(SOURCE, { type: "geojson", data: toFeatureCollection([], null) });
      m.addLayer({
        id: LAYER,
        type: "circle",
        source: SOURCE,
        paint: {
          "circle-color": matchState(stateColor, "#b8b6ad"),
          "circle-radius": matchState(stateRadius, 5),
          // A surface ring keeps overlapping marks readable; URGENT wears a thicker one.
          "circle-stroke-width": ["case", ["==", ["get", "state"], "URGENT"], 2.5, 1.5],
          "circle-stroke-color": "#ffffff",
          "circle-opacity": ["case", ["==", ["get", "dimmed"], 1], 0.15, 0.95],
          "circle-stroke-opacity": ["case", ["==", ["get", "dimmed"], 1], 0.1, 0.9],
        },
      });

      m.on("click", LAYER, (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === "string") onSelectRef.current(id);
      });
      m.on("click", (e) => {
        const hits = m.queryRenderedFeatures(e.point, { layers: [LAYER] });
        if (hits.length === 0) onSelectRef.current(null);
      });
      m.on("mouseenter", LAYER, () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", LAYER, () => {
        m.getCanvas().style.cursor = "";
      });

      ready.current = true;
      m.fire("hearth.ready");
    });

    return () => {
      ready.current = false;
      m.remove();
      map.current = null;
    };
    // Built once; meta.center only moves when the whole run changes, which remounts this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.center[0], meta.center[1]]);

  // Swap the data whenever the tick, the isolated state or the selection changes.
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const push = () => {
      const src = m.getSource(SOURCE) as GeoJSONSource | undefined;
      if (!src) return;
      src.setData(toFeatureCollection(snapshot?.patients ?? [], isolated));
    };

    if (ready.current) push();
    else m.once("hearth.ready", push);
  }, [snapshot, isolated]);

  // A selected patient gets a halo so the panel and the map agree on who is open.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;

    const HALO = "patients-selected";
    if (m.getLayer(HALO)) m.removeLayer(HALO);
    if (!selectedId) return;

    m.addLayer({
      id: HALO,
      type: "circle",
      source: SOURCE,
      filter: ["==", ["get", "id"], selectedId],
      paint: {
        "circle-radius": matchState((s) => stateRadius(s) + 7, 12),
        "circle-color": "rgba(0,0,0,0)",
        "circle-stroke-width": 2,
        "circle-stroke-color": "#0b0b0b",
      },
    });
  }, [selectedId, snapshot]);

  return <div ref={container} className="h-full w-full" aria-label="Patient map" />;
}
