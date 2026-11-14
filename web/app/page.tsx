import Link from "next/link";

/**
 * Placeholder home page. Part 2 of task C replaces this with the map and time slider.
 */
export default function HomePage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Hearth</h1>
      <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-secondary)" }}>
        A dispatcher tool for people on power-dependent home medical devices during a multi-day
        outage. The outage map with a time slider lands here next.
      </p>
      <Link
        href="/results"
        className="mt-6 inline-block rounded-lg border px-4 py-2 text-sm font-medium"
        style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
      >
        Results: patient-hours at risk by crew count →
      </Link>
    </div>
  );
}
