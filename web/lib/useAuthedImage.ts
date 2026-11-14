"use client";

import { useEffect, useState } from "react";
import { API, authHeaders } from "./api";

/** An API image as an object URL. The API needs the password header, so the image is fetched rather than linked.
 *  Null while loading, on failure, or with no API configured. */
export function useAuthedImage(path: string | null): string | null {
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    setImage(null);
    if (!path || !API) return;
    let url: string | null = null;
    let cancelled = false;
    fetch(`${API}${path}`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (b && !cancelled) setImage((url = URL.createObjectURL(b)));
      })
      .catch(() => setImage(null));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  return image;
}
