"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CallTranscript from "@/components/sim/CallTranscript";
import CoverageMap from "@/components/sim/CoverageMap";
import EmsOffer from "@/components/sim/EmsOffer";
import BuildingViews from "@/components/sim/BuildingViews";
import FullRun from "@/components/sim/FullRun";
import { useResidentFeed } from "@/lib/simSource";
import {
  ENROLMENT_CALL,
  ENROLMENT_FIELDS,
  EVENT_CALL,
  EVENT_CALL_ASK_LINE,
  EVENT_PHASES,
  HELP_REQUEST,
  RUN_HOURS,
  type Actor,
  type EventPhase,
  type TranscriptLine,
} from "@/lib/simulation";

/** Calls run faster than real time so the whole thing fits a demo. */
const SPEED = 0.4;
/** How long an automatic step sits on screen before it takes itself. */
const AUTO_MS = 1100;

type Stage = "intro" | "enrol" | "enrolled" | "event" | "full";
type CallMode = "simulated" | "real";

/** Reveals transcript lines on their own timings, and can be cut short. */
function useReveal(lines: TranscriptLine[], active: boolean) {
  const [n, setN] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clear = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => {
    // Going inactive leaves the lines on screen: a dispatcher still wants to read
    // the call after it has ended. Only starting a call clears the box.
    if (!active) return;
    clear();
    setN(0);
    timers.current = lines.map((l, i) =>
      setTimeout(() => setN(i + 1), Math.round(l.at * SPEED)),
    );
    return clear;
  }, [active, lines, clear]);

  /** Skipping has to kill the pending timers, or the next one drags the log back. */
  const finish = useCallback(() => {
    clear();
    setN(lines.length);
  }, [clear, lines.length]);

  const reset = useCallback(() => {
    clear();
    setN(0);
  }, [clear]);

  return { n, finish, reset };
}

function Section({
  title,
  side,
  children,
}: {
  title: string;
  side: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex min-h-0 flex-col rounded-xl border"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
    >
      <div className="shrink-0 border-b px-5 py-3" style={{ borderColor: "var(--border)" }}>
        <p
          className="text-[11px] font-semibold tracking-wide uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          {side}
        </p>
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
    </section>
  );
}

function StepButton({
  label,
  hint,
  onClick,
  tone = "accent",
}: {
  label: string;
  hint?: string;
  onClick: () => void;
  tone?: "accent" | "dark";
}) {
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={onClick}
        className="w-full rounded-lg px-4 py-3.5 text-sm font-semibold"
        style={
          tone === "accent"
            ? { background: "var(--accent)", color: "#fbf9f4", minHeight: 48 }
            : { background: "var(--text-primary)", color: "var(--surface-0)", minHeight: 48 }
        }
      >
        {label}
      </button>
      {hint && (
        <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {hint}
        </p>
      )}
    </div>
  );
}

