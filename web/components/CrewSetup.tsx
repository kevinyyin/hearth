"use client";

import { useEffect, useState } from "react";
import Choice from "@/components/Choice";
import { getJson, sendJson } from "@/lib/api";
import { EQUIPMENT, VEHICLES } from "@/lib/help";
import type { Equipment, Responder, Vehicle } from "@/lib/types";

type BuildingRow = { building_id: string; name: string | null; address: string };

const title = (b: BuildingRow) => `${b.name ? `${b.name}, ` : ""}${b.address}`;

/** A crew persona says where it is based, what it drives and what is on board. Dispatch reads all three. */
export default function CrewSetup({ crewId, crew, onSaved }: { crewId: string; crew: Responder | null; onSaved: () => void }) {
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [base, setBase] = useState(crew?.base_building_id ?? "");
  const [query, setQuery] = useState("");
  const [vehicle, setVehicle] = useState<Vehicle>(crew?.vehicle ?? "van");
  const [equipment, setEquipment] = useState<Equipment[]>(crew?.equipment ?? []);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    getJson<BuildingRow[]>("/api/buildings").then(setBuildings).catch(() => setBuildings([]));
  }, []);

  const q = query.trim().toLowerCase();
  const matches = q.length < 2 ? [] : buildings.filter((b) => title(b).toLowerCase().includes(q)).slice(0, 8);
  const chosen = buildings.find((b) => b.building_id === base);

  async function save() {
    if (!base) return setFailed("Choose where your crew is based first.");
    try {
      await sendJson<Responder>("PUT", `/api/crews/${encodeURIComponent(crewId)}`, { base_building_id: base, vehicle, equipment, on_duty: crew?.on_duty ?? true });
      onSaved();
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="space-y-3 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="text-sm font-semibold">Crew setup</h2>
      <div>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Based at</p>
        {chosen && <p className="text-sm">{title(chosen)}</p>}
        <label className="mt-1 block text-xs" style={{ color: "var(--text-secondary)" }}>
          Search by address or building name
          <input value={query} onChange={(e) => setQuery(e.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm"
            style={{ borderColor: "var(--border)", background: "var(--surface-0)", color: "var(--text-primary)" }} />
        </label>
        {matches.length > 0 && (
          <ul className="mt-1 space-y-1">
            {matches.map((b) => (
              <li key={b.building_id}>
                <button type="button" className="w-full rounded border px-3 py-1.5 text-left text-xs" style={{ borderColor: "var(--border)" }}
                  onClick={() => {
                    setBase(b.building_id);
                    setQuery("");
                    setFailed(null);
                  }}>
                  {title(b)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Vehicle</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {(Object.keys(VEHICLES) as Vehicle[]).map((v) => (
            <Choice key={v} on={vehicle === v} onClick={() => setVehicle(v)}>{VEHICLES[v]}</Choice>
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>On board</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {(Object.keys(EQUIPMENT) as Equipment[]).map((e) => (
            <Choice key={e} on={equipment.includes(e)} onClick={() => setEquipment(equipment.includes(e) ? equipment.filter((x) => x !== e) : [...equipment, e])}>
              {EQUIPMENT[e]}
            </Choice>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button type="button" onClick={save} className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: "#1b7f4d" }}>Save</button>
        {failed && <p role="alert" className="text-sm" style={{ color: "#d03b3b" }}>{failed}</p>}
      </div>
    </section>
  );
}
