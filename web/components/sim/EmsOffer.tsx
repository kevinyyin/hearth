"use client";

import { HELP_REQUEST, RESIDENT } from "@/lib/simulation";

/**
 * The offer a responder sees, in the shape the crew lane already uses: an offer
 * is the one state with two ways out, so it is the only place the simulation
 * waits for a person. Declining is drawn but disabled — the run always accepts.
 */
export default function EmsOffer({
  onAccept,
  accepted,
}: {
  onAccept: () => void;
  accepted: boolean;
}) {
  return (
    <div
      className="rounded-xl border-2 p-5 shadow-lg"
      style={{ background: "var(--surface-1)", borderColor: "var(--accent, #a8441a)" }}
      role="group"
      aria-label="Incoming job offer"
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <p
            className="mb-1 text-[11px] font-semibold tracking-wide uppercase"
            style={{ color: "var(--accent, #a8441a)" }}
          >
            {accepted ? "Job accepted" : "New job — 30s to respond"}
          </p>
          <h3 className="text-lg font-semibold">{HELP_REQUEST.summary}</h3>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            {RESIDENT.buildingLabel} · 2.4 km · about 11 min
          </p>
        </div>
        <span
          className="tnum shrink-0 rounded-full px-3 py-1 text-sm font-semibold"
          style={{ background: "#f6e0d6", color: "#7a2e12" }}
        >
          2 h 40 m left
        </span>
      </div>

      <dl className="mb-4 grid gap-x-5 gap-y-2 sm:grid-cols-2">
        {HELP_REQUEST.details.map((d) => (
          <div key={d.label}>
            <dt className="text-[11px] tracking-wide uppercase" style={{ color: "var(--text-muted)" }}>
              {d.label}
            </dt>
            <dd className="m-0 text-sm" style={{ color: "var(--text-primary)" }}>
              {d.value}
            </dd>
          </div>
        ))}
      </dl>

      {accepted ? (
        <p
          className="rounded-lg px-4 py-3 text-sm font-medium"
          style={{ background: "#def0e6", color: "#0b5c3e" }}
        >
          Accepted. The resident's own markup is now on the job.
        </p>
      ) : (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onAccept}
            className="flex-1 rounded-lg px-4 py-3 text-sm font-semibold"
            style={{ background: "var(--text-primary)", color: "var(--surface-0)", minHeight: 48 }}
          >
            Accept
          </button>
          <button
            type="button"
            disabled
            title="The simulation always accepts"
            className="rounded-lg border px-4 py-3 text-sm font-medium opacity-50"
            style={{ borderColor: "var(--border)", color: "var(--text-secondary)", minHeight: 48 }}
          >
            Decline
          </button>
        </div>
      )}
    </div>
  );
}
