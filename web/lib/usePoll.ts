"use client";

import { useCallback, useEffect, useState } from "react";
import { getJson } from "./api";

/** Reads `path` now and every `ms` after. `refresh` reads again at once, after this page changed something. */
export function usePoll<T>(path: string | null, ms = 3000): { data: T | undefined; error: string | null; refresh: () => void } {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    if (!path) return;
    getJson<T>(path)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [path]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, ms);
    return () => clearInterval(timer);
  }, [refresh, ms]);
  return { data, error, refresh };
}
