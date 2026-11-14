"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import AerialPins from "@/components/AerialPins";
import Choice from "@/components/Choice";
import HelpPanel from "@/components/HelpPanel";
import { API, getJson, putJson } from "@/lib/api";
import PeopleFields from "@/components/PeopleFields";
import ScanPins from "@/components/ScanPins";
import { currentOutside, emptyHome, getPersona, OUTSIDE_KINDS, PIN_COLOR, PIN_LABEL, SIZES, withBuilding, withDefaultScan } from "@/lib/home";
import type { BuildingDetail, Home, InsideKind, OutsideKind, Patient, SizeId } from "@/lib/types";

type BuildingRow = { building_id: string; name: string | null; address: string };

const INSIDE_KINDS: InsideKind[] = ["machine", "blocked", "route"]; // machine first: it is what the page opens on
const input = "mt-1 w-full rounded border px-3 py-2 text-sm";
const inputStyle = { borderColor: "var(--border)", background: "var(--surface-0)", color: "var(--text-primary)" };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** A number input that keeps its own text, so it can be emptied and retyped; it reports 0 while empty. */
function NumberField({ value, onChange, min, max, step }: { value: number; onChange: (n: number) => void; min: number; max: number; step?: number }) {
  const [text, setText] = useState(value ? String(value) : "");
  useEffect(() => {
    if ((Number(text) || 0) !== value) setText(value ? String(value) : ""); // the value changed from outside (a load, a reset)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only an outside change should rewrite what was typed
  }, [value]);
  return (
    <input type="number" inputMode="decimal" min={min} max={max} step={step} value={text} placeholder="0" className={input} style={inputStyle}
      onChange={(e) => {
        setText(e.target.value);
        onChange(Number(e.target.value) || 0);
      }} />
  );
}

