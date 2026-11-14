"use client";

import { useEffect, useState } from "react";
import { getJson, sendJson } from "@/lib/api";
import type { StagingLot, StagingView } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";
import { usePoll } from "@/lib/usePoll";

const muted = { color: "var(--text-muted)" };
const secondary = { color: "var(--text-secondary)" };
const button = "rounded border px-3 py-1.5 text-xs font-medium";
const NEEDS_CALL = "Needs a call: owner permission; lot not verified clear";

/** Where the lot is and what CoStar says about it. The name is the address when CoStar has no building name. */
function Facts({ lot, basis }: { lot: StagingLot; basis: string }) {
  return (
    <>
      <p className="text-sm font-medium">
        {[lot.name, lot.property_type, lot.address === lot.name ? null : lot.address, `${lot.km} km from ${basis}`].filter(Boolean).join(" · ")}
      </p>
      <p className="text-xs" style={secondary}>
        CoStar: {lot.surface_spaces} surface spaces{lot.lot_acres === null ? "" : ` · ${lot.lot_acres} acres`} · existing
      </p>
    </>
  );
}

/** A real parking lot for crews to gather at, proposed from CoStar's parking data with a Vexcel aerial of the lot.
 *  Approve only records the dispatcher's pick: nobody has asked the owner, and the card says so. */
export default function StagingCard() {
  const { data, refresh } = usePoll<StagingView>("/api/staging");
  const [shown, setShown] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const options = data?.options ?? [];
  const chosen = data?.chosen ?? null;
  const lot = chosen ? null : options[shown % Math.max(options.length, 1)] ?? null;
  const image = useAuthedImage(lot ? `/api/buildings/${lot.building_id}/lot-image` : null);

  // the model's line is read only for the lot on show: it costs a vision call the first time
  const id = lot?.building_id ?? null;
  useEffect(() => {
    setNote(null);
    if (!id) return;
    let stale = false;
    getJson<{ note: string }>(`/api/buildings/${id}/lot-reading`).then((r) => !stale && setNote(r.note)).catch(() => {});
    return () => {
      stale = true;
    };
  }, [id]);

  async function choose(buildingId: string | null) {
    try {
      await sendJson("POST", "/api/staging", { building_id: buildingId });
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    }
    refresh();
  }

  return (
    <section className="space-y-2 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="text-sm font-semibold">{chosen ? "Staging lot" : "Staging lot · proposed"}</h2>
      {chosen && (
        <>
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm">
              Staging at {chosen.name}{chosen.address === chosen.name ? "" : `, ${chosen.address}`} (not confirmed with the owner)
            </p>
            <button type="button" onClick={() => choose(null)} className={`shrink-0 ${button}`} style={{ borderColor: "var(--border)" }}>Change</button>
          </div>
          {chosen.stale && <p className="text-xs" style={{ color: "#d03b3b" }}>A help request has opened in this lot&apos;s ZIP. Consider changing.</p>}
        </>
      )}
      {!chosen && !lot && (
        <p className="text-sm" style={muted}>No lot to propose yet. A lot is proposed once a resident asks for help or registers a home.</p>
      )}
      {lot && (
        <>
          <Facts lot={lot} basis={data?.basis ?? "open requests"} />
          {image ? (
            <figure className="space-y-1">
              {/* eslint-disable-next-line @next/next/no-img-element -- an object URL fetched with the password header */}
              <img src={image} alt="Aerial image of the lot, Vexcel" className="w-full max-w-sm rounded" />
              <figcaption className="text-xs" style={muted}>Vexcel aerial, 300 m across; capture date printed on the image</figcaption>
            </figure>
          ) : (
            <p className="text-xs" style={muted}>{image === undefined ? "Loading the aerial…" : "No aerial"}</p>
          )}
          {note && <p className="text-xs" style={secondary}>Model reading: {note}</p>}
          <p className="text-xs" style={muted}>{NEEDS_CALL}</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => choose(lot.building_id)} className="rounded px-3 py-1.5 text-xs font-medium text-white" style={{ background: "#1b7f4d" }}>
              Approve
            </button>
            {options.length > 1 && (
              <button type="button" onClick={() => setShown((i) => (i + 1) % options.length)} className={button} style={{ borderColor: "var(--border)" }}>
                Next option
              </button>
            )}
          </div>
        </>
      )}
      {failed && <p role="alert" className="text-xs" style={{ color: "#d03b3b" }}>{failed}</p>}
    </section>
  );
}
