"use client";

import { useEffect, useRef, useState } from "react";
import AgentTrace from "@/components/AgentTrace";
import { API, getJson } from "@/lib/api";
import { reduceTrace, streamEvents } from "@/lib/sse";
import { type BuildingDetail, PROFILE_FIELDS, type TraceEvent } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

type Row = { building_id: string; name: string | null; surveyed: boolean };
type Recording = { recorded_at: number; events: TraceEvent[] };

const DEFAULT = "7768847"; // Calais Midtown Apartments: all three layers, and conflicts between them
const SPEED = 2;
const LAYER: Record<string, [string, string]> = {
  costar: ["CoStar", "var(--series-1)"], vexcel: ["Vexcel", "var(--series-3)"], matterport: ["Matterport", "var(--series-2)"],
};
const AGENT: Record<string, string> = { costar: "costar", aerial: "vexcel", interior: "matterport" };
const muted = { color: "var(--text-muted)" };
const fmt = (v: unknown) => (Array.isArray(v) ? `${v.length} rooms` : typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v));

function Tag({ layer }: { layer: string }) {
  const [name, color] = LAYER[layer] ?? ["lead agent", "var(--text-muted)"];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <i className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />{name}
    </span>
  );
}

/** One real building's surveyed profile from the API, and its last real survey replayed at 2× (or run live). */
export default function LiveSurvey() {
  const [rows, setRows] = useState<Row[]>([]);
  const [id, setId] = useState(DEFAULT);
  const [detail, setDetail] = useState<BuildingDetail | null>(null);
  const [recording, setRecording] = useState<Recording | null | undefined>(undefined);
  const [shown, setShown] = useState<TraceEvent[]>([]);
  const [mode, setMode] = useState<"idle" | "replay" | "live">("idle");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const started = useRef(0);
  const timers = useRef<number[]>([]);
  const log = useRef<HTMLOListElement>(null);
  const image = useAuthedImage(detail?.image_url ?? null);

  const stop = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const load = (bid: string) => {
    getJson<BuildingDetail>(`/api/buildings/${bid}`).then(setDetail).catch((e: Error) => setError(e.message));
    getJson<Recording>(`/api/buildings/${bid}/survey/recording`).then(setRecording).catch(() => setRecording(null));
  };

  useEffect(() => {
    if (API) getJson<Row[]>("/api/buildings").then((all) => setRows(all.filter((r) => r.surveyed))).catch((e: Error) => setError(e.message));
    return stop;
  }, []);
  useEffect(() => {
    if (rows.length && !rows.some((r) => r.building_id === id)) setId(rows[0].building_id);
  }, [rows, id]);
  useEffect(() => {
    stop();
    setShown([]);
    setMode("idle");
    setDetail(null);
    setRecording(undefined);
    setError(null);
    if (API) load(id);
  }, [id]);
  useEffect(() => {
    if (mode === "idle") return;
    const tick = setInterval(() => setNow((performance.now() - started.current) / 1000), 100);
    return () => clearInterval(tick);
  }, [mode]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [shown.length]);

  function replay() {
    if (!recording?.events.length) return;
    stop();
    setShown([]);
    setError(null);
    setMode("replay");
    started.current = performance.now();
    for (const e of recording.events) timers.current.push(window.setTimeout(() => setShown((s) => [...s, e]), (e.t * 1000) / SPEED));
    timers.current.push(window.setTimeout(() => setMode("idle"), (recording.events.at(-1)!.t * 1000) / SPEED + 100));
  }

  async function live() {
    stop();
    setShown([]);
    setError(null);
    setMode("live");
    started.current = performance.now();
    try {
      await streamEvents(`/api/buildings/${id}/survey?fresh=true`, undefined, (e) => setShown((s) => [...s, e]));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg.startsWith("409") ? "A survey of this building is already running. Replay the last one instead." : `The live run failed: ${msg}`);
    }
    setMode("idle");
    load(id);
  }

  if (!API) return <p className="text-sm" style={muted}>The live section needs the Hearth API.</p>;

  const p = detail?.profile;
  const known = p ? PROFILE_FIELDS.filter((f) => p[f].source !== "default") : [];
  const unknown = p ? PROFILE_FIELDS.filter((f) => p[f].source === "default") : [];
  const took = recording?.events.at(-1)?.t;
  const effects = detail?.layer_effects && detail.hours_to_unsafe != null
    ? [["All layers", detail.hours_to_unsafe, "var(--text-primary)"] as const,
       ...Object.entries(detail.layer_effects).map(([l, h]) => [`Without ${LAYER[l]?.[0] ?? l}`, h, LAYER[l]?.[1] ?? "var(--text-muted)"] as const)]
    : [];
  const top = Math.max(...effects.map((e) => e[1]), 1);
  const costarShift = detail?.layer_effects && detail.hours_to_unsafe != null ? detail.hours_to_unsafe - detail.layer_effects.costar : null;
  const playing = mode !== "idle";

  return (
    <div className="rounded-2xl border p-6" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Surveyed buildings">
        {rows.map((r) => (
          <button key={r.building_id} type="button" onClick={() => setId(r.building_id)} aria-pressed={r.building_id === id} disabled={playing}
            className={`rounded-full border px-3 py-1 text-[13px] disabled:opacity-60 ${r.building_id === id ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-1)]" : "border-[var(--border)] hover:bg-[var(--surface-2)]"}`}>
            {r.name ?? r.building_id}
          </button>
        ))}
      </div>
      {detail && <p className="mt-3 text-[13px]" style={muted}>CoStar property {detail.building_id} · {detail.address}</p>}
      {error && <p role="alert" className="mt-2 text-[13px]" style={{ color: "#9a3214" }}>{error}</p>}

      <div className="mt-5 grid gap-8 lg:grid-cols-2">
        <section aria-label="Surveyor trace" className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={replay} disabled={playing || !recording?.events.length}
              className="rounded-[7px] border border-[var(--text-primary)] bg-[var(--text-primary)] px-3 py-1.5 text-[13px] font-medium text-[var(--surface-1)] hover:bg-[#2b2925] disabled:opacity-50">
              {mode === "replay" ? "Replaying…" : `Replay the last survey · ${SPEED}×`}
            </button>
            <button type="button" onClick={live} disabled={playing}
              className="rounded-[7px] border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-[13px] font-medium hover:bg-[var(--surface-2)] disabled:opacity-50">
              {mode === "live" ? "Running live…" : "Run it live"}
            </button>
            <span className="tnum text-xs" style={muted}>
              {playing ? `${now.toFixed(1)} s${mode === "replay" ? ` · ${(now * SPEED).toFixed(1)} s of the real run` : ""}`
                : recording ? `Recorded ${new Date(recording.recorded_at * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · took ${took?.toFixed(1)} s live`
                : recording === null ? "No recorded survey yet: run it live once." : ""}
            </span>
          </div>
          <ol ref={log} aria-live="polite" className="mt-3 h-56 overflow-auto rounded-lg border px-3 py-2 font-mono text-[11.5px] leading-[1.7]"
            style={{ background: "var(--surface-0)", borderColor: "var(--border)" }}>
            {shown.length === 0 && <li style={muted}>Events from the deep agent stream here: the plan, three subagents in parallel, their tool calls, conflicts, the profile.</li>}
            {shown.filter((e) => e.kind !== "todo").map((e) => (
              <li key={e.seq} className="grid grid-cols-[3.2rem_6.5rem_1fr] gap-2" title={e.text}>
                <span className="tnum text-right" style={muted}>{e.t.toFixed(1)}s</span>
                <Tag layer={AGENT[e.agent] ?? e.agent} />
                <span className="truncate" style={{ color: e.kind === "conflict" ? "#9a3214" : "var(--text-secondary)" }}>{e.kind === "tool" ? e.text : `${e.kind}: ${e.text}`}</span>
              </li>
            ))}
          </ol>
          <div className="mt-4"><AgentTrace view={reduceTrace(shown)} running={playing} /></div>
        </section>

        <section aria-label="Surveyed profile" className="min-w-0">
          {!detail && !error && <p className="text-[13px]" style={muted}>Loading the building…</p>}
          {p && (<>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-xs" style={muted}>
                  <th className="pb-1.5 font-medium">Field</th><th className="pb-1.5 font-medium">Value</th>
                  <th className="pb-1.5 font-medium">Source</th><th className="pb-1.5 text-right font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {known.map((f) => (
                  <tr key={f} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="py-1 pr-3 font-mono text-[12px]">{f}</td>
                    <td className="max-w-[14rem] truncate py-1 pr-3" title={fmt(p[f].value)}>{fmt(p[f].value)}</td>
                    <td className="py-1 pr-3"><Tag layer={p[f].source} /></td>
                    <td className="tnum py-1 text-right">{p[f].confidence.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {unknown.length > 0 && <p className="mt-2 text-xs leading-relaxed" style={muted}>No layer showed: <span className="font-mono">{unknown.join(", ")}</span>. Left unknown, never guessed.</p>}
            {p.conflicts.length > 0 && (
              <div className="mt-4">
                <h3 className="text-xs font-semibold" style={{ color: "#9a3214" }}>Where the layers disagree</h3>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[13px]" style={{ color: "var(--text-secondary)" }}>{p.conflicts.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            )}
          </>)}
          {effects.length > 0 && (
            <div className="mt-5">
              <h3 className="text-xs font-semibold">Hours until this home is unsafe in the heat</h3>
              <p className="mt-0.5 text-xs" style={muted}>
                As surveyed, and with one layer&rsquo;s fields reset to defaults.{costarShift != null && Math.abs(costarShift) >= 0.1 && ` CoStar moves this deadline by ${Math.abs(costarShift).toFixed(1)} h.`}
              </p>
              <div className="mt-2 grid gap-1.5">
                {effects.map(([label, h, color]) => (
                  <div key={label} className="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-2 text-[13px]" title={`${label}: ${h.toFixed(1)} h`}>
                    <span style={{ color: "var(--text-secondary)" }}>{label}</span>
                    <span className="h-2 rounded-r-[4px]" style={{ width: `${(h / top) * 100}%`, background: color }} />
                    <span className="tnum text-right">{h.toFixed(1)} h</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {image && (
            <figure className="mt-5">
              <img src={image} alt={`Vexcel aerial of ${detail?.name ?? "the building"}`} className="h-40 w-40 rounded-lg border object-cover" style={{ borderColor: "var(--border)" }} />
              <figcaption className="mt-1 text-xs" style={muted}>Vexcel ortho tile the aerial subagent read</figcaption>
            </figure>
          )}
        </section>
      </div>
    </div>
  );
}
