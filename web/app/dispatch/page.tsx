"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Button from "@/components/Button";
import DispatchMap, { type MapPin } from "@/components/DispatchMap";
import HouseholdCard from "@/components/HouseholdCard";
import ProposalCard from "@/components/ProposalCard";
import StagingCard from "@/components/StagingCard";
import { API, getJson, sendJson } from "@/lib/api";
import { clock, type Household, households, hoursOf, need, PIN_COLORS, pin, SIMULATED_COLOR, stepSeconds, street, words } from "@/lib/dispatch";
import { EQUIPMENT, VEHICLES } from "@/lib/help";
import { streamEvents } from "@/lib/sse";
import type { AgentRun, DispatchView, Registrations, StagingView, StormRound } from "@/lib/types";
import { plainError, useAction } from "@/lib/useAction";
import { usePoll } from "@/lib/usePoll";

const ROUNDS: [StormRound, string, string][] = [["week", "A week out", "a week out"], ["day", "Landfall day", "landfall day"], ["outage", "Power is out", "power out"]];
const LEGEND: [string, string][] = [[PIN_COLORS.needs, "Needs you"], [PIN_COLORS.waiting, "Waiting"], [PIN_COLORS.moving, "Crew on the way"], [PIN_COLORS.safe, "Safe"], [SIMULATED_COLOR, "Simulated"]];
const LIVE = ["waiting", "offered", "accepted", "at_door", "riding"];
const NEEDS_TEXT = "#9a3214";
const muted = { color: "var(--text-muted)" };
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function Check({ className = "" }: { className?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className={className}>
      <path d="M2 6.5 5 9l5-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Section({ title, n, tint, children }: { title: string; n: number; tint?: boolean; children: ReactNode }) {
  return (
    <section className="border-b px-6 py-4" style={{ borderColor: "var(--border)", background: tint ? "#fbefe8" : undefined }}>
      <h2 className="mb-3 flex items-baseline gap-2 text-sm font-semibold" style={tint ? { color: NEEDS_TEXT } : undefined}>
        {title} <span className="tnum text-xs font-medium" style={tint ? { color: NEEDS_TEXT } : muted}>{n}</span>
      </h2>
      {children}
    </section>
  );
}

/** The three storm rounds as steps in order, and what the last one did. Each press rings every phone on the list. */
function StormRounds({ storm, onPlaced }: { storm: DispatchView["storm"] | undefined; onPlaced: () => void }) {
  const { busy, error, act } = useAction();
  const [note, setNote] = useState<string | null>(null);
  // the first press arms a round (or the reset), the second does it; pressing anywhere else disarms
  const [armed, setArmed] = useState<StormRound | "reset" | null>(null);
  const next = ROUNDS.find(([r]) => !storm?.placed[r])?.[0];
  const last = storm?.last;
  const call = (round: StormRound) =>
    act(round, async () => {
      const out = await sendJson<{ dialed: string[]; failed: string[] }>("POST", "/api/storm", { round });
      // a press inside the two-minute guard places nothing and says why in its one "failed" line
      setNote(out.dialed.length === 0 && out.failed.length ? plainError(new Error(out.failed.join("; "))) : out.failed.length ? `Not done: ${out.failed.join("; ")}` : null);
      onPlaced();
    });
  const reset = () =>
    act("reset", async () => {
      await sendJson("POST", "/api/storm/reset");
      setNote(null);
      onPlaced();
    });
  return (
    <div className="flex flex-col items-start gap-2 min-[960px]:ml-auto">
      <div className="flex w-full items-baseline justify-between gap-4">
        <p className="text-[13px] font-semibold" style={{ color: "var(--text-secondary)" }}>Call everyone on the list</p>
        {last && (
          <button type="button" disabled={!!busy} onBlur={() => setArmed(null)}
            onClick={() => { if (armed === "reset") { setArmed(null); reset(); } else setArmed("reset"); }}
            className="text-xs underline underline-offset-2 disabled:opacity-60" style={{ color: armed === "reset" ? NEEDS_TEXT : "var(--text-muted)" }}>
            {busy === "reset" ? "Resetting…" : armed === "reset" ? "Click again to reset the rounds" : "Reset dispatch"}
          </button>
        )}
      </div>
      <ol className="flex w-full flex-col items-stretch gap-1.5 min-[960px]:w-auto min-[960px]:flex-row" aria-label="Storm call rounds">
        {ROUNDS.map(([round, title], i) => {
          const at = storm?.placed[round];
          const primary = round === next;
          return (
            <li key={round} className="contents">
              {i > 0 && <span aria-hidden className="hidden self-center text-sm min-[960px]:inline" style={muted}>→</span>}
              <button type="button" disabled={!!busy} onBlur={() => setArmed(null)}
                onClick={() => { if (armed === round) { setArmed(null); call(round); } else setArmed(round); }}
                className={`flex w-full flex-col items-start gap-0.5 rounded-lg border px-3 py-[7px] text-left disabled:cursor-wait disabled:opacity-70 min-[960px]:w-auto min-[960px]:min-w-[150px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] ${armed === round ? "border-[#9a3214] bg-[#fbefe8] text-[#9a3214]" : primary ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-1)] hover:bg-[#2b2925]" : "border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--surface-2)]"}`}>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold">{at && <Check className="text-[#0e7a54]" />}{title}</span>
                <span className="tnum text-xs" style={{ color: armed === round ? NEEDS_TEXT : primary ? "#d9d4c8" : "var(--text-muted)" }}>
                  {busy === round ? "Calling…" : armed === round ? "Click again to call everyone" : at ? `Placed ${clock(at)} · call again` : primary ? "Call everyone now" : "Not placed yet"}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {last && (
        <p className="text-[13px]" style={muted}>
          Last round, {ROUNDS.find(([r]) => r === last.round)?.[2]} at {clock(last.t)}:{" "}
          <b className="tnum font-semibold" style={{ color: "var(--text-secondary)" }}>{last.dialed}</b> {last.dialed === 1 ? "call" : "calls"} placed ·{" "}
          <b className="tnum font-semibold" style={{ color: "var(--text-secondary)" }}>{last.failed}</b> failed ·{" "}
          <b className="tnum font-semibold" style={{ color: "var(--text-secondary)" }}>{last.registered}</b> new {last.registered === 1 ? "registration" : "registrations"}
        </p>
      )}
      {(error ?? note) && <p role="alert" className="max-w-xl text-[13px]" style={{ color: NEEDS_TEXT }}>{error ?? note}</p>}
    </div>
  );
}

/** A request code could not place: Take over, and the leads when the refuge agent found some. */
function Blocked({ h, leads, noRefuge, onSeeLeads, onChanged }: { h: Household; leads: number; noRefuge: boolean; onSeeLeads: () => void; onChanged: () => void }) {
  const { busy, error, act } = useAction();
  const r = h.request!;
  return (
    <div className="py-2">
      <p className="font-semibold">{street(h.address)} · {words(h.patient.device)}, {hoursOf(h)} h backup</p>
      <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
        {noRefuge ? `No refuge fits. ${leads ? `${plural(leads, "shelter lead")} found nearby.` : "No shelter lead found either."}` : `${r.blocked.charAt(0).toUpperCase()}${r.blocked.slice(1)}.`}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button primary disabled={!!busy} onClick={() => act("take", async () => { await sendJson("POST", `/api/dispatch/${h.id}/handled`); onChanged(); })}>
          {busy ? "Taking over…" : "Take over"}
        </Button>
        {leads > 0 && <Button onClick={onSeeLeads}>See leads</Button>}
      </div>
      {error && <p role="alert" className="mt-1 text-[13px]" style={{ color: NEEDS_TEXT }}>{error}</p>}
    </div>
  );
}

function AgentItem({ run, trigger }: { run: AgentRun; trigger: string }) {
  return (
    <div className="py-2">
      <div className="flex justify-between gap-3">
        <b className="font-semibold">{street(run.address)}</b>
        <span className="text-xs" style={muted}>{run.kind === "survey" ? "building survey" : "refuge search"}</span>
      </div>
      <ul className="mt-1.5 grid gap-[3px] text-[13px]">
        {run.steps.map((s, i) => (
          <li key={i} className="grid grid-cols-[14px_1fr_auto] items-center gap-2" style={{ color: "var(--text-secondary)" }}>
            {s.t1 === null && run.status === "running" ? <span className="live-dot justify-self-center" aria-label="working" /> : <Check className="text-[#0e7a54]" />}
            <span>{s.text}</span>
            <span className="tnum text-xs" style={muted}>{stepSeconds(s, run)} s</span>
          </li>
        ))}
        {run.steps.length === 0 && run.status === "running" && (
          <li className="grid grid-cols-[14px_1fr] items-center gap-2" style={{ color: "var(--text-secondary)" }}><span className="live-dot justify-self-center" aria-hidden />Planning</li>
        )}
      </ul>
      {run.status === "failed" && <p className="mt-1 text-[13px]" style={{ color: NEEDS_TEXT }}>Failed: {run.result.error}</p>}
      {run.status === "stopped" && <p className="mt-1 text-[13px]" style={muted}>Stopped before it finished; it starts again while this page is open.</p>}
      <p className="mt-1.5 text-xs" style={muted}>{trigger}</p>
    </div>
  );
}

type Selected = { kind: "home"; id: string; focus?: "leads" } | { kind: "lot"; id: string } | null;

/** The dispatcher's one screen: a county map of every household Hearth knows, and a rail of what needs a person, what
 *  the agents are doing on their own, the help under way, and the crews. Nothing needs a click unless it is under Needs you. */
export default function DispatchPage() {
  const { data: view, error, refresh } = usePoll<DispatchView>(API ? "/api/dispatch" : null, 2000);
  const { data: regs, refresh: refreshRegs } = usePoll<Registrations>(API ? "/api/registrations" : null);
  const { data: lots, refresh: refreshLots } = usePoll<StagingView>(API ? "/api/staging" : null, 10000);
  const [simulated, setSimulated] = useState<number[][]>([]);
  const [selected, setSelected] = useState<Selected>(null);
  const started = useRef(new Set<string>());
  const card = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (API) getJson<number[][]>("/api/dispatch/simulated").then(setSimulated).catch(() => {});
  }, []);

  // the agents start on their own: each run the server lists, once per key; the server refuses a second start
  useEffect(() => {
    for (const s of view?.to_start ?? []) {
      if (started.current.has(s.key)) continue;
      started.current.add(s.key);
      const path = s.kind === "survey" ? `/api/buildings/${s.building_id}/survey?patient_id=${encodeURIComponent(s.patient_id ?? "")}` : `/api/patients/${s.patient_id}/propose`;
      streamEvents(path, s.kind === "refuge" ? { method: "POST" } : undefined, () => {}).catch(() => {}).finally(refresh);
    }
  }, [view, refresh]);

  // on a phone the card opens below the map, out of sight: bring it up
  const selectedKey = selected && `${selected.kind}:${selected.id}:${"focus" in selected ? selected.focus : ""}`;
  useEffect(() => {
    if (selectedKey && !matchMedia("(min-width: 960px)").matches) card.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [selectedKey]);

  const all = useMemo(() => households(view, regs), [view, regs]);
  const changed = () => {
    refresh();
    refreshRegs();
    refreshLots();
  };

  if (!API) return <p className="mx-auto max-w-2xl px-6 py-10 text-sm">This page needs the Hearth API.</p>;

  const lotList = lots?.chosen ? [lots.chosen] : lots?.options ?? [];
  const pins: MapPin[] = view ? [
    ...all.map((h) => ({ id: h.id, lat: h.lat, lon: h.lon, label: street(h.address), note: pin(h, view).note, color: PIN_COLORS[pin(h, view).state] })),
    ...lotList.filter((l) => l.lat != null && l.lon != null).map((l) => ({ id: `lot:${l.building_id}`, lat: l.lat!, lon: l.lon!, label: "Crew staging lot",
      note: lots?.chosen ? "chosen" : "proposed", color: "", lot: lots?.chosen ? "chosen" as const : "proposed" as const })),
  ] : [];
  const open = selected?.kind === "home" ? all.find((h) => h.id === selected.id) : null;
  const openLot = selected?.kind === "lot" ? lotList.find((l) => l.building_id === selected.id) : null;
  const byId = new Map(all.map((h) => [h.id, h]));

  const needs = view ? all.map((h) => ({ h, n: need(h, view) })).filter((x) => x.n?.kind === "blocked") : [];
  const proposals = view?.proposals ?? [];
  const calls = regs?.needs_person ?? [];
  const working = (view?.agents ?? []).filter((a) => a.on_rail).sort((a, b) => Number(b.status === "running") - Number(a.status === "running") || b.started_at - a.started_at);
  const queue = view ? all.filter((h) => h.request && LIVE.includes(h.request.state) && !need(h, view)).sort((a, b) => (a.request!.rank ?? 1e6) - (b.request!.rank ?? 1e6)) : [];
  const onCrew = (id: string | null) => (id ? `with ${street(byId.get(id)?.address ?? null)}` : null);

  const trigger = (run: AgentRun) => {
    const h = run.patient_id ? byId.get(run.patient_id) : undefined;
    if (run.kind === "survey") return h?.home?.said_at ? `Started by the registration call at ${clock(h.home.said_at)}` : `Started at ${clock(run.started_at)}`;
    return h?.request?.times.waiting ? `Started by the help request at ${clock(h.request.times.waiting)}` : `Started at ${clock(run.started_at)}`;
  };

  return (
    <div className="flex min-h-full flex-col min-[960px]:h-full">
      <header className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b px-6 pt-6 pb-4" style={{ borderColor: "var(--border)" }}>
        <div>
          <Link href="/results" className="mb-3 inline-block rounded-[7px] border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-[13px] font-medium hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]">
            ← Back to results
          </Link>
          <h1 className="display text-[40px] leading-none tracking-[-0.01em]">Dispatch</h1>
          <p className="mt-1 text-[13px]" style={muted}>
            Harris County · simulated storm · real calls go only to numbers on the demo list ·{" "}
            <Link href="/start" className="underline underline-offset-2">Switch role</Link>
          </p>
        </div>
        <StormRounds storm={view?.storm} onPlaced={changed} />
      </header>
      {error && <p role="alert" className="px-6 py-2 text-[13px]" style={{ color: NEEDS_TEXT }}>The dispatch board did not load: {error}</p>}

      <div className="grid min-h-0 flex-1 grid-cols-1 min-[960px]:grid-cols-[1fr_384px]">
        <div className="relative min-h-0">
          <div className="relative h-[55vh] min-[960px]:absolute min-[960px]:inset-0 min-[960px]:h-auto">
            <DispatchMap pins={pins} simulated={simulated} selected={selected ? (selected.kind === "lot" ? `lot:${selected.id}` : selected.id) : null}
              onSelect={(id) => setSelected(id === null ? null : id.startsWith("lot:") ? { kind: "lot", id: id.slice(4) } : { kind: "home", id })} />
            <div aria-hidden className="absolute top-3 left-3 flex min-[960px]:top-auto min-[960px]:bottom-4 min-[960px]:left-4 max-w-[calc(100%-5rem)] flex-wrap gap-x-3 gap-y-1 rounded-lg border px-2.5 py-1.5 text-xs"
              style={{ background: "rgba(251,249,244,.94)", borderColor: "var(--border)", color: "var(--text-secondary)" }}>
              {LEGEND.map(([c, label]) => <span key={label} className="inline-flex items-center gap-1.5"><i className="inline-block h-[9px] w-[9px] rounded-full" style={{ background: c }} />{label}</span>)}
            </div>
          </div>
          {(open || openLot) && (
            <div ref={card} className="m-3 scroll-mt-3 rounded-xl border px-4 pt-4 pb-3 min-[960px]:absolute min-[960px]:top-4 min-[960px]:right-4 min-[960px]:m-0 min-[960px]:max-h-[calc(100%-32px)] min-[960px]:w-[340px] min-[960px]:overflow-auto min-[960px]:shadow-[0_8px_24px_rgba(20,19,15,.16)]"
              style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
              {open && view && <HouseholdCard key={open.id} h={open} view={view} focus={selected?.kind === "home" ? selected.focus : undefined} onClose={() => setSelected(null)} onChanged={changed} />}
              {openLot && (
                <div role="dialog" aria-label={openLot.name} className="relative">
                  <button type="button" onClick={() => setSelected(null)} aria-label="Close" className="absolute -top-1 -right-1 rounded-md p-1 hover:bg-[var(--surface-2)]" style={muted}>
                    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
                  </button>
                  <StagingCard key={openLot.building_id} lot={openLot} chosen={!!lots?.chosen} basis={lots?.basis ?? null} onChanged={() => { setSelected(null); changed(); }} />
                </div>
              )}
            </div>
          )}
        </div>

        <aside aria-label="Dispatch rail" className="border-t min-[960px]:overflow-auto min-[960px]:border-t-0 min-[960px]:border-l" style={{ borderColor: "var(--border)" }}>
          {!view && <p className="px-6 py-4 text-[13px]" style={muted}>{error ? "The board did not load." : "Loading the board…"}</p>}
          {view && (<>
          <Section title="Needs you" n={needs.length + proposals.length + calls.length} tint>
            {needs.length + proposals.length + calls.length === 0 && <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>Nothing needs you.</p>}
            <div className="divide-y divide-[#ecd9cc]">
              {needs.map(({ h, n }) => n?.kind === "blocked" && (
                <Blocked key={h.id} h={h} leads={n.leads} noRefuge={n.noRefuge} onChanged={changed} onSeeLeads={() => setSelected({ kind: "home", id: h.id, focus: "leads" })} />
              ))}
              {proposals.map((p) => (
                <ProposalCard key={p.proposal_id} proposal={p} onDecided={changed}
                  title={`Move ${street(byId.get(p.patient_id)?.address ?? null)} to ${p.options[0]?.name ?? "a refuge"}?`} />
              ))}
              {calls.map((c) => (
                <div key={c.call_id} className="py-2">
                  <p className="font-semibold">Call from {c.phone ?? "an unknown number"} · registration not finished</p>
                  <p className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
                    Confirmed: {Object.entries(c.facts).filter(([k, v]) => v !== null && !["has_equipment", "home_confirmed"].includes(k))
                      .map(([k, v]) => `${words(k)} ${String(v)}`).join(", ") || "nothing yet"}. Call them back.
                  </p>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Agents at work" n={working.length}>
            {working.length === 0 && <p className="text-[13px]" style={muted}>No agent is working. A registration or a request no refuge fits starts one.</p>}
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {working.map((run) => <AgentItem key={run.run_id} run={run} trigger={trigger(run)} />)}
            </div>
          </Section>

          <Section title="Help in progress" n={queue.length}>
            {queue.length === 0 && <p className="text-[13px]" style={muted}>No one is waiting for help.</p>}
            {queue.map((h, i) => {
              const state = pin(h, view!);
              const r = h.request!;
              return (
                <button key={h.id} type="button" onClick={() => setSelected({ kind: "home", id: h.id })}
                  className="grid w-full grid-cols-[20px_1fr] gap-2 rounded-md py-1.5 text-left text-[13px] hover:bg-[var(--surface-2)]">
                  <span className="tnum text-right" style={muted}>{r.rank ?? i + 1}</span>
                  <span>
                    <span className="block">
                      {street(h.address)} · {words(h.patient.device)}{" "}
                      <span className="ml-1 inline-block rounded-full px-[7px] text-xs" style={state.state === "moving" ? { background: "#e3edfa", color: "#1f5fae" } : { background: "#f6ecd2", color: "#7d5600" }}>
                        {state.note}
                      </span>
                    </span>
                    <span className="block text-xs" style={muted}>{r.reason || (r.ranked_by === "rule" ? "Ordered by the risk-per-hour rule; the model did not answer" : "")}</span>
                  </span>
                </button>
              );
            })}
          </Section>

          <Section title="Crews" n={view?.crews.length ?? 0}>
            {view?.crews.length === 0 && <p className="text-[13px]" style={muted}>No crew has set up yet.</p>}
            <div className="grid gap-1 text-[13px]">
              {view?.crews.map(({ crew, patient_id }) => (
                <div key={crew.crew_id} className="flex justify-between gap-3">
                  <span>{crew.crew_id} · {VEHICLES[crew.vehicle]}{crew.equipment.length ? ` · ${crew.equipment.map((e) => EQUIPMENT[e]).join(", ")}` : ""}</span>
                  <span className="text-right" style={muted}>{onCrew(patient_id) ?? (crew.on_duty ? "free" : "off duty")}</span>
                </div>
              ))}
            </div>
          </Section>
          </>)}
        </aside>
      </div>
    </div>
  );
}
