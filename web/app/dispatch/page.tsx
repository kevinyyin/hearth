"use client";

import Link from "next/link";
import { useState } from "react";
import { API, sendJson } from "@/lib/api";
import { EQUIPMENT, VEHICLES } from "@/lib/help";
import type { DispatchView } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const words = (s: string) => s.replace(/_/g, " ");
const card = "space-y-2 rounded-lg border p-4";
const cardStyle = { borderColor: "var(--border)", background: "var(--surface-1)" };
const muted = { color: "var(--text-muted)" };

/** Help requests as a dispatcher sees them. Nothing here needs a click unless code could not place a request. */
export default function DispatchPage() {
  const { data, error, refresh } = usePoll<DispatchView>(API ? "/api/dispatch" : null);
  const [failed, setFailed] = useState<string | null>(null);

  if (!API) return <p className="mx-auto max-w-2xl px-6 py-10 text-sm">This page needs the Hearth API.</p>;

  async function handled(patientId: string) {
    try {
      await sendJson("POST", `/api/dispatch/${patientId}/handled`);
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    }
    refresh();
  }

  const stuck = data?.requests.filter((r) => r.request.blocked && r.request.state === "waiting") ?? [];
  const queue = data?.requests.filter((r) => !(r.request.blocked && r.request.state === "waiting")) ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-4 px-6 py-10 pb-24">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Help requests</h1>
        <Link href="/start" className="text-xs underline underline-offset-2" style={{ color: "var(--text-secondary)" }}>Switch role</Link>
      </header>
      <p className="text-xs" style={muted}>
        Simulated patients. A resident&apos;s own request goes straight to a crew: a model orders the queue, code picks the crew and the
        drop-off. A person is asked only for the requests listed first.
      </p>
      {(failed ?? error) && <p role="alert" className="text-sm" style={{ color: "#d03b3b" }}>{failed ?? error}</p>}

      <section className={card} style={cardStyle}>
        <h2 className="text-sm font-semibold">Needs a person ({stuck.length})</h2>
        {stuck.length === 0 && <p className="text-sm" style={muted}>Nothing is waiting on a person.</p>}
        <ul className="space-y-3">
          {stuck.map(({ request: r, device, mobility, address }) => (
            <li key={r.patient_id} className="flex items-start justify-between gap-3 text-sm">
              <div>
                <p className="font-medium">{r.patient_id} · {words(device)} · {words(mobility)}</p>
                <p className="text-xs" style={muted}>{address ?? "No building on record"}</p>
                <p style={{ color: "#d03b3b" }}>{r.blocked}</p>
              </div>
              <button type="button" onClick={() => handled(r.patient_id)} className="shrink-0 rounded border px-3 py-1.5 text-xs font-medium"
                style={{ borderColor: "var(--border)" }}>
                Mark handled
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className={card} style={cardStyle}>
        <h2 className="text-sm font-semibold">Queue</h2>
        {queue.length === 0 && <p className="text-sm" style={muted}>No requests yet.</p>}
        <ol className="space-y-3">
          {queue.map(({ request: r, device, mobility }) => (
            <li key={r.patient_id} className="text-sm">
              <p className="font-medium">
                {r.patient_id} · {words(device)} · {words(mobility)} · <span style={{ color: "var(--text-secondary)" }}>{words(r.state)}</span>
              </p>
              {r.ranked_by && (
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {r.ranked_by === "model" ? `Model: ${r.reason}` : "Ordered by the risk-per-hour rule (the model did not answer)"}
                </p>
              )}
              {r.job && r.refuge && <p className="text-xs" style={muted}>{r.job.org_id} → {r.refuge.name} (not booked, power not verified)</p>}
            </li>
          ))}
        </ol>
      </section>

      <section className={card} style={cardStyle}>
        <h2 className="text-sm font-semibold">Crews</h2>
        {data?.crews.length === 0 && <p className="text-sm" style={muted}>No crew has set up yet.</p>}
        <ul className="space-y-1.5 text-sm">
          {data?.crews.map(({ crew, patient_id }) => (
            <li key={crew.crew_id}>
              <span className="font-medium">{crew.crew_id}</span> · {VEHICLES[crew.vehicle]}
              {crew.equipment.length ? ` · ${crew.equipment.map((e) => EQUIPMENT[e]).join(", ")}` : ""} ·{" "}
              <span style={muted}>{patient_id ? `with ${patient_id}` : crew.on_duty ? "free" : "off duty"}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
