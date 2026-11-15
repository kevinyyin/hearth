"use client";

import { useEffect, useRef, useState } from "react";
import { LAYER_NAMES, show } from "@/components/BuildingPanel";
import Button from "@/components/Button";
import ScanPins from "@/components/ScanPins";
import { getJson, sendJson } from "@/lib/api";
import { clock, type Household, hoursOf, refugeRun, words } from "@/lib/dispatch";
import type { BuildingDetail, DispatchView, ShelterSite } from "@/lib/types";
import { useAction } from "@/lib/useAction";
import { useAuthedImage } from "@/lib/useAuthedImage";

const muted = { color: "var(--text-muted)" };
const LIVE = ["waiting", "offered", "accepted", "at_door", "riding"];
// the building fields a crew asks about first, as the card names them
const FIELDS = [["floors", "Floors"], ["elevator_count", "Elevators"], ["step_free_entrance", "Step-free entrance"], ["entrance_steps", "Steps at the entrance"],
  ["van_dropoff", "Van drop-off"], ["min_door_width_m", "Narrowest door (m)"], ["hallway_width_m", "Hallway (m)"], ["unit_type", "Unit type"]] as const;

function Heading({ children }: { children: string }) {
  return <h3 className="mt-4 mb-1 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>{children}</h3>;
}

function Fact({ left, right, chip }: { left: string; right?: string; chip?: string }) {
  return (
    <li className="flex justify-between gap-3">
      <span>{left}</span>
      {right && <span className="text-right" style={{ color: "var(--text-secondary)" }}>{right}</span>}
      {chip && <span className="self-center whitespace-nowrap rounded-full border px-1.5 text-[11px]" style={{ borderColor: "var(--border)", ...muted }}>{chip}</span>}
    </li>
  );
}

/** One aerial-search lead. Nothing about it is verified, so it is a place to phone, never a proposal. */
function Lead({ site }: { site: ShelterSite }) {
  const image = useAuthedImage(`/api/shelter-tile?lat=${site.lat}&lon=${site.lon}`);
  return (
    <li className="grid grid-cols-[44px_1fr] items-center gap-2">
      {image
        // eslint-disable-next-line @next/next/no-img-element -- an object URL fetched with the password header
        ? <img src={image} alt={`Aerial of the site, Vexcel: looks like ${site.looks_like}`} className="h-11 w-11 rounded-md object-cover" />
        : <span className="h-11 w-11 rounded-md" style={{ background: "var(--grid)" }} aria-hidden />}
      <span>
        {site.costar ? site.costar.name : `Looks like a ${site.looks_like}`}
        <br />
        <span className="tnum" style={muted}>{site.km.toFixed(1)} km · {site.zip} · call to confirm</span>
      </span>
    </li>
  );
}

