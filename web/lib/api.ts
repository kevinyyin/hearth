export const API = process.env.NEXT_PUBLIC_API ?? "";

/**
 * Fetches `${API}${path}`. With no API configured it reads the static dev files
 * under `public/dev/`, so every page works before the backend exists.
 */
export async function getJson<T>(path: string): Promise<T> {
  const url = API ? `${API}${path}` : `/dev${path}.json`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return (await res.json()) as T;
}
