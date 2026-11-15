"use client";

import { useEffect, useMemo, useState } from "react";
import Button from "@/components/Button";
import Choice from "@/components/Choice";
import { PAIR_NEEDS, PAIR_VANS, SEARCH_NEEDS, SEARCH_VANS, bestPairing, nearestFirst, planCost, reachTimes, searchTrace, type Need, type Routes, type Van } from "@/lib/algorithm";
import { clock } from "./ScoreCurve";

const K = 10; // pixels per km
const vanColor = (vans: Van[], id: string) => `var(--series-${vans.findIndex((v) => v.id === id) + 1})`;

/** Vans (squares), people (numbered circles) and each van's route. A stop reached after its deadline is ringed and says so. */
function PlanMap({ vans, needs, routes, out = [], label }: { vans: Van[]; needs: Need[]; routes: Routes; out?: string[]; label: string }) {
  const reached = new Map(vans.flatMap((v) => reachTimes(v, routes[v.id] ?? []).map((t, i) => [routes[v.id][i].id, { t, van: v.id }] as const)));
  return (
    <svg viewBox="0 0 400 240" className="w-full rounded-lg border" style={{ borderColor: "var(--border)", background: "var(--surface-0)" }} role="img" aria-label={label}>
      {vans.map((v) => (
        <polyline key={v.id} points={[v, ...(routes[v.id] ?? [])].map((p) => `${p.x * K},${p.y * K}`).join(" ")} fill="none"
          stroke={vanColor(vans, v.id)} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      ))}
      {needs.map((n) => {
        const r = reached.get(n.id);
        const late = r !== undefined && r.t > n.hoursLeft;
        const gone = out.includes(n.id);
        return (
          <g key={n.id}>
            <title>{`${n.device}, ${clock(n.hoursLeft)} of backup. ${gone ? "Taken out of the plan." : r ? `Van ${r.van} arrives in ${clock(r.t)}${late ? `, ${clock(r.t - n.hoursLeft)} late` : ""}.` : "No van yet."}`}</title>
            <circle cx={n.x * K} cy={n.y * K} r="9" fill="var(--surface-1)" stroke={late ? "var(--accent)" : "var(--text-primary)"}
              strokeWidth={late ? 3 : 1.5} strokeDasharray={gone ? "3 3" : undefined} opacity={gone ? 0.55 : 1} />
            <text x={n.x * K} y={n.y * K + 3.5} textAnchor="middle" fontSize="10" fontWeight="600" fill="var(--text-primary)" opacity={gone ? 0.55 : 1}>{n.id}</text>
            {late && <text x={n.x * K} y={n.y * K + 22} textAnchor="middle" fontSize="10" fontWeight="600" fill="var(--text-primary)" stroke="var(--surface-0)" strokeWidth="3" paintOrder="stroke">late</text>}
          </g>
        );
      })}
      {vans.map((v) => (
        <g key={v.id}>
          <rect x={v.x * K - 7} y={v.y * K - 7} width="14" height="14" rx="3" fill={vanColor(vans, v.id)} stroke="var(--surface-0)" strokeWidth="2" />
          <text x={v.x * K} y={v.y * K - 12} textAnchor="middle" fontSize="10" fill="var(--text-secondary)" stroke="var(--surface-0)" strokeWidth="3" paintOrder="stroke">Van {v.id}</text>
        </g>
      ))}
    </svg>
  );
}

const Score = ({ value, note }: { value: number; note: string }) => (
  <p className="text-sm" style={{ color: "var(--text-secondary)" }} aria-live="polite">
    <span className="display tnum mr-2 text-4xl" style={{ color: "var(--text-primary)" }}>{value.toFixed(2)}</span>
    {note}
  </p>
);

