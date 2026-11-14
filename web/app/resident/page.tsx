"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import AerialPins from "@/components/AerialPins";
import { API, getJson, putJson } from "@/lib/api";
import ScanPins from "@/components/ScanPins";
import { emptyHome, getPersona, PIN_COLOR, PIN_LABEL, SIZES, withBuilding, withScan } from "@/lib/home";
import type { BuildingDetail, Home, InsideKind, OutsideKind, Patient, SizeId } from "@/lib/types";

type BuildingRow = { building_id: string; name: string | null; address: string };

const OUTSIDE_KINDS: OutsideKind[] = ["park", "entrance", "blocked", "route"];
const INSIDE_KINDS: InsideKind[] = ["machine", "blocked", "route"];
const words = (s: string) => s.replace(/_/g, " ");
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

/** A toggle in a row of choices (pin kind, size). */
function Choice({ on, color, onClick, children }: { on: boolean; color?: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className="rounded border px-2.5 py-1 text-xs font-medium"
      style={on ? { background: color ?? "var(--text-primary)", borderColor: color ?? "var(--text-primary)", color: color ? "#fff" : "var(--surface-1)" }
        : { borderColor: "var(--border)", color: "var(--text-secondary)" }}
    >
      {children}
    </button>
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
        setPatient(r.patient);
        setHome(r.home ?? emptyHome(r.patient));
      })
      .catch((e) => setStatus({ ok: false, text: e instanceof Error ? e.message : String(e) }));
    getJson<BuildingRow[]>("/api/buildings").then(setBuildings).catch(() => setBuildings([]));
  }, [router]);

  const buildingId = home?.building_id;
  useEffect(() => {
    setDetail(null);
    if (buildingId) getJson<BuildingDetail>(`/api/buildings/${buildingId}`).then(setDetail).catch(() => setDetail(null));
  }, [buildingId]);

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
  const scans = (detail?.scan_ids ?? []).slice(0, 6);
  const pickScan = (id: string | null) => {
    setHome(withScan(home, id));
    setStatus(null);
  };

  async function save() {
    if (!home) return;
    if (!home.building_id) return setStatus({ ok: false, text: "Choose your building first." });
    try {
      setHome(await putJson<Home>(`/api/patients/${home.patient_id}/home`, home));
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

      <Section title="Your device">
        <p className="text-sm">{words(patient.device)} ({words(patient.device_detail)})</p>
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          Without it I&apos;m OK for … hours
          <NumberField min={0} max={720} step={0.5} value={home.ok_without_h} onChange={(n) => set({ ok_without_h: n })} />
        </label>
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          Backup plan
          <input value={home.backup_plan} maxLength={500} className={input} style={inputStyle} onChange={(e) => set({ backup_plan: e.target.value })} />
        </label>
        <div>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>About the size of</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(Object.keys(SIZES) as Exclude<SizeId, "custom">[]).map((id) => (
              <Choice key={id} on={home.size === id} onClick={() => set({ size: id, size_cm: null })}>{SIZES[id].label}</Choice>
            ))}
            <Choice on={home.size === "custom"} onClick={() => set({ size: "custom", size_cm: cm })}>Other</Choice>
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
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Choose your building to see its scans.</p>
        ) : (
          <>
            {scans.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No 3D scan for this building.</p>
            ) : (
              <div>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Which of these is laid out like your home?</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {scans.map((id, i) => (
                    <Choice key={id} on={home.scan_id === id} onClick={() => pickScan(id)}>Layout {i + 1}</Choice>
                  ))}
                  <Choice on={home.scan_id === null} onClick={() => pickScan(null)}>None of these</Choice>
                </div>
              </div>
            )}
            {home.scan_id && scans.includes(home.scan_id) && (
              <>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Sample unit from this building, not your own home.</p>
                <div className="flex flex-wrap gap-1.5">
                  {INSIDE_KINDS.map((k) => (
                    <Choice key={k} on={insideKind === k} color={PIN_COLOR[k]} onClick={() => setInsideKind(k)}>{PIN_LABEL[k]}</Choice>
                  ))}
                </div>
                <ScanPins scanId={home.scan_id} sdkKey={detail.scan_sdk_key} pins={home.inside} kind={insideKind} onChange={(inside) => set({ inside })} />
              </>
            )}
            <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
              Note for the responder
              <input value={home.note} maxLength={500} className={input} style={inputStyle} onChange={(e) => set({ note: e.target.value })} />
            </label>
          </>
        )}
      </Section>

      <div className="flex items-center gap-3">
        <button type="button" onClick={save} className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: "#1b7f4d" }}>Save</button>
        {status && <p role="status" className="text-sm" style={{ color: status.ok ? "var(--text-secondary)" : "#d03b3b" }}>{status.text}</p>}
      </div>
    </div>
  );
}
