"use client";

import { useState } from "react";
import { API } from "@/lib/api";
import type { RefugeProposal } from "@/lib/types";

/** A refuge proposal waiting on the dispatcher. Nothing is booked or sent until Approve; Reject needs a reason. */
export default function ProposalCard({ proposal, onDecided }: { proposal: RefugeProposal; onDecided: (p: RefugeProposal) => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/proposals/${proposal.proposal_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason: decision === "reject" ? reason : null }),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
      onDecided((await res.json()) as RefugeProposal);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-2 rounded-lg border p-3 text-xs" style={{ borderColor: "var(--border)" }}>
      <h4 className="font-semibold">Refuge proposal · {proposal.status}</h4>
      <ol className="space-y-1.5">
        {proposal.options.map((o) => (
          <li key={o.building_id}>
            <div className="font-medium">{o.name}</div>
            <div style={{ color: "var(--text-secondary)" }}>{o.reasons.join("; ")}</div>
            <div style={{ color: "var(--text-muted)" }}>Sources: {o.sources.join(", ") || "—"}</div>
          </li>
        ))}
      </ol>
      {proposal.status === "pending" ? (
        <div className="space-y-1.5">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (required to reject)"
            aria-label="Reason for rejecting"
            className="w-full rounded border px-2 py-1"
            style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
          />
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => decide("approve")} className="rounded px-3 py-1 font-medium text-white" style={{ background: "#1b7f4d" }}>
              Approve
            </button>
            <button type="button" disabled={busy || !reason.trim()} onClick={() => decide("reject")} className="rounded border px-3 py-1" style={{ borderColor: "var(--border)" }}>
              Reject
            </button>
          </div>
        </div>
      ) : (
        <p style={{ color: "var(--text-secondary)" }}>
          {proposal.status === "approved"
            ? proposal.call_id ? `Approved. Consent call started (${proposal.call_id}).` : `Approved. ${proposal.call_error ? `Call not started: ${proposal.call_error}` : ""}`
            : `Rejected: ${proposal.reason}. The agent will remember this.`}
        </p>
      )}
      {error && <p style={{ color: "#d03b3b" }}>{error}</p>}
    </section>
  );
}