export default function SimulationPage() {
  // The record, the pins and the building facts come from the API when one is
  // reachable; the call itself is always the placeholder, since the voice lane
  // owns the real one.
  const residentFeed = useResidentFeed();
  const resident = residentFeed.resident;

  const [stage, setStage] = useState<Stage>("intro");
  const [showTranscript, setShowTranscript] = useState(true);
  const [phaseIdx, setPhaseIdx] = useState(0);

  const [callMode, setCallMode] = useState<CallMode>("simulated");
  const [realNumber, setRealNumber] = useState("");
  const [realCallNote, setRealCallNote] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [askedOnCall, setAskedOnCall] = useState(false);
  const [fields, setFields] = useState(ENROLMENT_FIELDS.map((f) => ({ ...f })));

  const current = EVENT_PHASES[phaseIdx];
  const phase: EventPhase = current.phase;
  const step = current.next;

  const enrolActive = stage === "enrol";
  const callActive = stage === "event" && phase === "calling";

  const enrol = useReveal(ENROLMENT_CALL, enrolActive);
  const event = useReveal(EVENT_CALL, callActive);

  const callDone = enrol.n >= ENROLMENT_CALL.length;

  const advance = useCallback(
    () => setPhaseIdx((i) => Math.min(i + 1, EVENT_PHASES.length - 1)),
    [],
  );
  const stepBy = (who: Actor) => (step && step.by === who && !step.auto ? step : null);

  // The two steps Hearth takes without being told: dialling, and routing the request.
  useEffect(() => {
    if (stage !== "event" || !step?.auto) return;
    const t = setTimeout(advance, AUTO_MS);
    return () => clearTimeout(t);
  }, [stage, step, advance]);

  // Most people ask the person they are already talking to. Once that line is said
  // the request exists, so the button gives way to a note and the run moves on.
  useEffect(() => {
    if (!callActive || event.n <= EVENT_CALL_ASK_LINE) return;
    setAskedOnCall(true);
    const t = setTimeout(advance, AUTO_MS);
    return () => clearTimeout(t);
  }, [callActive, event.n, advance]);

  const startEvent = () => {
    setPhaseIdx(0);
    setStage("event");
  };

  const restart = () => {
    setStage("intro");
    setPhaseIdx(0);
    setEditing(false);
    setAskedOnCall(false);
    setRealCallNote(null);
    setFields(ENROLMENT_FIELDS.map((f) => ({ ...f })));
    enrol.reset();
    event.reset();
  };

  const transcript = useMemo(() => {
    if (stage === "enrol" || stage === "enrolled") {
      return {
        lines: ENROLMENT_CALL,
        revealed: stage === "enrolled" ? ENROLMENT_CALL.length : enrol.n,
        title: `Enrollment call · ${callMode === "real" ? realNumber || "no number yet" : resident.phone}`,
        live: stage === "enrol" && !callDone,
      };
    }
    return {
      lines: EVENT_CALL,
      revealed: event.n,
      title: `Outage call · ${resident.phone}`,
      live: callActive && event.n < EVENT_CALL.length,
    };
  }, [stage, enrol.n, event.n, callActive, callDone, callMode, realNumber]);

  const phaseReached = (p: EventPhase) =>
    EVENT_PHASES.findIndex((x) => x.phase === p) <= phaseIdx;

  // the county panel follows the steps rather than its own clock
  const countyHour =
    stage === "event"
      ? Math.round((phaseIdx / (EVENT_PHASES.length - 1)) * RUN_HOURS)
      : 0;

  /** A field is known once the resident's answer to it has been said. */
  const landed = (label: string) =>
    stage === "enrolled" || enrol.n > (ENROLMENT_FIELDS.find((f) => f.label === label)?.after ?? Infinity);
  const entranceKnown = landed("Entrance");

  return (
    <div className="min-h-full">
      <div className="mx-auto max-w-[1500px] px-6 py-6 pb-24">
        {/* ---------- header ---------- */}
        <header className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Link href="/results" className="display text-2xl" style={{ color: "var(--text-primary)" }}>
            Hearth
          </Link>
          <div className="flex-1">
            <h1 className="text-lg font-semibold">Simulation</h1>
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {stage === "event"
                ? `During the event · ${current.clock}`
                : stage === "intro"
                  ? "Three ways in: one household, step by step, or the whole county"
                  : stage === "full"
                    ? "The whole county, both ways at once"
                    : "Before the event · enrollment"}
            </p>
          </div>

          {!showTranscript && (
            <button
              type="button"
              onClick={() => setShowTranscript(true)}
              className="rounded-lg border px-3 py-2 text-sm font-medium"
              style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
            >
              Show transcript
            </button>
          )}
          {stage !== "intro" && (
            <button
              type="button"
              onClick={restart}
              className="rounded-lg border px-3 py-2 text-sm font-medium"
              style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
            >
              Restart
            </button>
          )}
          <Link
            href="/results"
            className="rounded-lg px-4 py-2 text-sm font-semibold"
            style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
          >
            Back to results
          </Link>
        </header>

        {/* ---------- intro ---------- */}
        {stage === "intro" && (
          <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
            <section
              className="rounded-xl border p-8"
              style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
            >
              <h2 className="display text-4xl leading-tight">
                Two moments decide whether anyone reaches this household
              </h2>
              <p className="mt-5 text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                The first is months before any storm, when the equipment supplier tells the county
                someone has a device that needs mains power. The second is the night the power goes
                out. Hearth is the thing that connects them.
              </p>

              <ol className="mt-7 space-y-4">
                <li className="flex gap-4">
                  <span className="display shrink-0 text-3xl leading-none" style={{ color: "var(--accent)" }}>
                    1
                  </span>
                  <span className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>Before the event.</strong> A call
                    goes out to enroll the household, and what they say becomes their record.
                  </span>
                </li>
                <li className="flex gap-4">
                  <span className="display shrink-0 text-3xl leading-none" style={{ color: "var(--accent)" }}>
                    2
                  </span>
                  <span className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>During the event.</strong> The
                    outage starts, Hearth calls them on its own, and a responder gets a job with the
                    access details already attached.
                  </span>
                </li>
                <li className="flex gap-4">
                  <span className="display shrink-0 text-3xl leading-none" style={{ color: "var(--accent)" }}>
                    3
                  </span>
                  <span className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>The whole county.</strong> Both
                    ways at once, with the call logs and the vans, so you can see where the
                    difference actually comes from.
                  </span>
                </li>
              </ol>

              {/* --- how the call is placed --- */}
              <div
                className="mt-7 rounded-xl border p-5"
                style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
              >
                <h3 className="mb-3 text-sm font-semibold">How to place the enrollment call</h3>
                <div
                  role="group"
                  aria-label="Call mode"
                  className="mb-4 inline-flex rounded-lg border p-1"
                  style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
                >
                  {(["simulated", "real"] as CallMode[]).map((m) => (
                    <button
                      key={m}
                      type="button"
                      aria-pressed={callMode === m}
                      onClick={() => {
                        setCallMode(m);
                        setRealCallNote(null);
                      }}
                      className="rounded-md px-4 text-sm font-semibold"
                      style={{
                        minHeight: 40,
                        background: callMode === m ? "var(--text-primary)" : "transparent",
                        color: callMode === m ? "var(--surface-0)" : "var(--text-secondary)",
                      }}
                    >
                      {m === "simulated" ? "Simulated call" : "Real phone call"}
                    </button>
                  ))}
                </div>

                {callMode === "real" && (
                  <div>
                    <label
                      htmlFor="real-number"
                      className="mb-1.5 block text-sm font-medium"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Number to call
                    </label>
                    <input
                      id="real-number"
                      type="tel"
                      inputMode="tel"
                      placeholder="+1 713 555 0147"
                      value={realNumber}
                      onChange={(e) => {
                        setRealNumber(e.target.value);
                        setRealCallNote(null);
                      }}
                      className="w-full rounded-lg border px-3.5 py-3 text-base"
                      style={{
                        borderColor: "var(--border)",
                        background: "var(--surface-1)",
                        color: "var(--text-primary)",
                        minHeight: 48,
                      }}
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setRealCallNote(
                          realNumber.trim()
                            ? "Not connected. Placing a real call needs the voice lane's outbound number, which does not exist yet — spec v6 lists it as blocked on the Photon account, and no real call has been placed from this repo. Nothing was dialled."
                            : "Enter a number first.",
                        )
                      }
                      className="mt-3 rounded-lg border px-4 py-2.5 text-sm font-semibold"
                      style={{ borderColor: "var(--text-primary)", color: "var(--text-primary)" }}
                    >
                      Place the call
                    </button>
                    {realCallNote && (
                      <p
                        className="mt-3 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
                        style={{ background: "#fbeee6", color: "#7a2e12" }}
                      >
                        {realCallNote}
                      </p>
                    )}
                    <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                      The control is here so the voice lane has somewhere to connect. Until then,
                      run the simulated call.
                    </p>
                  </div>
                )}
              </div>

              <p className="mt-6 text-sm" style={{ color: "var(--text-secondary)" }}>
                Apart from Hearth dialling and routing the request, every step is a click, by
                whoever would really take it.
              </p>

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => setStage("enrol")}
                  className="rounded-lg px-6 py-3.5 text-base font-semibold"
                  style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
                >
                  Start stage 1 — the enrollment call
                </button>
                <button
                  type="button"
                  onClick={() => setStage("full")}
                  className="rounded-lg border px-6 py-3.5 text-base font-semibold"
                  style={{ borderColor: "var(--text-primary)", color: "var(--text-primary)" }}
                >
                  3. Run a full simulation
                </button>
              </div>
            </section>

            <div className="space-y-4">
              <CoverageMap hour={0} />
              <p
                className="rounded-xl border px-4 py-3 text-xs leading-relaxed"
                style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
              >
                Every call, transcript and record in this simulation is a fixed placeholder written
                into the page. The real enrollment call, its wording and the resident record belong to
                the registration lane, and this screen is built to have them dropped in.
              </p>
            </div>
          </div>
        )}

        {/* ---------- stage 3: the whole county ---------- */}
        {stage === "full" && <FullRun />}

        {/* ---------- stage 1 ---------- */}
        {(stage === "enrol" || stage === "enrolled") && (
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <Section side="Stage 1 · before the event" title="Enrolling the household">
              <div
                className="mb-5 rounded-xl border p-5"
                style={{ background: "var(--surface-0)", borderColor: "var(--border)" }}
              >
                <p className="text-[11px] tracking-wide uppercase" style={{ color: "var(--text-muted)" }}>
                  Calling
                </p>
                <p className="tnum display mt-1 text-3xl">
                  {callMode === "real" && realNumber ? realNumber : resident.phone}
                </p>
                <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                  {resident.name} · {resident.device} · simulated
                </p>
                <p className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>
                  {stage === "enrolled"
                    ? `Call ended. ${fields.length} fields captured.`
                    : callDone
                      ? "The call has ended."
                      : "On the call. The transcript is being written as it goes."}
                </p>
              </div>

              <h3 className="mb-3 text-sm font-semibold">What the call captured</h3>
              <dl className="space-y-0">
                {fields.map((f) => (
                  <div
                    key={f.label}
                    className="flex items-baseline justify-between gap-4 border-b py-2.5 last:border-b-0"
                    style={{ borderColor: "var(--border)", opacity: landed(f.label) ? 1 : 0.35 }}
                  >
                    <dt className="text-sm" style={{ color: "var(--text-muted)" }}>
                      {f.label}
                    </dt>
                    <dd className="m-0 text-right text-sm font-medium">
                      {landed(f.label) ? f.value : "—"}
                    </dd>
                  </div>
                ))}
              </dl>

              {/* the markers the call produced, and a route planned over the layout */}
              {entranceKnown && (
                <div className="mt-6">
                  <h3 className="mb-1 text-sm font-semibold">Where the call put the markers</h3>
                  <p className="mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
                    The aerial tile and the scan for this building, with what the call captured on
                    them.
                  </p>
                  <BuildingViews
                    buildingId={residentFeed.buildingId}
                    preferredScanId={residentFeed.scanId}
                    outside={residentFeed.outside}
                    inside={residentFeed.inside}
                  />
                </div>
              )}

              {stage === "enrol" && !callDone && (
                <button
                  type="button"
                  onClick={enrol.finish}
                  className="mt-5 rounded-lg border px-4 py-2.5 text-sm font-medium"
                  style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
                >
                  Skip to the end of the call
                </button>
              )}

              {/* the profile is corrected before it is confirmed, on this screen rather than another */}
              {stage === "enrol" && callDone && editing && (
                <form
                  className="mt-5 space-y-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setEditing(false);
                  }}
                >
                  {fields.map((f, i) => (
                    <div key={f.label}>
                      <label
                        htmlFor={`field-${i}`}
                        className="mb-1 block text-xs font-medium"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {f.label}
                      </label>
                      <input
                        id={`field-${i}`}
                        value={f.value}
                        onChange={(e) =>
                          setFields((prev) =>
                            prev.map((p, j) =>
                              j === i ? { ...p, value: e.target.value } : p,
                            ),
                          )
                        }
                        className="w-full rounded-lg border px-3 py-2.5 text-sm"
                        style={{
                          borderColor: "var(--border)",
                          background: "var(--surface-1)",
                          color: "var(--text-primary)",
                          minHeight: 44,
                        }}
                      />
                    </div>
                  ))}
                  <div className="flex flex-wrap gap-3 pt-1">
                    <button
                      type="submit"
                      className="rounded-lg px-4 py-2.5 text-sm font-semibold"
                      style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setFields(ENROLMENT_FIELDS.map((f) => ({ ...f })));
                        setEditing(false);
                      }}
                      className="rounded-lg border px-4 py-2.5 text-sm font-medium"
                      style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {stage === "enrol" && callDone && !editing && (
                <>
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="mt-5 w-full rounded-lg border px-4 py-3 text-sm font-semibold"
                    style={{ borderColor: "var(--text-primary)", color: "var(--text-primary)", minHeight: 48 }}
                  >
                    Edit profile
                  </button>
                  <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    Anything said on the call can be corrected before it is confirmed. Edits stay on
                    this screen; the registration lane&rsquo;s full editor is still being built.
                  </p>
                  <StepButton
                    label="Finish enrollment"
                    hint="The operator confirms what the call captured."
                    onClick={() => setStage("enrolled")}
                  />
                </>
              )}

              {stage === "enrolled" && (
                <div
                  className="mt-6 rounded-xl border-2 p-5"
                  style={{ borderColor: "var(--accent)", background: "var(--surface-0)" }}
                >
                  <p className="text-sm font-semibold">Enrolled.</p>
                  <p className="mt-1.5 text-sm" style={{ color: "var(--text-secondary)" }}>
                    The profile is confirmed. A dispatcher will see it if the power goes out.
                  </p>

                  <div className="mt-4">
                    <button
                      type="button"
                      onClick={startEvent}
                      className="rounded-lg border px-4 py-2.5 text-sm font-semibold"
                      style={{ borderColor: "var(--text-primary)", color: "var(--text-primary)" }}
                    >
                      Continue to stage 2
                    </button>
                  </div>
                </div>
              )}
            </Section>

            {showTranscript ? (
              /* a fixed height, so the log scrolls inside itself instead of growing the page */
              <div className="h-[560px]">
                <CallTranscript
                  lines={transcript.lines}
                  revealed={transcript.revealed}
                  title={transcript.title}
                  live={transcript.live}
                  onHide={() => setShowTranscript(false)}
                />
              </div>
            ) : (
              <CoverageMap hour={0} />
            )}
          </div>
        )}

        {/* ---------- stage 2 ---------- */}
        {stage === "event" && (
          <>
            <div
              className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border-2 px-5 py-3"
              style={{
                borderColor: phaseReached("warning") ? "var(--accent)" : "var(--border)",
                background: "var(--surface-1)",
              }}
            >
              <span
                aria-hidden="true"
                className="inline-block size-2.5 rounded-full"
                style={{ background: "var(--accent)" }}
              />
              <p className="flex-1 text-sm font-medium">
                {phaseReached("warning")
                  ? "Simulated event · Hurricane Beryl replay · widespread outage across Harris County"
                  : "Calm. The outage has not started."}
              </p>
              <span className="tnum text-sm" style={{ color: "var(--text-secondary)" }}>
                {current.clock}
              </span>

              {stepBy("operator") && (
                <button
                  type="button"
                  onClick={advance}
                  className="rounded-lg px-4 py-2.5 text-sm font-semibold"
                  style={{ background: "var(--text-primary)", color: "var(--surface-0)", minHeight: 44 }}
                >
                  {stepBy("operator")?.label}
                </button>
              )}
              {step?.auto && (
                <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>
                  {step.label}
                </span>
              )}
              {!step && (
                <span className="text-sm font-semibold" style={{ color: "#0b5c3e" }}>
                  Run complete
                </span>
              )}
            </div>

            <div className="grid gap-5 xl:grid-cols-3">
              {/* user side */}
              <Section side="User side" title={`${resident.name} · simulated`}>
                {!phaseReached("warning") && (
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Nothing on screen. The power is on.
                  </p>
                )}

                {phaseReached("warning") && (
                  <div
                    className="mb-4 rounded-xl border-2 p-4"
                    style={{ borderColor: "var(--accent)", background: "#fbeee6" }}
                  >
                    <p className="text-sm font-semibold" style={{ color: "#7a2e12" }}>
                      Power outage in your area
                    </p>
                    <p className="mt-1 text-sm" style={{ color: "#7a2e12" }}>
                      Expected to last through tonight. Your concentrator has about 4 hours of
                      battery.
                    </p>
                  </div>
                )}

                {phaseReached("calling") && !phaseReached("requested") && (
                  <div
                    className="mb-4 rounded-xl border p-4"
                    style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
                  >
                    <p className="text-[11px] tracking-wide uppercase" style={{ color: "var(--text-muted)" }}>
                      Incoming call
                    </p>
                    <p className="display mt-1 text-2xl">Hearth · Harris County</p>
                    <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                      Answered. The transcript is on the right.
                    </p>
                  </div>
                )}

                {phaseReached("requested") && (
                  <div className="space-y-3">
                    <div
                      className="rounded-xl border p-4"
                      style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
                    >
                      <p className="text-sm font-semibold">Help requested</p>
                      <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                        {HELP_REQUEST.summary}
                      </p>
                    </div>

                    <ol className="space-y-2.5">
                      {[
                        ["requested", "Request sent to a dispatcher"],
                        ["offered", "A dispatcher is looking at it"],
                        ["accepted", "A crew accepted"],
                        ["enroute", "Crew on the way"],
                        ["arrived", "Crew at the north door"],
                      ].map(([p, label]) => {
                        const done = phaseReached(p as EventPhase);
                        return (
                          <li key={p} className="flex items-center gap-3 text-sm">
                            <span
                              aria-hidden="true"
                              className="inline-block size-2.5 shrink-0 rounded-full"
                              style={{ background: done ? "#0e7a54" : "var(--border)" }}
                            />
                            <span style={{ color: done ? "var(--text-primary)" : "var(--text-muted)" }}>
                              {label}
                            </span>
                          </li>
                        );
                      })}
                    </ol>

                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      No line here promises a crew is coming until one has accepted.
                    </p>
                  </div>
                )}

                {askedOnCall && (
                  <p
                    className="mt-4 rounded-lg px-4 py-3 text-sm font-medium"
                    style={{ background: "#fbeee6", color: "#7a2e12" }}
                  >
                    Caller requested help over the phone
                  </p>
                )}

                {stepBy("resident") && !askedOnCall && (
                  <StepButton
                    label={stepBy("resident")!.label}
                    hint={stepBy("resident")!.hint}
                    onClick={advance}
                  />
                )}
              </Section>

              {/* ems side */}
              <Section side="Responder side" title="Crew 7 · wheelchair van">
                {!phaseReached("offered") && (
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    No open jobs. Waiting.
                  </p>
                )}

                {phaseReached("offered") && (
                  <EmsOffer accepted={phaseReached("accepted")} onAccept={advance} buildingLabel={resident.buildingLabel} />
                )}

                {phaseReached("accepted") && (
                  <div
                    className="mt-5 rounded-xl border p-5"
                    style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
                  >
                    <BuildingViews
                      buildingId={residentFeed.buildingId}
                    preferredScanId={residentFeed.scanId}
                      outside={residentFeed.outside}
                      inside={residentFeed.inside}
                    />

                    <ul className="mt-4 space-y-2.5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
                      {resident.pins.map((pin) => (
                        <li key={pin.kind} className="flex gap-3 text-sm">
                          <span
                            className="shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase"
                            style={{
                              background:
                                pin.kind === "blocked"
                                  ? "#f6e0d6"
                                  : pin.kind === "entrance"
                                    ? "#def0e6"
                                    : "var(--surface-2, var(--surface-1))",
                              color:
                                pin.kind === "blocked"
                                  ? "#7a2e12"
                                  : pin.kind === "entrance"
                                    ? "#0b5c3e"
                                    : "var(--text-secondary)",
                            }}
                          >
                            {pin.kind}
                          </span>
                          <span style={{ color: "var(--text-secondary)" }}>{pin.note}</span>
                        </li>
                      ))}
                    </ul>
                    <dl className="mt-4 space-y-1.5 border-t pt-4 text-sm" style={{ borderColor: "var(--border)" }}>
                      {fields
                        .filter((f) => f.label === "Where the device is" || f.label === "Can it be moved")
                        .map((f) => (
                          <div key={f.label} className="flex gap-3">
                            <dt className="w-36 shrink-0" style={{ color: "var(--text-muted)" }}>
                              {f.label}
                            </dt>
                            <dd className="m-0" style={{ color: "var(--text-secondary)" }}>{f.value}</dd>
                          </div>
                        ))}
                    </dl>
                    <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                      The blocked kerb came from the resident, not the imagery. No layer can tell you
                      what happened tonight.
                    </p>
                  </div>
                )}

                {phaseReached("enroute") && (
                  <div
                    className="mt-4 rounded-xl px-4 py-3 text-sm font-medium"
                    style={{ background: "#def0e6", color: "#0b5c3e" }}
                  >
                    {phaseReached("arrived")
                      ? "Arrived at the north door."
                      : "Driving. Eleven minutes out."}
                  </div>
                )}

                {stepBy("responder") && phase !== "offered" && (
                  <StepButton
                    label={stepBy("responder")!.label}
                    hint={stepBy("responder")!.hint}
                    onClick={advance}
                    tone="dark"
                  />
                )}
              </Section>

              {/* sidebar */}
              <div className="flex min-h-0 flex-col gap-5">
                {showTranscript ? (
                  <div className="h-[380px] shrink-0">
                    <CallTranscript
                      lines={transcript.lines}
                      revealed={transcript.revealed}
                      title={transcript.title}
                      live={transcript.live}
                      onHide={() => setShowTranscript(false)}
                    />
                  </div>
                ) : null}
                <CoverageMap hour={countyHour} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
