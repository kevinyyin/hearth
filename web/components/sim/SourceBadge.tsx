"use client";

import type { SourceKind } from "@/lib/simSource";

/**
 * Says which data answered. Drop it into any panel that can run on either the
 * API or a fixture — one line, no other wiring:
 *
 *   <SourceBadge source={source} detail={detail} error={error} />
 *
 * The point is that "did the integration work" is a thing you see on the page,
 * not something you go and read a console for.
 */
export default function SourceBadge({
  source,
  detail,
  error,
  className = "",
}: {
  source: SourceKind;
  detail: string;
  error?: string | null;
  className?: string;
}) {
  const live = source === "api";

  return (
    <p
      className={`inline-flex flex-wrap items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${className}`}
      style={{
        borderColor: live ? "#0e7a54" : "var(--border)",
        color: live ? "#0b5c3e" : "var(--text-secondary)",
        background: live ? "#def0e6" : "transparent",
      }}
    >
      <span
        aria-hidden="true"
        className="inline-block size-2 rounded-full"
        style={{ background: live ? "#0e7a54" : "var(--text-muted)" }}
      />
      {live ? "Live from the Hearth API" : "Fixture"}
      {detail && <> · {detail}</>}
      {error && <span style={{ color: "#7a2e12" }}>· API unreachable: {error}</span>}
    </p>
  );
}
