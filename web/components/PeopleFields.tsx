"use client";

import type { Person } from "@/lib/types";

const MAX_PEOPLE = 5; // the API's cap
const EMPTY: Person = { name: "", relation: "", phone: "", note: "" };
const field = "w-full rounded border px-2 py-1.5 text-sm";
const fieldStyle = { borderColor: "var(--border)", background: "var(--surface-0)", color: "var(--text-primary)" };

/** A short editable list of people the resident names. Rows left without a name are not saved. */
export default function PeopleFields({ people, onChange, addLabel, notePlaceholder }: {
  people: Person[];
  onChange: (people: Person[]) => void;
  addLabel: string;
  notePlaceholder: string;
}) {
  const edit = (i: number, patch: Partial<Person>) => onChange(people.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <div className="space-y-3">
      {people.map((p, i) => (
        <fieldset key={i} className="space-y-1.5">
          <legend className="sr-only">Person {i + 1}</legend>
          <div className="grid grid-cols-2 gap-1.5">
            <input aria-label="Name" placeholder="Name" maxLength={80} value={p.name} className={field} style={fieldStyle}
              onChange={(e) => edit(i, { name: e.target.value })} />
            <input aria-label="Relation" placeholder="Relation" maxLength={40} value={p.relation} className={field} style={fieldStyle}
              onChange={(e) => edit(i, { relation: e.target.value })} />
          </div>
          <input aria-label="Phone" type="tel" placeholder="Phone" maxLength={30} value={p.phone} className={field} style={fieldStyle}
            onChange={(e) => edit(i, { phone: e.target.value.replace(/[^0-9+() .-]/g, "") })} />
          <input aria-label="Note" placeholder={notePlaceholder} maxLength={200} value={p.note} className={field} style={fieldStyle}
            onChange={(e) => edit(i, { note: e.target.value })} />
          <button type="button" className="text-xs underline underline-offset-2" style={{ color: "var(--text-secondary)" }}
            onClick={() => onChange(people.filter((_, j) => j !== i))}>
            Remove{p.name ? ` ${p.name}` : ""}
          </button>
        </fieldset>
      ))}
      {people.length < MAX_PEOPLE && (
        <button type="button" className="rounded border px-2.5 py-1 text-xs font-medium" style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
          onClick={() => onChange([...people, EMPTY])}>
          {addLabel}
        </button>
      )}
    </div>
  );
}

/** The same people, read-only, one line each, for the responder. */
export function PeopleList({ people }: { people: Person[] }) {
  return (
    <ul className="space-y-0.5 text-sm">
      {people.map((p, i) => (
        <li key={i}>
          {p.name}{p.relation && ` (${p.relation})`}
          {p.phone && <> · <a href={`tel:${p.phone.replace(/[^0-9+]/g, "")}`} className="underline underline-offset-2">{p.phone}</a></>}
          {p.note && ` · ${p.note}`}
        </li>
      ))}
    </ul>
  );
}
