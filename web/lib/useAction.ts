"use client";

import { useCallback, useRef, useState } from "react";

/** In plain words: a fetch that never reached the API says so; the API's own refusals are already sentences. */
export const plainError = (e: unknown): string =>
  e instanceof TypeError ? "The Hearth API did not answer. Check the connection and try again."
  : e instanceof Error ? e.message.charAt(0).toUpperCase() + e.message.slice(1)
  : String(e);

/** One button press at a time: `busy` names the action under way (so a second press is ignored), `error` its failure. */
export function useAction(): { busy: string | null; error: string | null; act: (name: string, fn: () => Promise<unknown>) => Promise<void> } {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = useRef(false); // state lags a fast double press; the ref does not
  const act = useCallback(async (name: string, fn: () => Promise<unknown>) => {
    if (running.current) return;
    running.current = true;
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(plainError(e));
    } finally {
      running.current = false;
      setBusy(null);
    }
  }, []);
  return { busy, error, act };
}
