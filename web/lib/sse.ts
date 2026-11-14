import { API, authHeaders, onUnauthorized } from "./api";
import type { BuildingProfile, TraceEvent } from "./types";

export type Todo = { content: string; status: string };
export type SubagentRow = { name: string; task: string; last: string; asks: number; steps: number };

export type TraceView = {
  todos: Todo[];
  subagents: SubagentRow[];
  files: string[];
  conflicts: string[];
  profile: BuildingProfile | null;
  error: string | null;
  proposalId: string | null;
  done: boolean;
  /** The run's closing line, e.g. "no eligible refuge found"; shown even when there is no error. */
  message: string | null;
};

/** Folds a survey or refuge event stream into what the panel shows. Later events win. */
export function reduceTrace(events: TraceEvent[]): TraceView {
  const view: TraceView = { todos: [], subagents: [], files: [], conflicts: [], profile: null, error: null, proposalId: null, done: false, message: null };
  const row = (name: string) => view.subagents.find((s) => s.name === name);
  for (const e of events) {
    switch (e.kind) {
      case "todo":
        view.todos = (e.data.todos as Todo[]) ?? [];
        break;
      case "subagent": {
        const r = row(e.agent);
        if (r) r.asks += 1;
        else view.subagents.push({ name: e.agent, task: e.text, last: "", asks: 1, steps: 0 });
        break;
      }
      case "tool": {
        const r = row(e.agent);
        if (r) {
          r.last = e.text;
          r.steps += 1;
        }
        break;
      }
      case "file":
        if (!view.files.includes(e.text)) view.files.push(e.text);
        break;
      case "conflict":
        view.conflicts.push(e.text);
        break;
      case "interrupt":
        view.proposalId = (e.data.proposal_id as string) ?? null;
        break;
      case "done": {
        view.done = true;
        view.message = e.text;
        view.profile = (e.data.profile as BuildingProfile) ?? null;
        view.error = (e.data.error as string) ?? view.profile?.error ?? null;
        break;
      }
    }
  }
  return view;
}

/** Splits a server-sent-events buffer into complete `data:` payloads and the unfinished tail. */
export function parseSSE(buffer: string): { events: unknown[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events = parts.flatMap((part) =>
    part.split("\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)) as unknown),
  );
  return { events, rest };
}

/** Streams events from the API (GET or POST; EventSource cannot POST). Resolves when the stream ends. */
export async function streamEvents(path: string, init: RequestInit | undefined, onEvent: (e: TraceEvent) => void): Promise<void> {
  if (!API) throw new Error("Set NEXT_PUBLIC_API to the Hearth API to run the agent live.");
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...authHeaders(), ...(init?.headers as Record<string, string>) } });
  if (res.status === 401) onUnauthorized();
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSSE(buffer + decoder.decode(value, { stream: true }));
    buffer = parsed.rest;
    parsed.events.forEach((e) => onEvent(e as TraceEvent));
  }
}
