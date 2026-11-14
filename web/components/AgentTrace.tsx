"use client";

import type { TraceView } from "@/lib/sse";

const STATUS_MARK: Record<string, string> = { completed: "✓", in_progress: "…", pending: "○" };

/** The deep agent's live work: its to-do plan, one row per layer subagent, files written, conflicts found. */
export default function AgentTrace({ view, running }: { view: TraceView; running: boolean }) {
  if (!running && view.todos.length === 0 && view.subagents.length === 0) return null;
  return (
    <div className="space-y-3 text-xs">
      {view.todos.length > 0 && (
        <section>
          <h4 className="mb-1 font-semibold" style={{ color: "var(--text-muted)" }}>Agent plan</h4>
          <ul className="space-y-0.5">
            {view.todos.map((t, i) => (
              <li key={i} style={{ color: t.status === "pending" ? "var(--text-muted)" : "var(--text-primary)" }}>
                <span className="mr-1.5 inline-block w-3">{STATUS_MARK[t.status] ?? "○"}</span>
                {t.content}
              </li>
            ))}
          </ul>
        </section>
      )}
      {view.subagents.length > 0 && (
        <section>
          <h4 className="mb-1 font-semibold" style={{ color: "var(--text-muted)" }}>Subagents</h4>
          <ul className="space-y-1.5">
            {view.subagents.map((s) => (
              <li key={s.name} className="rounded border px-2 py-1.5" style={{ borderColor: "var(--border)" }}>
                <div className="flex justify-between font-medium">
                  <span>{s.name}</span>
                  <span style={{ color: "var(--text-muted)" }}>{s.steps} steps{s.asks > 1 ? ` · ${s.asks - 1} follow-up` : ""}</span>
                </div>
                {s.last && <p className="mt-0.5 line-clamp-3" style={{ color: "var(--text-secondary)" }}>{s.last}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {view.files.length > 0 && (
        <p style={{ color: "var(--text-muted)" }}>Saved: {view.files.map((f) => f.split("/").pop()).join(", ")}</p>
      )}
      {view.conflicts.length > 0 && (
        <section>
          <h4 className="mb-1 font-semibold" style={{ color: "#b4541a" }}>Layers disagree</h4>
          <ul className="list-disc space-y-0.5 pl-4">{view.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </section>
      )}
      {running && !view.done && <p style={{ color: "var(--text-muted)" }}>Working…</p>}
      {view.error && <p style={{ color: "#d03b3b" }}>{view.error}</p>}
    </div>
  );
}