/** A household: what the call said, what the agents found about the building, and where to take them. */
export default function HouseholdCard({ h, view, focus, onClose, onChanged }: {
  h: Household;
  view: DispatchView;
  focus?: "leads";
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<BuildingDetail | null>(null);
  const [plan, setPlan] = useState(false);
  const leads = useRef<HTMLDivElement>(null);
  const { busy, error, act } = useAction();
  const r = h.request;
  const home = h.home;
  const survey = view.agents.find((a) => a.run_id === `survey-${h.buildingId}`);
  const search = refugeRun(view, h.id);
  const sites = search?.result.shelter_sites ?? [];

  // read again when a survey of this building ends, so its profile shows
  useEffect(() => {
    setDetail(null);
    if (h.buildingId) getJson<BuildingDetail>(`/api/buildings/${h.buildingId}`).then(setDetail).catch(() => setDetail(null));
  }, [h.buildingId, survey?.status]);
  useEffect(() => {
    if (focus === "leads") leads.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focus, sites.length]);

  const p = detail?.profile;
  const facts = p ? FIELDS.filter(([f]) => p[f] && p[f].source !== "default" && p[f].value !== null) : [];
  const scan = home?.scan_id ?? null;
  const title = `${h.address?.split(",")[0] ?? "Address not on record"}${home?.unit ? `, apt ${home.unit}` : ""}`;

  return (
    <div role="dialog" aria-label={title} className="relative">
      <button type="button" onClick={onClose} aria-label="Close" className="absolute -top-1 -right-1 rounded-md p-1 hover:bg-[var(--surface-2)]" style={muted}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      </button>
      <h2 className="pr-8 text-base font-semibold">{title}</h2>
      <p className="mt-0.5 text-[13px]" style={muted}>
        {[home?.source === "phone" && home.said_at && `Registered by phone ${clock(home.said_at)}`, r?.times.waiting && `asked for help ${clock(r.times.waiting)}`]
          .filter(Boolean).join(" · ") || "Simulated resident on record"}
      </p>

      <Heading>{home?.source === "phone" ? "From the call" : "On record"}</Heading>
      <ul className="grid gap-[3px] text-[13px]">
        <Fact left={home?.device_name || words(h.patient.device)} right={`${hoursOf(h)} h of backup`} />
        <Fact left={`Floor ${h.patient.floor}${home?.complex_building ? `, building ${home.complex_building}` : ""}`} right={home?.room ? `machine: ${home.room}` : words(h.patient.mobility)} />
        {home?.door && <Fact left="Door" right={home.door} />}
      </ul>

      <Heading>The building, researched by the agents</Heading>
      {survey?.status === "running" ? <p className="text-[13px]" style={muted}>Agents researching…</p>
        : facts.length ? (
          <ul className="grid gap-[3px] text-[13px]">
            {facts.map(([f, label]) => <Fact key={f} left={`${label}: ${show(p![f].value)}`} chip={LAYER_NAMES[p![f].source]} />)}
          </ul>
        ) : <p className="text-[13px]" style={muted}>{survey?.status === "failed" ? `The survey failed: ${survey.result.error}` : "Not researched yet."}</p>}

      <Heading>Where to take them</Heading>
      <div ref={leads} className="scroll-mt-4">
        {r && (r.refuge ?? r.refuge_pick) ? (
          <p className="text-[13px]">
            {(r.refuge ?? r.refuge_pick)!.name} <span style={muted}>· {r.refuge_pick ? "approved by a dispatcher; " : ""}not booked, power not verified</span>
          </p>
        ) : r?.state === "waiting" && r.blocked ? (
          <>
            <p className="text-[13px]" style={{ color: "#9a3214" }}>{r.blocked.charAt(0).toUpperCase() + r.blocked.slice(1)}.</p>
            {search?.status === "running" && <p className="text-[13px]" style={muted}>The refuge agent is searching…</p>}
            {sites.length > 0 && <ul className="mt-1 grid gap-1.5 text-[13px]">{sites.map((s) => <Lead key={`${s.lat},${s.lon}`} site={s} />)}</ul>}
          </>
        ) : (
          <p className="text-[13px]" style={muted}>{!r ? "No help asked for yet." : r.state === "handled" ? "A dispatcher has taken this over." : "No drop-off yet."}</p>
        )}
      </div>

      {plan && (scan ? (
        <div className="mt-3">
          <ScanPins scanId={scan} sdkKey={detail?.scan_sdk_key ?? null} pins={home?.inside ?? []} view="floorplan" route />
        </div>
      ) : detail?.embed_url && (
        <iframe src={detail.embed_url} title="3D scan of the building" className="mt-3 h-48 w-full rounded border-0" allow="xr-spatial-tracking; fullscreen" />
      ))}

      <div className="mt-4 flex flex-wrap gap-2">
        {r && LIVE.includes(r.state) && (
          <Button primary disabled={!!busy} onClick={() => act("take", async () => { await sendJson("POST", `/api/dispatch/${h.id}/handled`); onChanged(); })}>
            {busy ? "Taking over…" : "Take over"}
          </Button>
        )}
        {(scan || detail?.embed_url) && (
          <Button onClick={() => setPlan((v) => !v)} aria-expanded={plan}>{plan ? "Close the floor plan" : "Open the floor plan"}</Button>
        )}
      </div>
      {error && <p role="alert" className="mt-1 text-[13px]" style={{ color: "#9a3214" }}>{error}</p>}
    </div>
  );
}
