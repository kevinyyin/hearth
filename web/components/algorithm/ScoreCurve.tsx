"use client";

import { useState } from "react";
import Choice from "@/components/Choice";
import { HORIZON_H, cost } from "@/lib/algorithm";

const DEVICES: [string, number][] = [["Ventilator", 5], ["Oxygen", 3], ["Home dialysis", 2], ["Feeding pump", 1]];
const W = 420, H = 220, L = 34, R = 12, T = 14, B = 30;
const Y_MAX = 42; // fixed, so switching device shows the difference instead of rescaling it away
const px = (h: number) => L + (h / HORIZON_H) * (W - L - R);
const py = (c: number) => H - B - (Math.min(c, Y_MAX) / Y_MAX) * (H - T - B);
export function clock(h: number): string {
  const m = Math.round(h * 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
}

/** The score for one person, as a curve: flat until their backup runs out, steep after. */
export default function ScoreCurve() {
  const [weight, setWeight] = useState(3);
  const [left, setLeft] = useState(2);
  const [wait, setWait] = useState(3.5);
  const at = cost(weight, left, wait);
  const line = [0, left, HORIZON_H].map((h) => `${px(h)},${py(cost(weight, left, h))}`).join(" ");

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Device">
        {DEVICES.map(([name, w]) => (
          <Choice key={name} on={w === weight} onClick={() => setWeight(w)}>{name} · weight {w}</Choice>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
        aria-label={`Cost of reaching a person with weight ${weight} and ${clock(left)} of backup, by hours waited. Reached after ${clock(wait)}, the cost is ${at.toFixed(1)}.`}>
        {[0, 10, 20, 30, 40].map((c) => (
          <g key={c}>
            <line x1={L} x2={W - R} y1={py(c)} y2={py(c)} stroke="var(--grid)" />
            <text x={L - 6} y={py(c) + 3.5} textAnchor="end" fontSize="10" fill="var(--text-muted)">{c}</text>
          </g>
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((h) => (
          <text key={h} x={px(h)} y={H - B + 14} textAnchor="middle" fontSize="10" fill="var(--text-muted)">{h}</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 2} textAnchor="middle" fontSize="10" fill="var(--text-muted)">hours waited for a crew</text>
        <line x1={px(left)} x2={px(left)} y1={T} y2={H - B} stroke="var(--text-muted)" strokeDasharray="3 3" />
        <text x={px(left) + (left > 4.4 ? -5 : 5)} y={T + 8} textAnchor={left > 4.4 ? "end" : "start"} fontSize="10" fill="var(--text-secondary)">backup runs out</text>
        <polyline points={line} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={px(wait)} cy={py(at)} r="5" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
      </svg>
      <div className="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <label className="block">
          <span style={{ color: "var(--text-muted)" }}>Backup left: </span><span className="tnum font-semibold">{clock(left)}</span>
          <input type="range" min={0.25} max={HORIZON_H} step={0.25} value={left} onChange={(e) => setLeft(+e.target.value)} className="mt-1 block w-full" style={{ accentColor: "var(--text-primary)" }} />
        </label>
        <label className="block">
          <span style={{ color: "var(--text-muted)" }}>A crew arrives after: </span><span className="tnum font-semibold">{clock(wait)}</span>
          <input type="range" min={0} max={HORIZON_H} step={0.25} value={wait} onChange={(e) => setWait(+e.target.value)} className="mt-1 block w-full" style={{ accentColor: "var(--text-primary)" }} />
        </label>
      </div>
      <p className="mt-4 text-sm" style={{ color: "var(--text-secondary)" }} aria-live="polite">
        <span className="display tnum mr-2 text-4xl" style={{ color: "var(--text-primary)" }}>{at.toFixed(1)}</span>
        {wait > left ? `weighted hours: ${clock(wait - left)} past the deadline, times ${weight}` : "weighted hours: not late yet, so only the small term counts"}
      </p>
    </div>
  );
}
