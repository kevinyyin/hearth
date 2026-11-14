export const API = process.env.NEXT_PUBLIC_API ?? "";

const KEY = "hearth-password";

/** The shared password for the hosted API, kept in this browser only. */
export const getPassword = (): string | null => (typeof localStorage === "undefined" ? null : localStorage.getItem(KEY));

export function setPassword(p: string | null): void {
  if (p) localStorage.setItem(KEY, p);
  else localStorage.removeItem(KEY);
}

export function authHeaders(): Record<string, string> {
  const p = getPassword();
  return API && p ? { Authorization: `Bearer ${p}` } : {};
}

/** A 401 forgets the stored password and tells the password screen to show itself. */
export function onUnauthorized(): never {
  setPassword(null);
  if (typeof window !== "undefined") window.dispatchEvent(new Event("hearth-auth"));
  throw new Error("password required");
}

/**
 * Fetches `${API}${path}`. With no API configured it reads the static dev files
 * under `public/dev/`, so every page works before the backend exists.
 */
export async function getJson<T>(path: string): Promise<T> {
  const url = API ? `${API}${path}` : `/dev${path}.json`;
  const res = await fetch(url, { cache: "no-store", headers: authHeaders() });
  if (res.status === 401) onUnauthorized();
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return (await res.json()) as T;
}
