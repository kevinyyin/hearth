"use client";

import { useEffect, useState } from "react";
import { RUN_HOURS } from "@/lib/simulation";

/**
 * The clock both runs play on, in simulated hours. `hourMs` is one hour at 1×;
 * the speed can change mid-run without a jump, because only the rate changes.
 * Anything passed as `resetOn` sends the run back to hour 0.
 */
export function useRunClock(hourMs: number, resetOn: unknown) {
  const [time, setTime] = useState(0);
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    if (!running) return;
    let last = performance.now();
    let raf = requestAnimationFrame(function tick(now) {
      const step = ((now - last) / hourMs) * speed;
      last = now;
      setTime((t) => Math.min(t + step, RUN_HOURS));
      raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [running, speed, hourMs]);

  useEffect(() => {
    if (time >= RUN_HOURS) setRunning(false);
  }, [time]);

  // a population arriving mid-run would be two different answers in one picture
  useEffect(() => {
    setTime(0);
    setRunning(false);
  }, [resetOn]);

  const start = () => {
    setTime(0);
    setRunning(true);
  };

  return { time, hour: Math.floor(time), running, start, speed, setSpeed };
}

export function SpeedControl({ speed, onChange }: { speed: number; onChange: (s: number) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
      Speed
      <input
        type="range"
        min={0.25}
        max={8}
        step={0.25}
        value={speed}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={`${speed} times`}
        className="w-28"
        style={{ accentColor: "var(--text-primary)" }}
      />
      <span className="tnum w-9 font-semibold" style={{ color: "var(--text-primary)" }}>
        {speed}×
      </span>
    </label>
  );
}
