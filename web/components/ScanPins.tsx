"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";
import { PIN_COLOR, PIN_LABEL, pinLabels } from "@/lib/home";
import { nearestSpot, scanRoute, type Spot } from "@/lib/scanRoute";
import type { InsideKind, InsidePin, Vec3 } from "@/lib/types";

const SDK_SRC = "https://static.matterport.com/showcase-sdk/latest.js";
const MAX_PINS = 50; // the API's cap
const OPEN_TIMEOUT_MS = 60_000; // a cold scan was measured at about 25 s; twice that before calling it failed
const HOLD_MS = 800;

// The slice of Matterport's embed SDK used here (verified Nov 14 on a real scan).
type Hit = { position: Vec3; normal: Vec3; object: string };
type Sweep = Spot; // a spot the scan was taken from, which the viewer can stand at
type Point = { x: number; y: number };
type Sdk = {
  App: { state: { waitUntil(f: (s: { phase: string }) => boolean): Promise<unknown> }; Phase: { PLAYING: string } };
  Tag: { add(...tags: object[]): Promise<string[]>; remove(...ids: string[]): Promise<unknown> };
  Mattertag: { navigateToTag(id: string, transition: unknown): Promise<unknown>; Transition: { FLY: unknown } };
  Mode: { moveTo(mode: unknown): Promise<unknown>; Mode: { FLOORPLAN: string }; current: { subscribe(f: (mode: string) => void): { cancel(): void } } };
  Sweep: {
    data: { subscribe(o: { onCollectionUpdated(sweeps: Record<string, Sweep>): void }): { cancel(): void } };
    current: { subscribe(f: (sweep: { id?: string; sid?: string }) => void): { cancel(): void } };
    moveTo(id: string, options: object): Promise<unknown>;
    Transition: { FLY: unknown };
  };
  Pointer: { intersection: { subscribe(f: (hit: Hit) => void): { cancel(): void } } };
  Camera: { getPose(): Promise<unknown>; pose: { subscribe(f: (pose: unknown) => void): { cancel(): void } } };
  Conversion: { worldToScreen(p: Vec3, pose: unknown, size: { w: number; h: number }): Point };
};
type Connect = (iframe: HTMLIFrameElement, key: string, unused: string) => Promise<Sdk>;

let script: Promise<void> | null = null;
function loadSdk(): Promise<void> {
  return (script ??= new Promise<void>((resolve, reject) => {
    const el = document.createElement("script");
    el.src = SDK_SRC;
    el.onload = () => resolve();
    el.onerror = () => {
      script = null; // let a later mount try again
      reject(new Error("the scan script did not load"));
    };
    document.head.appendChild(el);
  }));
}

const xyz = (v: Vec3): Vec3 => ({ x: v.x, y: v.y, z: v.z });
/** The spot the scan opens at, which is where whoever scanned the home chose to start: nearly always the way in. */
function openingSpot(s: Sdk): Promise<string | null> {
  let sub: { cancel(): void } | undefined;
  return new Promise<string | null>((resolve) => {
    sub = s.Sweep.current.subscribe((sweep) => {
      const id = sweep.id || sweep.sid; // empty while the viewer is between spots
      if (id) resolve(id);
    });
    setTimeout(() => resolve(null), 3000);
  }).finally(() => sub?.cancel());
}

const rgb = (hex: string) => ({ r: parseInt(hex.slice(1, 3), 16) / 255, g: parseInt(hex.slice(3, 5), 16) / 255, b: parseInt(hex.slice(5, 7), 16) / 255 });

/** One of the building's 3D scans with the resident's inside pins. With `onChange`, holding the pointer still on a
 *  surface offers "Drop pin here"; without it the pins are only shown and the view turns to the machine pin.
 *  The pins are always listed as text below, so they survive a scan that does not open. */
