"use client";

import maplibregl, { type GeoJSONSource, type Map as MapLibreMap, type Marker } from "maplibre-gl";
import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { STYLE_URL } from "@/components/Map";
import { SIMULATED_COLOR } from "@/lib/dispatch";

export type MapPin = { id: string; lat: number; lon: number; label: string; note: string; color: string; lot?: "chosen" | "proposed" };

const HOUSTON: [number, number] = [-95.37, 29.76];
const WIDE = "(min-width: 960px)";

/** A labelled pin: a coloured dot (or a "P" square for a staging lot) and its tag. A button, so a keyboard reaches it. */
function pinElement(p: MapPin, selected: boolean, onSelect: (id: string) => void): HTMLElement {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "flex cursor-pointer items-center gap-1.5 rounded-md focus-visible:outline-2 focus-visible:outline-[var(--accent)]";
  el.setAttribute("aria-label", `${p.label}, ${p.note}`);
  el.setAttribute("aria-pressed", String(selected));
  const dot = document.createElement("span");
  if (p.lot) {
    dot.textContent = "P";
    dot.className = "grid h-[18px] w-[18px] flex-none place-items-center rounded text-[11px] font-bold";
    Object.assign(dot.style, p.lot === "chosen" ? { background: "var(--text-primary)", color: "#fff", border: "2px solid #fff" }
      : { background: "var(--surface-1)", color: "var(--text-primary)", border: "2px solid var(--text-primary)" });
  } else {
    dot.className = "h-4 w-4 flex-none rounded-full border-[3px] border-white";
    dot.style.background = p.color;
  }
  dot.style.boxShadow = selected ? "0 0 0 2px var(--text-primary)" : "0 1px 4px rgba(20,19,15,.35)";
  const tag = document.createElement("span");
  tag.className = "whitespace-nowrap rounded-md border px-[7px] py-0.5 text-xs";
  Object.assign(tag.style, { background: "var(--surface-1)", borderColor: selected ? "var(--text-primary)" : "var(--border)", boxShadow: "0 1px 3px rgba(20,19,15,.12)", color: "var(--text-primary)" });
  const note = document.createElement("span");
  note.style.color = "var(--text-muted)";
  note.textContent = ` · ${p.note}`;
  tag.append(p.label, note);
  el.append(dot, tag);
  el.addEventListener("click", (e) => {
    e.stopPropagation();
    onSelect(p.id);
  });
  return el;
}

/** The county map: faint simulated households behind the real ones, labelled pins by state, and staging lots. The view
 *  fits every real pin when a new one appears, padded on wide screens so the household card never covers a pin. */
export default function DispatchMap({ pins, simulated, selected, onSelect }: {
  pins: MapPin[];
  simulated: number[][];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const fitted = useRef("");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({ container: container.current, style: STYLE_URL, center: HOUSTON, zoom: 10, attributionControl: false });
    m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    // MapLibre opens the compact attribution on first paint; collapse it back to the "i"
    m.once("load", () => container.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"));
    m.on("click", () => onSelectRef.current(null));
    // "style.load", not "load": "load" waits for every basemap tile, and a slow raster tile held the dots back
    m.once("style.load", () => {
      m.addSource("simulated", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "simulated", type: "circle", source: "simulated", paint: { "circle-radius": 2.4, "circle-color": SIMULATED_COLOR, "circle-opacity": 0.55 } });
      m.fire("hearth.ready");
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const push = () =>
      (m.getSource("simulated") as GeoJSONSource | undefined)?.setData({
        type: "FeatureCollection",
        features: simulated.map(([lon, lat]) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [lon, lat] } })),
      });
    if (m.getSource("simulated")) push();
    else m.once("hearth.ready", push);
  }, [simulated]);

  // pins are rebuilt only when what they show changes, not on every poll
  const key = JSON.stringify([pins, selected]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    const seen = new Map<string, number>(); // households in one building stack downward instead of hiding each other
    markers.current = pins.map((p) => {
      const at = `${p.lat.toFixed(4)},${p.lon.toFixed(4)}`;
      const k = seen.get(at) ?? 0;
      seen.set(at, k + 1);
      return new maplibregl.Marker({ element: pinElement(p, p.id === selected, (id) => onSelectRef.current(id)), anchor: "left", offset: [-8, k * 24] })
        .setLngLat([p.lon, p.lat]).addTo(m);
    });
    const ids = pins.map((p) => p.id).sort().join();
    if (pins.length && ids !== fitted.current) {
      fitted.current = ids;
      const b = new maplibregl.LngLatBounds();
      pins.forEach((p) => b.extend([p.lon, p.lat]));
      // tags extend right of their dot and stacked pins downward; the legend sits bottom-left (top-left on a phone)
      const wide = matchMedia(WIDE).matches;
      m.fitBounds(b, { padding: wide ? { top: 70, bottom: 110, left: 70, right: 420 } : { top: 70, bottom: 40, left: 30, right: 170 }, maxZoom: 14, animate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return <div ref={container} className="h-full w-full" aria-label="Map of households" />;
}
