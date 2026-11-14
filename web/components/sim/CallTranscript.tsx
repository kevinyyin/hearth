"use client";

import { useEffect, useRef } from "react";
import type { TranscriptLine } from "@/lib/simulation";

/**
 * Presentational only: the page owns playback, so hiding the box never pauses or
 * skips the call. Styled as a chat log because that is how a dispatcher reads a
 * call they did not take themselves.
 */
export default function CallTranscript({
  lines,
  revealed,
  title,
  live,
  onHide,
}: {
  lines: TranscriptLine[];
  revealed: number;
  title: string;
  live: boolean;
  onHide: () => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);

  // Scroll the log itself, never scrollIntoView: that walks up and scrolls every
  // scrollable ancestor, so a new line would drag the whole page with it.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [revealed]);

  return (
    <aside
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
      aria-label={title}
    >
      <div
        className="flex shrink-0 items-center gap-3 border-b px-4 py-3"
        style={{ borderColor: "var(--border)" }}
      >
        <span
          aria-hidden="true"
          className="inline-block size-2 rounded-full"
          style={{ background: live ? "var(--series-2)" : "var(--text-muted)" }}
        />
        <h3 className="flex-1 text-sm font-semibold">{title}</h3>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {live ? "Live" : "Ended"}
        </span>
        <button
          type="button"
          onClick={onHide}
          className="rounded-md border px-2.5 py-1 text-xs font-medium"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          Hide
        </button>
      </div>

      <div
        ref={listRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4"
        aria-live="polite"
      >
        {revealed === 0 && (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Waiting for the call to connect…
          </p>
        )}

        {lines.slice(0, revealed).map((line, i) => {
          const fromHearth = line.from === "hearth";
          return (
            <div
              key={`${line.at}-${i}`}
              className={`flex ${fromHearth ? "justify-start" : "justify-end"}`}
            >
              <div className="max-w-[85%]">
                <p
                  className="mb-1 text-[11px] font-medium tracking-wide uppercase"
                  style={{ color: "var(--text-muted)" }}
                >
                  {fromHearth ? "Hearth" : "Resident (simulated)"}
                </p>
                <p
                  className="rounded-xl px-3 py-2 text-sm leading-relaxed"
                  style={
                    fromHearth
                      ? { background: "var(--surface-2, var(--surface-0))", color: "var(--text-primary)" }
                      : { background: "var(--accent, #a8441a)", color: "#fbf9f4" }
                  }
                >
                  {line.text}
                </p>
              </div>
            </div>
          );
        })}

        {live && revealed > 0 && revealed < lines.length && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }} aria-hidden="true">
            …
          </p>
        )}
      </div>

      <p
        className="shrink-0 border-t px-4 py-2.5 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
      >
        Placeholder transcript. The real call and its wording belong to the voice lane.
      </p>
    </aside>
  );
}