export default function ScanPins({ scanId, sdkKey, pins, kind, onChange, view = "inside", route = false }: {
  scanId: string;
  sdkKey: string | null;
  pins: InsidePin[];
  kind?: InsideKind;
  onChange?: (pins: InsidePin[]) => void;
  /** "floorplan" opens the scan from straight above; a click on a spot there takes the viewer inside at that spot.
   *  Pins are dropped in the in-person view only, so clicking around the floor plan never places one by accident. */
  view?: "inside" | "floorplan";
  /** On the floor plan, draw the walk from where the scan starts to the machine: the machine pin, or with none the
   *  spot farthest from the start. */
  route?: boolean;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [sdk, setSdk] = useState<Sdk | null>(null);
  const [state, setState] = useState<"opening" | "open" | "failed">("opening");
  const [spot, setSpot] = useState<{ hit: Hit; x: number; y: number } | null>(null);
  const tagIds = useRef<string[]>([]);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const turned = useRef(false);
  const sweeps = useRef<Record<string, Sweep>>({});
  const [mode, setMode] = useState<string | null>(null);
  const start = useRef<string | null>(null);
  const [walk, setWalk] = useState<{ w: number; h: number; line: Point[] } | null>(null);
  const editable = !!onChange;
  const labels = pinLabels(pins);

  // Open the scan. Only the scan and the key reload the iframe; pins never do.
  useEffect(() => {
    const iframe = frame.current;
    setSdk(null);
    setSpot(null);
    tagIds.current = [];
    turned.current = false;
    start.current = null;
    setWalk(null);
    if (!sdkKey || !iframe) return setState("failed");
    setState("opening");
    let cancelled = false;
    let opened = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    // The scan pauses while it is scrolled out of view, so the clock starts when it is first seen. A scan that opens
    // after the clock ran out still counts as open.
    const seen = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) timeout ??= setTimeout(() => !opened && !cancelled && setState("failed"), OPEN_TIMEOUT_MS);
    });
    seen.observe(iframe);
    const onLoad = async () => {
      try {
        await loadSdk();
        const connect = (window as unknown as { MP_SDK?: { connect: Connect } }).MP_SDK?.connect;
        if (!connect) throw new Error("the scan script is missing");
        const s = await connect(iframe, sdkKey, "");
        await s.App.state.waitUntil((a) => a.phase === s.App.Phase.PLAYING);
        if (route) start.current = await openingSpot(s); // read before the view leaves it for the floor plan
        if (view === "floorplan") await s.Mode.moveTo(s.Mode.Mode.FLOORPLAN).catch(() => {}); // a refused move leaves the walk-through view
        if (cancelled) return;
        opened = true;
        setSdk(s);
        setState("open");
      } catch {
        if (!cancelled) setState("failed");
      }
    };
    iframe.addEventListener("load", onLoad);
    iframe.src = `https://my.matterport.com/show?m=${encodeURIComponent(scanId)}&play=1&qs=1&applicationKey=${encodeURIComponent(sdkKey)}`;
    return () => {
      cancelled = true;
      clearTimeout(timeout);
      seen.disconnect();
      iframe.removeEventListener("load", onLoad);
    };
  }, [scanId, sdkKey, view, route]);

  // Keep the scan's tags equal to the pins. Runs are queued so a quick second change cannot interleave with the first.
  useEffect(() => {
    if (!sdk) return;
    queue.current = queue.current.then(async () => {
      try {
        if (tagIds.current.length) await sdk.Tag.remove(...tagIds.current);
        tagIds.current = pins.length
          ? await sdk.Tag.add(...pins.map((p, i) => ({
              label: labels[i], description: "", anchorPosition: xyz(p.position),
              stemVector: { x: p.normal.x * 0.3, y: p.normal.y * 0.3, z: p.normal.z * 0.3 }, color: rgb(PIN_COLOR[p.kind]),
            })))
          : [];
        const machine = pins.findIndex((p) => p.kind === "machine");
        if (!editable && !route && !turned.current && machine >= 0) { // flying to the pin would leave the floor plan the route is on
          turned.current = true;
          await sdk.Mattertag.navigateToTag(tagIds.current[machine], sdk.Mattertag.Transition.FLY);
        }
      } catch {
        // the text list below still shows every pin
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- labels derive from pins
  }, [sdk, pins, editable]);

  // Which view the scan is in, and the spots a viewer can stand at: both feed the floor plan's double-click. The
  // spots and the camera also place the route, which is redrawn whenever either moves.
  useEffect(() => {
    if (!sdk) return;
    let pose: unknown = null;
    const draw = () => {
      const iframe = frame.current;
      if (!route || !pose || !iframe || !start.current) return;
      const all = sweeps.current;
      const machine = pins.find((p) => p.kind === "machine");
      const spots = scanRoute(all, start.current, machine ? nearestSpot(all, machine.position) : null).map((id) => all[id].position);
      if (machine && spots.length) spots.push(machine.position);
      const size = { w: iframe.clientWidth, h: iframe.clientHeight };
      setWalk(spots.length > 1 ? { ...size, line: spots.map((p) => sdk.Conversion.worldToScreen(p, pose, size)) } : null);
    };
    const a = sdk.Mode.current.subscribe(setMode);
    const b = sdk.Sweep.data.subscribe({ onCollectionUpdated: (all) => { sweeps.current = all; draw(); } });
    const c = sdk.Camera.pose.subscribe((p) => { pose = p; draw(); });
    // a scan that named no spot while it opened still gets its route from the first one it names
    const d = sdk.Sweep.current.subscribe((sweep) => {
      const id = sweep.id || sweep.sid;
      if (id && !start.current) { start.current = id; draw(); }
    });
    return () => {
      a.cancel();
      b.cancel();
      c.cancel();
      d.cancel();
    };
  }, [sdk, route, pins]);

  /** A double-click on the floor plan: stand at the scan spot nearest to it on screen, in the in-person view. */
  async function standAt(e: MouseEvent<HTMLDivElement>) {
    const iframe = frame.current;
    if (!sdk || !iframe) return;
    const box = e.currentTarget.getBoundingClientRect();
    const at = { x: e.clientX - box.left, y: e.clientY - box.top };
    const pose = await sdk.Camera.getPose();
    const size = { w: iframe.clientWidth, h: iframe.clientHeight };
    let nearest: string | null = null;
    let best = Infinity;
    for (const [id, s] of Object.entries(sweeps.current)) {
      if (s.enabled === false) continue;
      const p = sdk.Conversion.worldToScreen(s.position, pose, size);
      const d = (p.x - at.x) ** 2 + (p.y - at.y) ** 2;
      if (d < best) [nearest, best] = [id, d];
    }
    if (nearest) await sdk.Sweep.moveTo(nearest, { transition: sdk.Sweep.Transition.FLY, transitionTime: 1200 }).catch(() => {});
  }

  // Editing: a pointer held still on a real surface offers the drop button under it.
  useEffect(() => {
    if (!sdk || !editable) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sub = sdk.Pointer.intersection.subscribe((hit) => {
      setSpot(null);
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const iframe = frame.current;
        // sky, a window or anything outside the model reports another object and a position thousands of metres away
        if (!iframe || hit.object !== "intersectedobject.model") return;
        const size = { w: iframe.clientWidth, h: iframe.clientHeight };
        const pose = await sdk.Camera.getPose();
        if ((pose as { mode?: string }).mode !== "mode.inside") return; // on the floor plan a click means "go there", not "pin this"
        const p = sdk.Conversion.worldToScreen(hit.position, pose, size);
        // the value the SDK replays on subscribe is not under the pointer and can project outside the view
        if (p.x >= 0 && p.x <= size.w && p.y >= 0 && p.y <= size.h) setSpot({ hit, x: p.x, y: p.y });
      }, HOLD_MS);
    });
    return () => {
      clearTimeout(timer);
      sub.cancel();
    };
  }, [sdk, editable]);

  return (
    <div className="space-y-2">
      <div className="relative w-full overflow-hidden rounded" style={{ aspectRatio: "16 / 10", background: "var(--grid)", display: sdkKey ? "block" : "none" }}>
        <iframe ref={frame} title="3D scan of the home" className="h-full w-full border-0" allow="xr-spatial-tracking; fullscreen" />
        {view === "floorplan" && sdk && mode === sdk.Mode.Mode.FLOORPLAN && (
          // The scan lives in another site's frame, which keeps its own clicks. This sheet over the floor plan catches
          // the double-click instead; it is gone once the viewer is inside, so the in-person view works as usual.
          <div className="absolute inset-0 cursor-pointer" title="Double-click a spot to stand there" onDoubleClick={standAt}>
            {walk && (
              <>
                <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${walk.w} ${walk.h}`} preserveAspectRatio="none" aria-hidden>
                  {/* white under the dots, so the route reads on a dark floor and a pale one */}
                  {([["#fff", 6, undefined], [PIN_COLOR.route, 3.5, "0.1 8"]] as const).map(([stroke, width, dash]) => (
                    <polyline key={stroke} points={walk.line.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke={stroke}
                      strokeWidth={width} strokeDasharray={dash} strokeLinejoin="round" strokeLinecap="round" />
                  ))}
                </svg>
                {(["entrance", "machine"] as const).map((k) => {
                  const p = walk.line[k === "entrance" ? 0 : walk.line.length - 1];
                  return (
                    <span key={k} className="pointer-events-none absolute flex flex-col items-center"
                      style={{ left: `${(p.x / walk.w) * 100}%`, top: `${(p.y / walk.h) * 100}%`, transform: "translate(-50%, -7px)" }}>
                      <span className="block h-3.5 w-3.5 rounded-full border-2 border-white shadow" style={{ background: PIN_COLOR[k] }} />
                      <span className="mt-0.5 rounded px-1 text-[10px] font-semibold leading-4 text-white" style={{ background: PIN_COLOR[k] }}>
                        {PIN_LABEL[k]}
                      </span>
                    </span>
                  );
                })}
              </>
            )}
          </div>
        )}
        {state === "opening" && (
          <p className="absolute inset-x-0 bottom-2 text-center text-xs" style={{ color: "var(--text-muted)" }}>Opening the 3D scan…</p>
        )}
        {spot && onChange && kind && pins.length < MAX_PINS && (
          // sits under the pointer: moving toward a button placed elsewhere would move the pointer and dismiss it
          <button
            type="button"
            className="absolute rounded px-2 py-1 text-xs font-semibold text-white shadow"
            style={{ left: spot.x, top: spot.y, transform: "translate(-50%, -50%)", background: PIN_COLOR[kind] }}
            onMouseLeave={() => setSpot(null)}
            onClick={() => {
              onChange([...pins, { kind, position: xyz(spot.hit.position), normal: xyz(spot.hit.normal) }]);
              setSpot(null);
            }}
          >
            Drop pin here
          </button>
        )}
      </div>
      {state === "failed" && <p className="text-xs" style={{ color: "#d03b3b" }}>The 3D scan did not open.</p>}
      {walk && sdk && mode === sdk.Mode.Mode.FLOORPLAN && (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
            <span className="flex items-center gap-1.5 font-semibold">
              <svg width="22" height="6" aria-hidden="true">
                <line x1="2" y1="3" x2="20" y2="3" stroke={PIN_COLOR.route} strokeWidth="3.5" strokeDasharray="0.1 6" strokeLinecap="round" />
              </svg>
              Recommended path
            </span>
            {(["entrance", "machine"] as const).map((k) => (
              <span key={k} className="flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: PIN_COLOR[k] }} />
                {PIN_LABEL[k]}
              </span>
            ))}
          </div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            The recommended path is the walk from the entrance to the machine. It is planned over the spots the scanner stood
            at, so every step of it is somewhere a person can stand. The entrance is where the scan starts
            {pins.some((p) => p.kind === "machine") ? "." : "; nobody has pinned the machine yet, so the simulation places it in the farthest room from the door."}
          </p>
        </>
      )}
      {route && sdk && mode !== null && mode !== sdk.Mode.Mode.FLOORPLAN && (
        // the route is drawn on the floor plan only, and a double-click there walks the viewer inside
        <button type="button" className="rounded border px-2.5 py-1 text-xs font-semibold" style={{ borderColor: "var(--border)" }}
          onClick={() => sdk.Mode.moveTo(sdk.Mode.Mode.FLOORPLAN).catch(() => {})}>
          Show the recommended path on the floor plan
        </button>
      )}
      {editable && state !== "failed" && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {view === "floorplan" && "Double-click a spot on the floor plan to stand there. "}
          In the in-person view, hold the pointer still on the spot, then press &quot;Drop pin here&quot;.
        </p>
      )}
      {pins.length > 0 && (
        <ol className="space-y-1 text-xs" aria-label="Inside pins">
          {pins.map((p, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PIN_COLOR[p.kind] }} />
              <span className="flex-1">{labels[i]}</span>
              {onChange && (
                <button type="button" className="underline underline-offset-2" style={{ color: "var(--text-secondary)" }}
                  aria-label={`Remove ${labels[i]} pin`} onClick={() => onChange(pins.filter((_, j) => j !== i))}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
