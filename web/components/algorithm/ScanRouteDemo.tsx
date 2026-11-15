"use client";

import { useState } from "react";
import Button from "@/components/Button";
import { UNIT_ENTRANCE, UNIT_ROOMS, UNIT_SIGHT, UNIT_SPOTS } from "@/lib/algorithm";
import { scanRoute } from "@/lib/scanRoute";

const M = 40; // pixels per metre
const at = (id: string) => ({ x: UNIT_SPOTS[id].position.x * M, y: UNIT_SPOTS[id].position.z * M });

/** Step 3: `scanRoute` itself, on a hand-made unit. Click a spot to put the machine there. */
export default function ScanRouteDemo() {
  const [pin, setPin] = useState<string | null>(null);
  const route = scanRoute(UNIT_SPOTS, UNIT_ENTRANCE, pin);
  const end = route.at(-1)!;
  const metres = route.slice(1).reduce((sum, id, i) => sum + Math.hypot(at(id).x - at(route[i]).x, at(id).y - at(route[i]).y) / M, 0);

  return (
    <div>
      <svg viewBox="-4 28 488 264" className="w-full" role="group" aria-label="Floor plan of a scanned unit with the walking route from the entrance to the machine">
        {UNIT_ROOMS.map((r) => (
          <g key={r.id}>
            <rect x={r.x * M} y={r.y * M} width={r.w * M} height={r.h * M} fill="var(--surface-0)" stroke="var(--text-muted)" strokeWidth="1.5" />
            <text x={r.x * M + 7} y={r.y * M + 15} fontSize="10" fill="var(--text-muted)">{r.name}</text>
          </g>
        ))}
        {UNIT_SIGHT.map(([a, b]) => (
          <line key={a + b} x1={at(a).x} y1={at(a).y} x2={at(b).x} y2={at(b).y} stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2 4" />
        ))}
        <polyline points={route.map((id) => `${at(id).x},${at(id).y}`).join(" ")} fill="none" stroke="var(--series-1)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        {Object.keys(UNIT_SPOTS).map((id) => {
          const on = route.includes(id);
          const say = id === UNIT_ENTRANCE ? "Entrance" : id === end ? "Machine" : null;
          return (
            <g key={id} role="button" tabIndex={0} aria-label={`Put the machine at spot ${id}`} style={{ cursor: "pointer" }}
              onClick={() => setPin(id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setPin(id))}>
              <circle cx={at(id).x} cy={at(id).y} r="14" fill="transparent" />
              <circle cx={at(id).x} cy={at(id).y} r={say ? 7 : 5} fill={id === end ? "var(--accent)" : on ? "var(--series-1)" : "var(--surface-1)"}
                stroke={on ? "var(--surface-0)" : "var(--text-secondary)"} strokeWidth={on ? 2 : 1.5} />
              {say && <text x={at(id).x} y={at(id).y - 12} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--text-primary)">{say}</text>}
            </g>
          );
        })}
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="text-sm" style={{ color: "var(--text-secondary)" }} aria-live="polite">
          <span className="display tnum mr-2 text-4xl" style={{ color: "var(--text-primary)" }}>{metres.toFixed(1)} m</span>
          over {route.length} spots. {pin ? "The machine is where you pinned it." : "Nobody has pinned the machine, so it is assumed to be in the farthest real room."}
        </p>
        {pin && <Button onClick={() => setPin(null)}>Clear the pin</Button>}
      </div>
    </div>
  );
}
