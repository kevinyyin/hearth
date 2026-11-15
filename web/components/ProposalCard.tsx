"use client";

import { useState } from "react";
import Button from "@/components/Button";
import { sendJson } from "@/lib/api";
import type { RefugeProposal } from "@/lib/types";
import { useAction } from "@/lib/useAction";

/** A refuge proposal waiting on the dispatcher. Nothing is booked or sent until Approve, which makes the first option the
 *  request's drop-off; Reject asks for a reason, which the refuge agent remembers. */
export default function ProposalCard({ proposal, title, onDecided }: { proposal: RefugeProposal; title: string; onDecided: () => void }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const { busy, error, act } = useAction();
  const best = proposal.options[0];

  const decide = (decision: "approve" | "reject") =>
    act(decision, async () => {
      await sendJson("POST", `/api/proposals/${proposal.proposal_id}/decision`, { decision, reason: decision === "reject" ? reason.trim() : null });
      onDecided();
    });

  return (
    <div className="py-2">
      <p className="font-semibold">{title}</p>
      <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
        Proposed by the refuge agent · {best ? best.reasons.slice(0, 3).join(" · ") : "no option"}
        {proposal.options.length > 1 && ` · ${proposal.options.length - 1} more option${proposal.options.length > 2 ? "s" : ""}`}
      </p>
      {rejecting && (
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why not? The agent will remember." aria-label="Reason for rejecting"
          autoFocus className="mt-2 w-full rounded-[7px] border px-2 py-1.5 text-[13px]" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }} />
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {rejecting ? (
          <>
            <Button primary disabled={!!busy || !reason.trim()} onClick={() => decide("reject")}>{busy === "reject" ? "Rejecting…" : "Reject with this reason"}</Button>
            <Button disabled={!!busy} onClick={() => setRejecting(false)}>Cancel</Button>
          </>
        ) : (
          <>
            <Button primary disabled={!!busy || !best} onClick={() => decide("approve")}>{busy === "approve" ? "Approving…" : "Approve"}</Button>
            <Button disabled={!!busy} onClick={() => setRejecting(true)}>Reject</Button>
          </>
        )}
      </div>
      {error && <p role="alert" className="mt-1 text-[13px]" style={{ color: "#9a3214" }}>{error}</p>}
    </div>
  );
}
