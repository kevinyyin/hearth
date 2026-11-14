"use client";

import { formatTick } from "@/lib/snapshots";

export default function TimeSlider({
  ticks,
  index,
  onChange,
  loading,
}: {
  ticks: string[];
  index: number;
  onChange: (i: number) => void;
  loading: boolean;
}) {
  const last = Math.max(ticks.length - 1, 0);

  return (
    <div
      className="flex items-center gap-4 border-t px-5 py-3"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onChange(Math.max(index - 1, 0))}
          disabled={index === 0}
          aria-label="Previous tick"
          className="rounded-md border px-2 py-1 text-sm disabled:opacity-35"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          ‹
        </button>
        <button
          type="button"
          onClick={() => onChange(Math.min(index + 1, last))}
          disabled={index >= last}
          aria-label="Next tick"
          className="rounded-md border px-2 py-1 text-sm disabled:opacity-35"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          ›
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={last}
        step={1}
        value={index}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Outage time"
        aria-valuetext={formatTick(ticks[index] ?? "")}
        className="h-1.5 min-w-0 flex-1 cursor-pointer appearance-none rounded-full"
        style={{ accentColor: "var(--series-1)", background: "var(--grid)" }}
      />

      <div className="flex w-56 shrink-0 items-center justify-end gap-2">
        {loading && (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            loading…
          </span>
        )}
        <span className="tnum text-sm font-medium">{formatTick(ticks[index] ?? "")}</span>
        <span className="tnum text-xs" style={{ color: "var(--text-muted)" }}>
          {index + 1}/{ticks.length}
        </span>
      </div>
    </div>
  );
}
