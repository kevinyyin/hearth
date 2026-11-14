"use client";

import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { useEffect, useState } from "react";

// The browser phone: the same ElevenLabs agent as the phone line, whose model is our server.
// Every word the agent says is chosen by code from fixed templates; this page only connects and shows the transcript.
const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID ?? "";

type Line = { role: string; text: string };

function Phone() {
  const [callId, setCallId] = useState("");
  const [textOnly, setTextOnly] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const conversation = useConversation({
    onMessage: (m) => setLines((ls) => [...ls, { role: m.role, text: m.message }]),
    onError: (e) => setError(String(e)),
  });
  const live = conversation.status === "connected";

  useEffect(() => setCallId(new URLSearchParams(window.location.search).get("call_id") ?? ""), []);

  const start = () => {
    setError(null);
    setLines([]);
    conversation.startSession({
      agentId: AGENT_ID,
      customLlmExtraBody: { call_id: callId },
      ...(textOnly ? { textOnly: true } : {}),
    });
  };
  const send = (text: string) => {
    if (!text.trim()) return;
    setLines((ls) => [...ls, { role: "user", text }]);
    conversation.sendUserMessage(text);
    setDraft("");
  };

  return (
    <div className="mx-auto max-w-xl space-y-4 p-6">
      <header>
        <h1 className="text-xl font-semibold">Hearth browser phone</h1>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Simulated patient. The agent opens by saying it is automated; promises of help come only from fixed templates after a
          crew accepts.
        </p>
      </header>

      {!AGENT_ID && <p role="alert">Set NEXT_PUBLIC_ELEVENLABS_AGENT_ID (printed by python -m hearth.messaging.voice setup).</p>}

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-sm">
          Call id
          <input
            className="rounded border px-2 py-1 font-mono"
            style={{ borderColor: "var(--border)" }}
            value={callId}
            onChange={(e) => setCallId(e.target.value)}
            placeholder="C-…"
            disabled={live}
          />
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={textOnly} onChange={(e) => setTextOnly(e.target.checked)} disabled={live} />
          Text only (no microphone)
        </label>
        {live ? (
          <button className="rounded border px-3 py-1" style={{ borderColor: "var(--border)" }} onClick={() => conversation.endSession()}>
            Hang up
          </button>
        ) : (
          <button
            className="rounded border px-3 py-1"
            style={{ borderColor: "var(--border)" }}
            onClick={start}
            disabled={!AGENT_ID || !callId || conversation.status === "connecting"}
          >
            {conversation.status === "connecting" ? "Connecting…" : "Start call"}
          </button>
        )}
      </div>

      {error && <p role="alert">{error}</p>}

      <ol aria-label="Call transcript" aria-live="polite" className="space-y-2">
        {lines.map((l, i) => (
          <li key={i} className="rounded border p-2 text-sm" style={{ borderColor: "var(--border)" }}>
            <span className="font-medium">{l.role === "user" ? "Caller" : "Hearth"}: </span>
            {l.text}
          </li>
        ))}
      </ol>

      {live && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          {["1", "2", "3"].map((k) => (
            <button key={k} type="button" aria-label={`Keypad ${k}`} className="w-10 rounded border py-1" style={{ borderColor: "var(--border)" }} onClick={() => send(k)}>
              {k}
            </button>
          ))}
          <input
            className="min-w-0 flex-1 rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Type a reply"
            placeholder="Type a reply"
          />
          <button type="submit" className="rounded border px-3 py-1" style={{ borderColor: "var(--border)" }}>
            Send
          </button>
        </form>
      )}
    </div>
  );
}

export default function PhonePage() {
  return (
    <ConversationProvider>
      <Phone />
    </ConversationProvider>
  );
}
