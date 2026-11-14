"use client";

import type { AccessBrief as Brief } from "@/lib/types";

const Part = ({ title, lines, empty }: { title: string; lines: string[]; empty: string }) => (
  <div>
    <p className="font-medium">{title}</p>
    {lines.length ? (
      <ul className="list-disc pl-4" style={{ color: "var(--text-secondary)" }}>{lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
    ) : (
      <p style={{ color: "var(--text-muted)" }}>{empty}</p>
    )}
  </div>
);

/** One screen for a crew, built only from layer-sourced fields. The scan shows a unit type, never the patient's own rooms.
 *  `scanShown`: a scan is on screen beside this brief, so an empty inside part means it was not surveyed, not that it is missing. */
export default function AccessBrief({ brief, scanShown = false }: { brief: Brief; scanShown?: boolean }) {
  return (
    <section className="space-y-2 text-xs">
      <h4 className="font-semibold" style={{ color: "var(--text-muted)" }}>Crew access brief</h4>
      <Part title="Getting to the door" lines={brief.to_door} empty="No layer showed stories, elevators or where to stop." />
      <Part title="Inside the unit" lines={brief.inside_unit}
        empty={scanShown ? "The agent has not surveyed this scan yet: rooms and widths are not listed." : "No 3D scan: the layout inside is not shown."} />
    </section>
  );
}
