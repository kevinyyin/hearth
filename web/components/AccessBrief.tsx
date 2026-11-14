"use client";

import type { AccessBrief as Brief } from "@/lib/types";

/** One screen for a crew. Built only from layer-sourced fields; the scan shows common areas, never a resident's unit. */
export default function AccessBrief({ brief }: { brief: Brief }) {
  const rows: [string, string | null][] = [["Stop at", brief.stop_at], ["Entrance", brief.entrance], ["Widths", brief.widths]];
  return (
    <section className="space-y-1 text-xs">
      <h4 className="font-semibold" style={{ color: "var(--text-muted)" }}>Crew access brief</h4>
      {rows.map(([k, v]) => (
        <p key={k}><span style={{ color: "var(--text-muted)" }}>{k}: </span>{v ?? <em style={{ color: "var(--text-muted)" }}>not shown by any layer</em>}</p>
      ))}
      {brief.route.length > 0 && (
        <ol className="list-decimal pl-4" style={{ color: "var(--text-secondary)" }}>{brief.route.map((r, i) => <li key={i}>{r}</li>)}</ol>
      )}
      {brief.missing.includes("matterport") && <p style={{ color: "var(--text-muted)" }}>No 3D scan: the route inside is not shown.</p>}
      <p style={{ color: "var(--text-muted)" }}>Scans show common areas and model units, not the patient's own rooms.</p>
    </section>
  );
}
