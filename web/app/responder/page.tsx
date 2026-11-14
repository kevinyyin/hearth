"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import AccessBrief from "@/components/AccessBrief";
import AerialPins from "@/components/AerialPins";
import CrewSetup from "@/components/CrewSetup";
import ScanPins from "@/components/ScanPins";
import { API, getJson, sendJson } from "@/lib/api";
import { EQUIPMENT, NEXT_ACTION, VEHICLES } from "@/lib/help";
import { getPersona, SIZES } from "@/lib/home";
import type { BuildingDetail, CrewJob, Home, Patient, RefugeOption } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const words = (s: string) => s.replace(/_/g, " ");
const card = "space-y-4 rounded-lg border p-4";
const cardStyle = { borderColor: "var(--border)", background: "var(--surface-1)" };
const green = "rounded px-4 py-2 text-sm font-medium text-white disabled:opacity-60";
const plain = "rounded border px-4 py-2 text-sm font-medium disabled:opacity-60";

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>{title}</h3>
      {children}
    </section>
  );
}

/** Where the job ends. Nothing is booked and nobody has checked the power, and the card says so. */
function Refuge({ refuge }: { refuge: RefugeOption }) {
  return (
    <Part title="Drop-off">
      <p className="text-sm font-medium">{refuge.name}</p>
      <ul className="list-disc pl-4 text-xs" style={{ color: "var(--text-secondary)" }}>{refuge.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
    </Part>
  );
}

/** One job: what the resident said about their device and home, on the same aerial image and scan, above the crew brief.
 *  A resident who never marked up their home still gets a card; it shows nothing they did not say. */
function JobCard({ patient, home, address, buildingId }: { patient: Patient; home: Home | null; address: string | null; buildingId: string | null }) {
  // undefined: still loading; null: the building detail (which carries the scan key and the brief) did not load
  const [detail, setDetail] = useState<BuildingDetail | null | undefined>(undefined);
  useEffect(() => {
    setDetail(undefined);
    if (!buildingId) return setDetail(null);
    getJson<BuildingDetail>(`/api/buildings/${buildingId}`).then(setDetail).catch(() => setDetail(null));
  }, [buildingId]);

  const cm = home && (home.size === "custom" ? home.size_cm : SIZES[home.size].cm);
  const size = home && `${home.size === "custom" ? "measured" : SIZES[home.size].label}${cm ? ` (${cm.join(" × ")} cm)` : ""}`;

  return (
    <article className={card} style={cardStyle}>
      <header>
        <h2 className="text-sm font-semibold">Simulated resident {patient.patient_id}</h2>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>{address ?? "No building on record"}</p>
      </header>
      <ul className="space-y-0.5 text-sm">
        <li>{words(patient.device)} · {words(patient.mobility)}</li>
        {home ? (
          <>
            <li>OK without it for {home.ok_without_h} hours</li>
            <li>Size: {size}</li>
            {home.backup_plan && <li>Backup plan: {home.backup_plan}</li>}
            {home.note && <li>Resident&apos;s note: {home.note}</li>}
          </>
        ) : (
          <li style={{ color: "var(--text-muted)" }}>This resident has not marked up their home.</li>
        )}
      </ul>
      {buildingId && (
        <Part title="Outside">
          <AerialPins imagePath={`/api/buildings/${buildingId}/image`} pins={home?.outside ?? []} />
        </Part>
      )}
      {home && (
        <Part title="Inside">
          {home.scan_id ? (
            <>
              {/* the key arrives with the building detail. Without it the scan cannot open, and the pins are still listed */}
              {detail !== undefined && <ScanPins scanId={home.scan_id} sdkKey={detail?.scan_sdk_key ?? null} pins={home.inside} />}
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                Sample unit from this building. The resident says their home is laid out like it.
              </p>
            </>
          ) : (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>The resident did not match a scan to their home.</p>
          )}
        </Part>
      )}
      {detail?.brief && <AccessBrief brief={detail.brief} scanShown={!!home?.scan_id} />}
    </article>
  );
}

/** The responder persona: set the crew up once, then one offer at a time, worked through to the drop-off. */
export default function ResponderPage() {
  const router = useRouter();
  const [crewId, setCrewId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const persona = getPersona();
    if (persona?.role !== "responder") return router.replace("/start");
    setCrewId(persona.id);
  }, [router]);

  const base = crewId ? `/api/crews/${encodeURIComponent(crewId)}` : null;
  const { data, error, refresh } = usePoll<CrewJob>(API && base ? `${base}/job` : null);

  if (!API) return <p className="mx-auto max-w-md px-6 py-10 text-sm">This page needs the Hearth API.</p>;

  async function send(method: "PUT" | "POST", path: string, body: unknown) {
    setSending(true);
    try {
      await sendJson(method, path, body);
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    }
    setSending(false);
    refresh();
  }

  const crew = data?.crew ?? null;
  const job = data?.job ?? null;
  // the press names the resident on the card, so a press on a card that has gone stale is refused, not applied to the next job
  const act = (action: string) => send("POST", `${base}/job`, { action, patient_id: job?.request.patient_id });
  const next = job ? NEXT_ACTION[job.request.state] : undefined;

  return (
    <div className="mx-auto max-w-md space-y-4 px-6 py-10 pb-24">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Jobs{crewId ? ` · ${crewId}` : ""}</h1>
        <Link href="/start" className="text-xs underline underline-offset-2" style={{ color: "var(--text-secondary)" }}>Switch role</Link>
      </header>
      {(failed ?? error) && <p role="alert" className="text-sm" style={{ color: "#d03b3b" }}>{failed ?? error}</p>}
      {!data && !error && <p className="text-sm" style={{ color: "var(--text-muted)" }}>Loading…</p>}

      {data && crewId && (!crew || editing) && (
        <CrewSetup crewId={crewId} crew={crew} onSaved={() => {
          setEditing(false);
          refresh();
        }} />
      )}

      {crew && !editing && (
        <section className="flex flex-wrap items-center justify-between gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
          <p>{VEHICLES[crew.vehicle]}{crew.equipment.length ? ` · ${crew.equipment.map((e) => EQUIPMENT[e]).join(", ")}` : ""}</p>
          <div className="flex gap-3">
            <button type="button" className="underline underline-offset-2"
              onClick={() => send("PUT", base!, { base_building_id: crew.base_building_id, vehicle: crew.vehicle, equipment: crew.equipment, on_duty: !crew.on_duty })}>
              {crew.on_duty ? "Go off duty" : "Go on duty"}
            </button>
            <button type="button" className="underline underline-offset-2" onClick={() => setEditing(true)}>Edit setup</button>
          </div>
        </section>
      )}

      {crew && !editing && !job && (
        <p className="rounded-lg border p-4 text-sm" style={{ ...cardStyle, color: "var(--text-muted)" }}>
          {crew.on_duty ? "On duty. Waiting for a job." : "Off duty. You will not be offered jobs."}
        </p>
      )}

      {job?.request.state === "offered" && (
        <article className={card} style={cardStyle}>
          <header>
            <p className="text-xs font-semibold" style={{ color: "#d03b3b" }}>New job</p>
            <h2 className="text-sm font-semibold">Simulated resident {job.patient.patient_id}</h2>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>{job.address ?? "No building on record"} · {job.km} km from you</p>
          </header>
          <ul className="space-y-0.5 text-sm">
            <li>{words(job.patient.device)} · {words(job.patient.mobility)}</li>
            <li>
              <span style={{ color: "var(--text-muted)" }}>Why now: </span>
              {job.request.ranked_by === "model" ? job.request.reason : "ordered by the risk-per-hour rule (the model did not answer)"}
            </li>
          </ul>
          {job.request.refuge && <Refuge refuge={job.request.refuge} />}
          <div className="flex gap-2">
            <button type="button" disabled={sending} className={green} style={{ background: "#1b7f4d" }} onClick={() => act("accept")}>Accept</button>
            <button type="button" disabled={sending} className={plain} style={{ borderColor: "var(--border)" }} onClick={() => act("decline")}>Decline</button>
          </div>
        </article>
      )}

      {job && job.request.state !== "offered" && (
        <>
          <section className={card} style={cardStyle}>
            {job.request.refuge && <Refuge refuge={job.request.refuge} />}
            {next && <button type="button" disabled={sending} className={green} style={{ background: "#1b7f4d" }} onClick={() => act(next.action)}>{next.label}</button>}
          </section>
          <JobCard key={job.patient.patient_id} patient={job.patient} home={job.home} address={job.address} buildingId={job.building_id} />
        </>
      )}
    </div>
  );
}
