"use client";

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useRef } from "react";
import { API_BASE_URL } from "@/lib/api-client";
import { parseSseEvent } from "@/lib/sse";
import { useAgentSessionStore } from "@/stores/agent-session-store";

interface ChatDenyBody {
  reason?: string;
}

/** The SINGLE SSE connection owner (frontend rules: state management). POSTs
 * a question to /api/chat, reads the X-AskRAG-* response headers, and
 * dispatches every parsed event into the session store. Components never
 * open a connection or parse a payload themselves — they call `ask` and read
 * store slices.
 *
 * Native EventSource can't POST a body or read response headers, hence
 * @microsoft/fetch-event-source (decisions.md 2026-07-08). */
export function useAgentStream() {
  const controllerRef = useRef<AbortController | null>(null);

  const ask = useCallback(async (question: string) => {
    controllerRef.current?.abort(); // at most one live turn per hook instance
    const controller = new AbortController();
    controllerRef.current = controller;

    const { sessionId, startTurn, setSessionId, setCapped, setReplay, applyEvent } =
      useAgentSessionStore.getState();
    startTurn(question);

    try {
      await fetchEventSource(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId ?? undefined }),
        signal: controller.signal,
        openWhenHidden: true, // a turn keeps running server-side; don't drop the connection on tab blur

        async onopen(response) {
          const newSessionId = response.headers.get("X-AskRAG-Session-Id");
          if (newSessionId) setSessionId(newSessionId);

          if (response.status === 429) {
            // Budget DENY: a plain JSON error, not a stream (routes_chat.py).
            const body: ChatDenyBody = await response.json().catch(() => ({}));
            setCapped(body.reason ?? "budget exceeded");
            throw new Error("askrag: budget denied");
          }

          if (response.headers.get("X-AskRAG-Mode") === "replay") {
            // Header values are percent-encoded (routes_chat.py: reasons
            // aren't ASCII-only, HTTP header values are Latin-1-only).
            const reasonHeader = response.headers.get("X-AskRAG-Reason");
            setReplay(reasonHeader ? decodeURIComponent(reasonHeader) : "");
          }

          if (!response.ok) {
            throw new Error(`askrag: chat request failed with ${response.status}`);
          }
        },

        onmessage(msg) {
          const event = parseSseEvent(msg.data);
          if (event) applyEvent(event);
        },

        onerror(err) {
          // Rethrow: this is a one-shot turn, not a long-lived reconnecting
          // subscription — fetch-event-source's default is to retry
          // indefinitely on error, which would silently re-POST the question.
          throw err;
        },
      });
    } catch {
      // Terminal state is USUALLY already reflected in the store (capped/
      // replay set inside onopen, or `done` already landed via applyEvent).
      // The exception is a genuine network failure mid-turn: no `done` event
      // is coming, so without this the store would stay stuck in
      // streaming/tool_running and the composer would stay disabled forever.
      const { status } = useAgentSessionStore.getState();
      if (status.kind === "streaming" || status.kind === "tool_running") {
        useAgentSessionStore.setState({ status: { kind: "idle" } });
      }
    }
  }, []);

  return { ask };
}
