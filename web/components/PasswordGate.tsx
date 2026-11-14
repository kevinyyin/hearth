"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { API, getJson, getPassword, setPassword } from "@/lib/api";

/** The hosted API needs a shared password. Without one stored (or after a 401) this asks for it; locally it does nothing. */
export default function PasswordGate({ children }: { children: ReactNode }) {
  const [needed, setNeeded] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNeeded(!!API && !getPassword());
    const ask = () => setNeeded(true);
    window.addEventListener("hearth-auth", ask);
    return () => window.removeEventListener("hearth-auth", ask);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPassword(value);
    try {
      await getJson("/api/runs");
      window.location.reload(); // pages fetch on load; start them over with the password
    } catch {
      setError("That password did not work.");
    }
  }

  if (!needed) return <>{children}</>;
  return (
    <form onSubmit={submit} className="mx-auto mt-24 max-w-sm space-y-3 px-6">
      <h1 className="text-lg font-semibold">Hearth</h1>
      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        A dispatcher tool replaying Hurricane Beryl over simulated patients. Enter the password you were given.
      </p>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Password"
        autoFocus
        className="w-full rounded border px-3 py-2 text-sm"
        style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
      />
      <button type="submit" className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: "#1b7f4d" }}>
        Enter
      </button>
      {error && <p className="text-sm" style={{ color: "#d03b3b" }}>{error}</p>}
    </form>
  );
}
