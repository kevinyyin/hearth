"use client";

import { useEffect, useState } from "react";
import Button from "@/components/Button";
import { getJson, sendJson } from "@/lib/api";
import type { StagingLot } from "@/lib/types";
import { useAction } from "@/lib/useAction";
import { useAuthedImage } from "@/lib/useAuthedImage";

const muted = { color: "var(--text-muted)" };
const secondary = { color: "var(--text-secondary)" };
const NEEDS_CALL = "Needs a call: owner permission; lot not verified clear";

/** One staging lot, proposed from CoStar's parking data with a Vexcel aerial of the lot. Choose only records the
 *  dispatcher's pick: nobody has asked the owner, and the card says so. */
export default function StagingCard({ lot, chosen, basis, onChanged }: { lot: StagingLot; chosen: boolean; basis: string | null; onChanged: () => void }) {
  const [note, setNote] = useState<string | null>(null);
  const image = useAuthedImage(`/api/buildings/${lot.building_id}/lot-image`);
  const { busy, error, act } = useAction();

  // the model's line costs a vision call the first time, so it is read only for the lot on show
  useEffect(() => {
    setNote(null);
    let stale = false;
    getJson<{ note: string }>(`/api/buildings/${lot.building_id}/lot-reading`).then((r) => !stale && setNote(r.note)).catch(() => {});
    return () => {
      stale = true;
    };
  }, [lot.building_id]);

  const choose = (buildingId: string | null) =>
    act(buildingId ? "choose" : "clear", async () => {
      await sendJson("POST", "/api/staging", { building_id: buildingId });
      onChanged();
    });

  return (
    <div className="space-y-2">
      <h2 className="pr-8 text-base font-semibold">{lot.name}</h2>
      <p className="text-[13px]" style={muted}>
        {chosen ? "Crew staging lot, chosen (not confirmed with the owner)" : "Proposed crew staging lot"}
        {lot.address === lot.name ? "" : ` · ${lot.address}`}
      </p>
      <p className="text-[13px]" style={secondary}>
        {[lot.property_type.replace(/_/g, " "), `${lot.km} km from ${basis ?? "the households"}`].join(" · ")}
      </p>
      <p className="text-[13px]" style={secondary}>
        CoStar: {lot.surface_spaces} surface spaces{lot.lot_acres === null ? "" : ` · ${lot.lot_acres} acres`} · existing
      </p>
      {chosen && lot.stale && <p className="text-[13px]" style={{ color: "#9a3214" }}>A help request has opened in this lot&apos;s ZIP. Consider changing.</p>}
      {image ? (
        <figure className="space-y-1">
          {/* eslint-disable-next-line @next/next/no-img-element -- an object URL fetched with the password header */}
          <img src={image} alt="Aerial image of the lot, Vexcel" className="w-full rounded" />
          <figcaption className="text-xs" style={muted}>Vexcel aerial, 300 m across; capture date printed on the image</figcaption>
        </figure>
      ) : (
        <p className="text-xs" style={muted}>{image === undefined ? "Loading the aerial…" : "No aerial"}</p>
      )}
      {note && <p className="text-[13px]" style={secondary}>Model reading: {note}</p>}
      <p className="text-[13px]" style={muted}>{NEEDS_CALL}</p>
      <div className="flex gap-2 pt-1">
        {chosen ? (
          <Button disabled={!!busy} onClick={() => choose(null)}>{busy ? "Clearing…" : "Clear the choice"}</Button>
        ) : (
          <Button primary disabled={!!busy} onClick={() => choose(lot.building_id)}>{busy ? "Choosing…" : "Choose this lot"}</Button>
        )}
      </div>
      {error && <p role="alert" className="text-[13px]" style={{ color: "#9a3214" }}>{error}</p>}
    </div>
  );
}
