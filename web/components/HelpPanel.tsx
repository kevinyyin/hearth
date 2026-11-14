"use client";

import { useState } from "react";
import { sendJson } from "@/lib/api";
import { clock, fillWindow } from "@/lib/help";
import type { Tracker } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const LIVE = ["waiting", "offered", "accepted", "at_door", "riding"];

/** The resident's two buttons and their tracker. Every line shown is fixed text the API chose by the request's state. */
export default function HelpPanel({ patientId }: { patientId: string }) {
  const path = `/api/patients/${patientId}/help`;
  const { data, error, refresh } = usePoll<Tracker>(path);
  const [failed, setFailed] = useState<string | null>(null);

  async function send(what: "help" | "safe") {
    try {
      await sendJson<Tracker>("POST", `/api/patients/${patientId}/${what}`);
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    }
    refresh();
  }

  const state = data?.state ?? null;
  const live = state !== null && LIVE.includes(state);
  const withCrew = state === "riding" || state === "dropped_off";

  return (
    <section className="space-y-3 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <div className="flex flex-wrap items-center gap-2">
        {!live && (
          <button type="button" onClick={() => send("help")} className="rounded px-4 py-2 text-sm font-semibold text-white" style={{ background: "#d03b3b" }}>
            I need help
          </button>
        )}
        {!withCrew && (
          <button type="button" onClick={() => send("safe")} className="rounded border px-4 py-2 text-sm font-medium"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}>
            {live ? "I'm safe, cancel" : "I'm safe"}
          </button>
        )}
      </div>

      {data && data.steps.length > 0 && (
        <ol className="space-y-1.5" aria-label="Your request">
          {data.steps.map((s, i) => (
            <li key={i} className="flex items-baseline gap-2 text-sm" style={{ color: s.done ? "var(--text-primary)" : "var(--text-muted)" }}>
              <span aria-hidden="true" style={{ color: s.done ? "#1b7f4d" : "var(--text-muted)" }}>{s.done ? "●" : "○"}</span>
              <span className="flex-1">{fillWindow(s.text, data.window)}</span>
              {s.at && <time dateTime={s.at} className="text-xs" style={{ color: "var(--text-muted)" }}>{clock(s.at)}</time>}
            </li>
          ))}
        </ol>
      )}
      {data?.refuge_note && <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{data.refuge_note}</p>}
      {(failed ?? error) && <p role="alert" className="text-sm" style={{ color: "#d03b3b" }}>{failed ?? error}</p>}
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Simulated request. In an emergency call 911.</p>
    </section>
  );
}
