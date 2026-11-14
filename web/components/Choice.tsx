import type { ReactNode } from "react";

/** A toggle in a row of choices (pin kind, size, vehicle, equipment). */
export default function Choice({ on, color, onClick, children }: { on: boolean; color?: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className="rounded border px-2.5 py-1 text-xs font-medium"
      style={on ? { background: color ?? "var(--text-primary)", borderColor: color ?? "var(--text-primary)", color: color ? "#fff" : "var(--surface-1)" }
        : { borderColor: "var(--border)", color: "var(--text-secondary)" }}
    >
      {children}
    </button>
  );
}
