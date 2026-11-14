"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { API, getJson } from "@/lib/api";
import { setPersona } from "@/lib/home";
import type { Patient } from "@/lib/types";

const words = (s: string) => s.replace(/_/g, " ");
const card = "space-y-2 rounded-lg border p-4";
const button = "w-full rounded border px-3 py-2 text-left text-sm";

/** Demo personas, not logins: the choice is kept in this browser and the shared password still guards the hosted site. */
export default function StartPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [crew, setCrew] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (API) getJson<Patient[]>("/api/demo-patients").then(setPatients).catch((e) => setError(String(e)));
  }, []);

  if (!API) return <p className="mx-auto max-w-md px-6 py-10 text-sm">This page needs the Hearth API.</p>;

  function asResponder(e: FormEvent) {
    e.preventDefault();
    if (!crew.trim()) return;
    setPersona({ role: "responder", id: crew.trim() });
    router.push("/responder");
  }

  return (
    <div className="mx-auto max-w-md space-y-4 px-6 py-10 pb-20">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Who are you?</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Demo personas over simulated patients. Nothing here is a real account.
        </p>
      </header>

      <section className={card} style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
        <h2 className="text-sm font-semibold">Resident</h2>
        {patients.map((p) => (
          <button
            key={p.patient_id}
            type="button"
            className={button}
            style={{ borderColor: "var(--border)" }}
            onClick={() => {
              setPersona({ role: "resident", id: p.patient_id });
              router.push("/resident");
            }}
          >
            {p.patient_id} · {words(p.device)} · {words(p.mobility)}
          </button>
        ))}
        {error && <p className="text-xs" style={{ color: "#d03b3b" }}>{error}</p>}
      </section>

      <form onSubmit={asResponder} className={card} style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
        <h2 className="text-sm font-semibold">Responder</h2>
        <label className="block text-xs" style={{ color: "var(--text-secondary)" }}>
          Crew name
          <input
            value={crew}
            onChange={(e) => setCrew(e.target.value)}
            required
            className="mt-1 w-full rounded border px-3 py-2 text-sm"
            style={{ borderColor: "var(--border)", background: "var(--surface-0)", color: "var(--text-primary)" }}
          />
        </label>
        <button type="submit" className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: "#1b7f4d" }}>
          Continue
        </button>
      </form>

      <section className={card} style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
        <h2 className="text-sm font-semibold">Dispatcher</h2>
        <Link href="/" className="text-sm underline underline-offset-2">Open the map</Link>
      </section>
    </div>
  );
}
