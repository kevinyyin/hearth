"use client";

import { useEffect, useRef, useState } from "react";
import { PIN_COLOR, pinLabels } from "@/lib/home";
import type { InsideKind, InsidePin, Vec3 } from "@/lib/types";

const SDK_SRC = "https://static.matterport.com/showcase-sdk/latest.js";
const MAX_PINS = 50; // the API's cap
const OPEN_TIMEOUT_MS = 60_000; // a cold scan was measured at about 25 s; twice that before calling it failed
const HOLD_MS = 800;

// The slice of Matterport's embed SDK used here (verified Nov 14 on a real scan).
type Hit = { position: Vec3; normal: Vec3; object: string };
type Sdk = {
  App: { state: { waitUntil(f: (s: { phase: string }) => boolean): Promise<unknown> }; Phase: { PLAYING: string } };
  Tag: { add(...tags: object[]): Promise<string[]>; remove(...ids: string[]): Promise<unknown> };
  Mattertag: { navigateToTag(id: string, transition: unknown): Promise<unknown>; Transition: { FLY: unknown } };
  Pointer: { intersection: { subscribe(f: (hit: Hit) => void): { cancel(): void } } };
  Camera: { getPose(): Promise<unknown> };
  Conversion: { worldToScreen(p: Vec3, pose: unknown, size: { w: number; h: number }): { x: number; y: number } };
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
const rgb = (hex: string) => ({ r: parseInt(hex.slice(1, 3), 16) / 255, g: parseInt(hex.slice(3, 5), 16) / 255, b: parseInt(hex.slice(5, 7), 16) / 255 });

/** One of the building's 3D scans with the resident's inside pins. With `onChange`, holding the pointer still on a
 *  surface offers "Drop pin here"; without it the pins are only shown and the view turns to the machine pin.
 *  The pins are always listed as text below, so they survive a scan that does not open. */
export default function ScanPins({ scanId, sdkKey, pins, kind, onChange }: {
  scanId: string;
  sdkKey: string | null;
  pins: InsidePin[];
  kind?: InsideKind;
  onChange?: (pins: InsidePin[]) => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [sdk, setSdk] = useState<Sdk | null>(null);
  const [state, setState] = useState<"opening" | "open" | "failed">("opening");
  const [spot, setSpot] = useState<{ hit: Hit; x: number; y: number } | null>(null);
  const tagIds = useRef<string[]>([]);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const turned = useRef(false);
  const editable = !!onChange;
  const labels = pinLabels(pins);

  // Open the scan. Only the scan and the key reload the iframe; pins never do.
  useEffect(() => {
    const iframe = frame.current;
    setSdk(null);
    setSpot(null);
    tagIds.current = [];
    turned.current = false;
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
  }, [scanId, sdkKey]);

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
        if (!editable && !turned.current && machine >= 0) {
          turned.current = true;
          await sdk.Mattertag.navigateToTag(tagIds.current[machine], sdk.Mattertag.Transition.FLY);
        }
      } catch {
        // the text list below still shows every pin
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- labels derive from pins
  }, [sdk, pins, editable]);

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
        const p = sdk.Conversion.worldToScreen(hit.position, await sdk.Camera.getPose(), size);
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
        <iframe ref={frame} title="3D scan of a sample unit" className="h-full w-full border-0" allow="xr-spatial-tracking; fullscreen" />
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
      {editable && state !== "failed" && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Hold the pointer still on the spot, then press &quot;Drop pin here&quot;.</p>
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