/** The resident persona's own setup: their device, and their home marked up outside and inside for whoever comes to help. */
export default function ResidentPage() {
  const router = useRouter();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [home, setHome] = useState<Home | null>(null);
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [detail, setDetail] = useState<BuildingDetail | null>(null);
  const [query, setQuery] = useState("");
  const [outsideKind, setOutsideKind] = useState<OutsideKind>("park");
  const [insideKind, setInsideKind] = useState<InsideKind>("machine");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const persona = getPersona();
    if (persona?.role !== "resident") return router.replace("/start");
    if (!API) return;
    getJson<{ patient: Patient; home: Home | null }>(`/api/patients/${persona.id}/home`)
      .then((r) => {
        const fresh = emptyHome(r.patient);
        setPatient(r.patient);
        // a home saved before the device was asked for starts from the patient record; older outside pins are dropped
        setHome(r.home ? { ...r.home, device_name: r.home.device_name || fresh.device_name, outside: currentOutside(r.home.outside) } : fresh);
      })
      .catch((e) => setStatus({ ok: false, text: e instanceof Error ? e.message : String(e) }));
    getJson<BuildingRow[]>("/api/buildings").then(setBuildings).catch(() => setBuildings([]));
  }, [router]);

  const buildingId = home?.building_id;
  useEffect(() => {
    setDetail(null);
    if (buildingId) getJson<BuildingDetail>(`/api/buildings/${buildingId}`).then(setDetail).catch(() => setDetail(null));
  }, [buildingId]);

  // the home's scan opens on its own: the saved one, else the building's first
  const scanIds = detail?.scan_ids;
  useEffect(() => {
    if (scanIds) setHome((h) => (h ? withDefaultScan(h, scanIds) : h));
  }, [scanIds]);

  if (!API) return <p className="mx-auto max-w-md px-6 py-10 text-sm">This page needs the Hearth API.</p>;
  if (!patient || !home) {
    return <p className="mx-auto max-w-md px-6 py-10 text-sm" style={{ color: status ? "#d03b3b" : "var(--text-muted)" }}>{status?.text ?? "Loading…"}</p>;
  }

  const set = (patch: Partial<Home>) => {
    setHome({ ...home, ...patch });
    setStatus(null);
  };
  const q = query.trim().toLowerCase();
  const matches = q.length < 2 ? [] : buildings.filter((b) => `${b.address} ${b.name ?? ""}`.toLowerCase().includes(q)).slice(0, 8);
  const cm = home.size_cm ?? [50, 40, 30];

  async function save() {
    if (!home) return;
    if (!home.building_id) return setStatus({ ok: false, text: "Choose your building first." });
    try {
      const hasName = (p: { name: string }) => !!p.name.trim(); // a row left without a name is not a person
      const named = { ...home, contacts: home.contacts.filter(hasName), helpers: home.helpers.filter(hasName) };
      setHome(await putJson<Home>(`/api/patients/${home.patient_id}/home`, named));
      setStatus({ ok: true, text: "Saved." });
    } catch (e) {
      setStatus({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 px-6 py-10 pb-24">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Your home setup</h1>
        <Link href="/start" className="text-xs underline underline-offset-2" style={{ color: "var(--text-secondary)" }}>Switch role</Link>
      </header>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Simulated resident {patient.patient_id}</p>

      <HelpPanel patientId={patient.patient_id} />

      <Section title="Your device">
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          The device you have
          <input value={home.device_name} maxLength={120} className={input} style={inputStyle} onChange={(e) => set({ device_name: e.target.value })} />
        </label>
        <div>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Can it be moved?</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Choice on={home.movable === true} onClick={() => set({ movable: true })}>Yes, it can go with me</Choice>
            <Choice on={home.movable === false} onClick={() => set({ movable: false })}>No, it stays here</Choice>
          </div>
        </div>
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          Without it I&apos;m OK for … hours
          <NumberField min={0} max={720} step={0.5} value={home.ok_without_h} onChange={(n) => set({ ok_without_h: n })} />
        </label>
        <div>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Its size: exact dimensions, or about the size of</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Choice on={home.size === "custom"} onClick={() => set({ size: "custom", size_cm: cm })}>Exact dimensions</Choice>
            {(Object.keys(SIZES) as Exclude<SizeId, "custom">[]).map((id) => (
              <Choice key={id} on={home.size === id} onClick={() => set({ size: id, size_cm: null })}>{SIZES[id].label}</Choice>
            ))}
          </div>
          {home.size === "custom" && (
            <div className="mt-2 grid grid-cols-3 gap-2">
              {(["Width", "Depth", "Height"] as const).map((name, i) => (
                <label key={name} className="block text-xs" style={{ color: "var(--text-secondary)" }}>
                  {name} (cm)
                  <NumberField min={1} max={300} value={cm[i]}
                    onChange={(n) => set({ size_cm: cm.map((v, j) => (j === i ? n : v)) as [number, number, number] })} />
                </label>
              ))}
            </div>
          )}
        </div>
      </Section>

      <Section title="Your building">
        {detail && <p className="text-sm">{detail.name ? `${detail.name}, ` : ""}{detail.address}</p>}
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          Search by address or building name
          <input value={query} className={input} style={inputStyle} onChange={(e) => setQuery(e.target.value)} />
        </label>
        {matches.length > 0 && (
          <ul className="space-y-1">
            {matches.map((b) => (
              <li key={b.building_id}>
                <button type="button" className="w-full rounded border px-3 py-1.5 text-left text-xs" style={{ borderColor: "var(--border)" }}
                  onClick={() => {
                    setHome(withBuilding(home, b.building_id));
                    setQuery("");
                    setStatus(null);
                  }}>
                  {b.name ? `${b.name}, ` : ""}{b.address}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Outside">
        {detail ? (
          <>
            <div className="flex flex-wrap gap-1.5">
              {OUTSIDE_KINDS.map((k) => (
                <Choice key={k} on={outsideKind === k} color={PIN_COLOR[k]} onClick={() => setOutsideKind(k)}>{PIN_LABEL[k]}</Choice>
              ))}
            </div>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Pick what to mark, then tap the image. Tap a pin to remove it.</p>
            <AerialPins imagePath={detail.image_url} pins={home.outside} kind={outsideKind} onChange={(outside) => set({ outside })} />
          </>
        ) : (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Choose your building to see it from above.</p>
        )}
      </Section>

      <Section title="Inside">
        {!detail ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Choose your building to see its scan.</p>
        ) : (
          <>
            {home.scan_id && detail.scan_ids.includes(home.scan_id) ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {INSIDE_KINDS.map((k) => (
                    <Choice key={k} on={insideKind === k} color={PIN_COLOR[k]} onClick={() => setInsideKind(k)}>{PIN_LABEL[k]}</Choice>
                  ))}
                </div>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Mark where your machine is.</p>
                {/* opens on the floor plan; going inside from it, and pins showing in both, are the scan viewer's own behaviour */}
                <ScanPins view="floorplan" scanId={home.scan_id} sdkKey={detail.scan_sdk_key} pins={home.inside} kind={insideKind}
                  onChange={(inside) => set({ inside })} />
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Simulated: this resident&apos;s home is this scanned unit.</p>
              </>
            ) : (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No 3D scan for this building.</p>
            )}
            <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
              Note for the responder
              <input value={home.note} maxLength={500} className={input} style={inputStyle} onChange={(e) => set({ note: e.target.value })} />
            </label>
          </>
        )}
      </Section>

      <Section title="People who live with you">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Anyone at home who can help before a crew arrives. Simulated: do not enter a real person&apos;s details.
        </p>
        <PeopleFields people={home.helpers} onChange={(helpers) => set({ helpers })} addLabel="Add a person at home"
          notePlaceholder="What they can do (swap the tank, lift)" />
      </Section>

      <Section title="People to contact">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Family or trusted people to reach as well. Simulated: do not enter a real person&apos;s details.
        </p>
        <PeopleFields people={home.contacts} onChange={(contacts) => set({ contacts })} addLabel="Add a contact" notePlaceholder="Note (has a key)" />
      </Section>

      <div className="flex items-center gap-3">
        <button type="button" onClick={save} className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: "#1b7f4d" }}>Save</button>
        {status && <p role="status" className="text-sm" style={{ color: status.ok ? "var(--text-secondary)" : "#d03b3b" }}>{status.text}</p>}
      </div>
    </div>
  );
}
