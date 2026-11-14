"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import AccessBrief from "@/components/AccessBrief";
import AerialPins from "@/components/AerialPins";
import { PeopleList } from "@/components/PeopleFields";
import ScanPins from "@/components/ScanPins";
import { API, getJson } from "@/lib/api";
import { getPersona, SIZES } from "@/lib/home";
import type { BuildingDetail, HomeRow } from "@/lib/types";

const words = (s: string) => s.replace(/_/g, " ");

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>{title}</h3>
      {children}
    </section>
  );
}

/** One job: what the resident said about their device and home, on the same aerial image and scan, above the crew brief. */
function JobCard({ row }: { row: HomeRow }) {
  const { home, patient } = row;
  // undefined: still loading; null: the building detail (which carries the scan key and the brief) did not load
  const [detail, setDetail] = useState<BuildingDetail | null | undefined>(undefined);
  useEffect(() => {
    setDetail(undefined);
    getJson<BuildingDetail>(`/api/buildings/${home.building_id}`).then(setDetail).catch(() => setDetail(null));
  }, [home.building_id]);

  const cm = home.size === "custom" ? home.size_cm : SIZES[home.size].cm;
  const size = `${home.size === "custom" ? "measured" : SIZES[home.size].label}${cm ? ` (${cm.join(" × ")} cm)` : ""}`;

  return (
    <article className="space-y-4 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <header>
        <h2 className="text-sm font-semibold">Simulated resident {patient.patient_id}</h2>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>{row.address}</p>
      </header>
      <ul className="space-y-0.5 text-sm">
        <li>{words(patient.device)} · {words(patient.mobility)}</li>
        <li>OK without it for {home.ok_without_h} hours</li>
        <li>Size: {size}</li>
        {home.backup_plan && <li>Backup plan: {home.backup_plan}</li>}
        {home.note && <li>Resident&apos;s note: {home.note}</li>}
      </ul>
      {/* who is already there comes before how to get in */}
      <Part title="At home with the resident">
        {home.helpers.length > 0 ? <PeopleList people={home.helpers} />
          : <p className="text-xs" style={{ color: "var(--text-muted)" }}>The resident listed no one at home.</p>}
      </Part>
      <Part title="Outside">
        <AerialPins imagePath={`/api/buildings/${home.building_id}/image`} pins={home.outside} />
      </Part>
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
      {home.contacts.length > 0 && (
        <Part title="People to contact">
          <PeopleList people={home.contacts} />
        </Part>
      )}
      {detail?.brief && <AccessBrief brief={detail.brief} scanShown={!!home.scan_id} />}
    </article>
  );
}

/** The responder persona's jobs: every resident who has saved a home markup (dispatch comes in a later slice). */
export default function ResponderPage() {
  const router = useRouter();
  const [crew, setCrew] = useState<string | null>(null);
  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const persona = getPersona();
    if (persona?.role !== "responder") return router.replace("/start");
    setCrew(persona.id);
    if (API) getJson<HomeRow[]>("/api/homes").then(setRows).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [router]);

  if (!API) return <p className="mx-auto max-w-md px-6 py-10 text-sm">This page needs the Hearth API.</p>;
  const job = rows?.find((r) => r.home.patient_id === selected);

  return (
    <div className="mx-auto max-w-md space-y-4 px-6 py-10 pb-24">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Jobs{crew ? ` · ${crew}` : ""}</h1>
        <Link href="/start" className="text-xs underline underline-offset-2" style={{ color: "var(--text-secondary)" }}>Switch role</Link>
      </header>
      {error && <p className="text-sm" style={{ color: "#d03b3b" }}>{error}</p>}
      {rows?.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No resident has marked up a home yet.</p>}
      <ul className="space-y-1.5">
        {rows?.map((r) => (
          <li key={r.home.patient_id}>
            <button
              type="button"
              aria-pressed={selected === r.home.patient_id}
              onClick={() => setSelected(r.home.patient_id)}
              className="w-full rounded border px-3 py-2 text-left text-sm"
              style={{ borderColor: selected === r.home.patient_id ? "var(--text-primary)" : "var(--border)", background: "var(--surface-1)" }}
            >
              {r.home.patient_id} · {words(r.patient.device)} · {r.address}
            </button>
          </li>
        ))}
      </ul>
      {job && <JobCard key={job.home.patient_id} row={job} />}
    </div>
  );
}
