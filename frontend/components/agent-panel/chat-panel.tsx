"use client";

import { useState, type FormEvent } from "react";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { cn } from "@/lib/utils";
import { ToolTimeline } from "@/components/agent-panel/tool-timeline";
import { CostBadge } from "@/components/agent-panel/cost-badge";
import { MessageMarkdown } from "@/components/agent-panel/message-markdown";
import { ReplayBanner } from "@/components/agent-panel/replay-banner";

/** The machine-room agent panel: message list + timeline + composer, wired
 * to the single SSE connection owner (use-agent-stream.ts). Composition
 * only — parsing, event dispatch, and citation verification all live
 * upstream, in the hook and the store. */
export function ChatPanel() {
  const [question, setQuestion] = useState("");
  const status = useAgentSessionStore((state) => state.status);
  const mode = useAgentSessionStore((state) => state.mode);
  const turns = useAgentSessionStore((state) => state.turns);
  const verifiedPaperIds = useAgentSessionStore((state) => state.verifiedPaperIds);
  const { ask } = useAgentStream();

  const busy = status.kind === "streaming" || status.kind === "tool_running";
  const lastTurn = turns.length > 0 ? turns[turns.length - 1] : undefined;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setQuestion("");
    void ask(trimmed);
  }

  return (
    <div className="bg-machine border-machine-line text-machine-text flex h-full flex-col border-l">
      <header className="border-machine-line flex items-center gap-2 border-b px-3.5 py-2.5">
        <span
          className={cn("h-2 w-2 rounded-full", mode.kind === "replay" ? "bg-amber" : "bg-teal")}
        />
        <h2 className="font-mono text-[11px] tracking-wide uppercase">agent</h2>
        <div className="ml-auto">
          <CostBadge cost={lastTurn?.cost ?? null} />
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-3.5 py-3">
        {turns.length === 0 && (
          <p className="text-machine-muted text-sm">
            Ask about the corpus — I search, read, and compute; every step shows here with its cost.
          </p>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col gap-2">
            <div className="bg-machine-2 border-machine-line self-end rounded-lg rounded-br-sm border px-3 py-2 text-[13px]">
              {turn.question}
            </div>
            <ToolTimeline entries={turn.timeline} />
            {turn.answer.length > 0 && (
              <MessageMarkdown text={turn.answer} verifiedPaperIds={verifiedPaperIds} />
            )}
            {status.kind === "tool_running" && turn === lastTurn && (
              <p className="text-machine-muted font-mono text-[11px]">running {status.name}…</p>
            )}
          </div>
        ))}
      </div>

      <ReplayBanner mode={mode} status={status} />

      <form onSubmit={handleSubmit} className="border-machine-line flex gap-2 border-t p-3">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={busy}
          placeholder="Ask about the corpus…"
          className="bg-machine-2 border-machine-line text-machine-text flex-1 rounded border px-2.5 py-2 text-sm outline-none"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length === 0}
          className="bg-teal-deep rounded px-3.5 py-2 text-sm font-semibold text-[#eafaf6] disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
