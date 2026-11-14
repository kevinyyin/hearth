"use client";

import { formatTick, stateColor } from "@/lib/snapshots";
import type { HearthEvent, PatientSnap } from "@/lib/types";

/** Backup hours are capped on the gauge; past a day of runway the exact number stops mattering. */
const GAUGE_MAX_HOURS = 24;

function BackupGauge({ hours }: { hours: number }) {
  const pct = Math.max(0, Math.min(hours / GAUGE_MAX_HOURS, 1)) * 100;
  const low = hours < 4;

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Backup left
        </span>
        <span className="tnum text-sm font-medium">{hours.toFixed(1)} h</span>
      </div>
      <div
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full"
        style={{ background: "var(--grid)" }}
        role="meter"
        aria-valuenow={hours}
        aria-valuemin={0}
        aria-valuemax={GAUGE_MAX_HOURS}
        aria-label="Backup hours left"
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: low ? "#d03b3b" : "#2a78d6" }}
        />
      </div>
      {low && (
        <p className="mt-1 text-xs" style={{ color: "#d03b3b" }}>
          Under four hours of runway.
        </p>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  );
}

function eventLine(e: HearthEvent): string | null {
  const d = e.data as Record<string, unknown>;
  if (e.type === "state_change") return `${d.from} → ${d.to}${d.why ? ` — ${d.why}` : ""}`;
  if (e.type === "job_created") return `${d.kind} job ${d.job_id} for ${d.org_id}`;
  if (e.type === "job_accepted") return `job ${d.job_id} accepted by crew ${d.crew_id}`;
  if (e.type === "escalation") return String(d.why ?? "escalated");
  if (e.type === "power_lost") return d.zip ? `zip ${d.zip}` : null;
  const keys = Object.keys(d);
  return keys.length ? keys.map((k) => `${k} ${String(d[k])}`).join(", ") : null;
}

export default function PatientPanel({
  patient,
  events,
  onClose,
}: {
  patient: PatientSnap;
  events: HearthEvent[];
  onClose: () => void;
}) {
  const mine = events
    .filter((e) => e.patient_id === patient.id)
    .slice()
    .sort((a, b) => a.t.localeCompare(b.t));

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-start justify-between border-b px-5 py-4"
        style={{ borderColor: "var(--border)" }}
      >
        <div>
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block size-3 rounded-full"
              style={{ background: stateColor(patient.state) }}
            />
            <h2 className="text-sm font-semibold">Patient {patient.id}</h2>
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
            Simulated · {patient.building_id ?? "no building match"}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close patient panel"
          className="rounded-md px-2 py-0.5 text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          ✕
        </button>
      </div>

      <div className="space-y-5 px-5 py-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Device" value={patient.device.replace(/_/g, " ")} />
          <Field label="State" value={patient.state.replace(/_/g, " ")} />
          <Field label="Indoor temperature" value={`${patient.indoor_temp_c.toFixed(1)} °C`} />
          <Field label="Power" value={patient.unpowered ? "Out" : "On"} />
        </div>

        <BackupGauge hours={patient.backup_hours} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-t px-5 py-4" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-xs font-semibold tracking-wide uppercase" style={{ color: "var(--text-muted)" }}>
          Events
        </h3>
        {mine.length === 0 ? (
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
            No events for this patient in this run.
          </p>
        ) : (
          <ol className="mt-3 space-y-3">
            {mine.map((e, i) => {
              const line = eventLine(e);
              return (
                <li key={`${e.t}-${e.type}-${i}`} className="text-sm">
                  <div className="tnum text-xs" style={{ color: "var(--text-muted)" }}>
                    {formatTick(e.t)}
                  </div>
                  <div className="font-medium">{e.type.replace(/_/g, " ")}</div>
                  {line && (
                    <div style={{ color: "var(--text-secondary)" }}>{line}</div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
