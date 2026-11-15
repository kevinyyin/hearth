import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const store: Record<string, string> = {};
beforeEach(() => {
  vi.resetModules();
  process.env.NEXT_PUBLIC_API = "https://api.example";
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_API;
  for (const k of Object.keys(store)) delete store[k];
});

describe("getJson against the hosted API", () => {
  it("sends the stored password as a bearer token", async () => {
    const fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setPassword("open sesame");
    await api.getJson("/api/runs");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer open sesame");
  });

  it("forgets a rejected password", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));
    vi.stubGlobal("window", { dispatchEvent: () => true });
    const api = await import("./api");
    api.setPassword("wrong");
    await expect(api.getJson("/api/runs")).rejects.toThrow("password");
    expect(api.getPassword()).toBeNull();
  });

  it("says what failed when the API answers with an error", async () => {
    const body = JSON.stringify({ detail: "an upstream service answered 503" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 502, statusText: "Bad Gateway" })));
    const api = await import("./api");
    await expect(api.getJson("/api/runs")).rejects.toThrow("502 an upstream service answered 503");
  });
});
