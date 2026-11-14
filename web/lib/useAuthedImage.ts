"use client";

import { useEffect, useState } from "react";
import { API, authHeaders } from "./api";

/** An API image as an object URL. The API needs the password header, so the image is fetched rather than linked.
 *  Undefined while loading; null when there is no image (no path, no API, or the fetch failed). */
export function useAuthedImage(path: string | null): string | null | undefined {
  const [image, setImage] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (!path || !API) return setImage(null);
    setImage(undefined);
    let url: string | null = null;
    let cancelled = false;
    fetch(`${API}${path}`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (!cancelled) setImage(b ? (url = URL.createObjectURL(b)) : null);
      })
      .catch(() => {
        if (!cancelled) setImage(null);
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  return image;
}