/** Step 1: the same three calls under the nearest-van rule and under the best pairing. */
export function PairingDemo() {
  const [best, setBest] = useState(false);
  const routes = useMemo(() => (best ? bestPairing : nearestFirst)(PAIR_NEEDS, PAIR_VANS), [best]);
  const rows = PAIR_NEEDS.map((n) => {
    const van = PAIR_VANS.find((v) => routes[v.id]?.[0] === n)!;
    return { n, van, t: reachTimes(van, [n])[0] };
  });
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Rule">
        <Choice on={!best} onClick={() => setBest(false)}>Nearest van first</Choice>
        <Choice on={best} onClick={() => setBest(true)}>Best pairing</Choice>
      </div>
      <PlanMap vans={PAIR_VANS} needs={PAIR_NEEDS} routes={routes} label={`Three vans and three calls, paired by ${best ? "the best pairing" : "the nearest-van rule"}`} />
      <table className="mt-3 w-full text-left text-sm">
        <thead>
          <tr style={{ color: "var(--text-muted)" }}>
            {["Call", "Backup left", "Van", "Arrives in"].map((h) => <th key={h} scope="col" className="py-1 pr-3 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ n, van, t }) => (
            <tr key={n.id} className="border-t" style={{ borderColor: "var(--border)" }}>
              <th scope="row" className="py-1.5 pr-3 font-medium">{n.id} · {n.device}</th>
              <td className="tnum pr-3">{clock(n.hoursLeft)}</td>
              <td className="pr-3">
                <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] align-baseline" style={{ background: vanColor(PAIR_VANS, van.id) }} />{van.id}
              </td>
              <td className="tnum">{clock(t)}{t > n.hoursLeft && <strong className="ml-2">{clock(t - n.hoursLeft)} late</strong>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4">
        <Score value={planCost(routes, PAIR_NEEDS, PAIR_VANS)} note={best ? "weighted hours at risk: nobody is late" : "weighted hours at risk: the ventilator took the van the oxygen call needed"} />
      </div>
    </div>
  );
}

const ROUNDS = 30;
const HOW = { random: "picked at random", worst: "the ones paying the most where they sat", related: "a cluster of neighbors" } as const;

/** Step 2: the route search, one frame at a time. */
export function SearchDemo() {
  const frames = useMemo(() => searchTrace(SEARCH_NEEDS, SEARCH_VANS, ROUNDS), []);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const last = frames.length - 1;
  const f = frames[i];

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setI((j) => Math.min(j + 1, last)), 450);
    return () => clearInterval(id);
  }, [playing, last]);
  useEffect(() => {
    if (i === last) setPlaying(false);
  }, [i, last]);

  const round = Math.ceil(i / 2);
  const said = f.how === "start" ? "The start: the pairing from step 1, then every other stop put where it costs least."
    : f.how === "best" ? `The best plan found in ${ROUNDS} rounds: nobody is late. Each van sets off for its first stop.`
    : f.kept === null ? `Round ${round}. Took out ${f.out.length} stops: ${HOW[f.how]}.`
    : `Round ${round}. Put back where they cost least. ${f.best < frames[i - 1].best ? "A new best." : f.kept ? "Not a new best, but kept to search from." : "Worse, thrown away."}`;

  // best score so far, as a step line up to the frame on show
  const top = frames[0].score, low = frames[last].score;
  const sx = (j: number) => 4 + (j / last) * 392, sy = (s: number) => 8 + ((top - s) / (top - low || 1)) * 40;
  const path = frames.slice(0, i + 1).map((fr, j) => `${j ? "H" : "M"}${sx(j)}${j ? `V${sy(fr.best)}` : `,${sy(fr.best)}`}`).join("");

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <Button primary onClick={() => (i === last ? (setI(0), setPlaying(true)) : setPlaying(!playing))}>{playing ? "Pause" : i === last ? "Play again" : "Play"}</Button>
        <Button onClick={() => (setPlaying(false), setI(Math.min(i + 1, last)))} disabled={i === last}>Step</Button>
        <Button onClick={() => (setPlaying(false), setI(0))} disabled={i === 0}>Reset</Button>
        <span className="tnum ml-auto text-xs" style={{ color: "var(--text-muted)" }}>Round {Math.min(round, ROUNDS)} of {ROUNDS}</span>
      </div>
      <PlanMap vans={SEARCH_VANS} needs={SEARCH_NEEDS} routes={f.routes} out={f.out} label="Three vans and eleven stops; each van's route is a line through its stops in order" />
      <p className="mt-3 min-h-[2.75rem] text-sm leading-snug" style={{ color: "var(--text-secondary)" }} aria-live="polite">{said}</p>
      <svg viewBox="0 0 400 56" className="mt-1 w-full" role="img" aria-label={`Best score so far: ${f.best.toFixed(2)}, down from ${top.toFixed(2)} at the start`}>
        <line x1="4" x2="396" y1={sy(low)} y2={sy(low)} stroke="var(--grid)" />
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" />
        <circle cx={sx(i)} cy={sy(f.best)} r="4" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
      </svg>
      <div className="mt-2">
        <Score value={f.best} note={`weighted hours at risk, best so far. It started at ${top.toFixed(2)}.`} />
      </div>
    </div>
  );
}
