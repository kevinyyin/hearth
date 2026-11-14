"use client";

import { useCallback, useEffect, useState } from "react";
import AccessBrief from "@/components/AccessBrief";
import AgentTrace from "@/components/AgentTrace";
import ProposalCard from "@/components/ProposalCard";
import { API, getJson } from "@/lib/api";
import { reduceTrace, streamEvents } from "@/lib/sse";
import { PROFILE_FIELDS, type BuildingDetail, type RefugeProposal, type TraceEvent } from "@/lib/types";

const MISSING_WORDS: Record<string, string> = {
  costar: "Not in CoStar's records",
  vexcel: "No aerial data",
  matterport: "No 3D scan: entrance, stairs and elevator unverified",
};
const LAYER_NAMES: Record<string, string> = { costar: "CoStar", vexcel: "Vexcel", matterport: "Matterport" };

const show = (v: unknown): string =>
  v === null || v === undefined ? "unknown"
  : typeof v === "boolean" ? (v ? "yes" : "no")
  : Array.isArray(v) ? v.map((r) => (r && typeof r === "object" ? Object.values(r).filter((x) => x != null).join(" ") : String(r))).join("; ")
  : String(v);

/** The building agent for one building: aerial tile, scan, live trace, sourced profile, unsafe-time by layer, access brief,
 *  and (for a patient) the refuge proposal the dispatcher approves or rejects. */
export default function BuildingPanel({ buildingId, patientId }: { buildingId: string; patientId?: string }) {
  const [detail, setDetail] = useState<BuildingDetail | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [refugeEvents, setRefugeEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState<"survey" | "refuge" | null>(null);
  const [proposal, setProposal] = useState<RefugeProposal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getJson<BuildingDetail>(`/api/buildings/${buildingId}`).then(setDetail).catch((e) => setError(String(e)));
  }, [buildingId]);
  useEffect(() => {
    setDetail(null); setEvents([]); setRefugeEvents([]); setProposal(null); setError(null);
    load();
  }, [load]);

  async function run(kind: "survey" | "refuge") {
    setRunning(kind); setError(null);
    const sink = kind === "survey" ? setEvents : setRefugeEvents;
    sink([]);
    try {
      const path = kind === "survey" ? `/api/buildings/${buildingId}/survey?fresh=true` : `/api/patients/${patientId}/propose`;
      await streamEvents(path, kind === "refuge" ? { method: "POST" } : undefined, (e) => {
        sink((prev) => [...prev, e]);
        if (e.kind === "interrupt" && e.data.proposal) setProposal(e.data.proposal as RefugeProposal);
      });
      if (kind === "survey") load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(null);
    }
  }

  const trace = reduceTrace(events);
  // after a run, show what that run produced (a failed run shows its default-backed profile); otherwise the stored, cached one
  const failed = trace.done && !!trace.error;
  const p = failed ? trace.profile : detail?.profile;
  return (
    <div className="space-y-3 border-t p-4" style={{ borderColor: "var(--border)" }}>
      <div>
        <h3 className="text-sm font-semibold">{detail?.name ?? buildingId}</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>{detail?.address}</p>
        {p?.cached && !trace.done && <span className="mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: "var(--grid)" }}>cached</span>}
      </div>
      {detail && API && <img src={`${API}${detail.image_url}`} alt="Top-down aerial image of the building (Vexcel)" className="w-full rounded" />}
      {detail?.embed_url && (
        <iframe src={detail.embed_url} title="Matterport scan" className="h-48 w-full rounded border-0" allow="xr-spatial-tracking; fullscreen" />
      )}
      <button type="button" disabled={!!running} onClick={() => run("survey")} className="rounded border px-3 py-1 text-xs font-medium" style={{ borderColor: "var(--border)" }}>
        {running === "survey" ? "Surveying…" : p ? "Survey again" : "Survey building"}
      </button>
      <AgentTrace view={trace} running={running === "survey"} />

      {p && (
        <>
          {!failed && detail?.hours_to_unsafe != null && (
            <section className="text-xs">
              <h4 className="font-semibold" style={{ color: "var(--text-muted)" }}>Unsafe without power (at 35 °C outside, heuristic)</h4>
              <p className="tnum text-sm font-medium">in {detail.hours_to_unsafe.toFixed(1)} hours</p>
              {detail.layer_effects && (
                <ul style={{ color: "var(--text-secondary)" }}>
                  {Object.entries(detail.layer_effects).map(([layer, h]) => (
                    <li key={layer} className="tnum">without {LAYER_NAMES[layer]}: {h.toFixed(1)} h</li>
                  ))}
                </ul>
              )}
            </section>
          )}
          <table className="w-full text-xs">
            <thead><tr style={{ color: "var(--text-muted)" }}><th className="text-left font-normal">Field</th><th className="text-left font-normal">Value</th><th className="text-left font-normal">Source</th><th className="text-right font-normal">Conf.</th></tr></thead>
            <tbody>
              {PROFILE_FIELDS.filter((f) => p[f]).map((f) => (
                <tr key={f} style={{ color: p[f].source === "default" ? "var(--text-muted)" : "var(--text-primary)" }}>
                  <td>{f.replace(/_/g, " ")}</td><td>{show(p[f].value)}</td><td>{p[f].source}</td><td className="tnum text-right">{p[f].confidence.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {p.layers_missing.length > 0 && (
            <ul className="text-xs" style={{ color: "#b4541a" }}>{p.layers_missing.map((l) => <li key={l}>{MISSING_WORDS[l] ?? l}</li>)}</ul>
          )}
          {p.conflicts.length > 0 && events.length === 0 && (
            <ul className="list-disc pl-4 text-xs" style={{ color: "#b4541a" }}>{p.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>
          )}
          {!failed && detail?.brief && <AccessBrief brief={detail.brief} />}
        </>
      )}

      {patientId && (
        <>
          <button type="button" disabled={!!running} onClick={() => run("refuge")} className="rounded border px-3 py-1 text-xs font-medium" style={{ borderColor: "var(--border)" }}>
            {running === "refuge" ? "Finding a refuge…" : "Find a refuge"}
          </button>
          <AgentTrace view={reduceTrace(refugeEvents)} running={running === "refuge"} />
          {proposal && <ProposalCard proposal={proposal} onDecided={setProposal} />}
        </>
      )}
      {error && <p className="text-xs" style={{ color: "#d03b3b" }}>{error}</p>}
    </div>
  );
}
