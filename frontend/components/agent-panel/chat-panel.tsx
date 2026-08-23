"use client";

import { useRef, useState, type FormEvent } from "react";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { cn } from "@/lib/utils";
import { ToolTimeline } from "@/components/agent-panel/tool-timeline";
import { CostBadge } from "@/components/agent-panel/cost-badge";
import { MessageMarkdown } from "@/components/agent-panel/message-markdown";
import { ReplayBanner } from "@/components/agent-panel/replay-banner";

// First-run starters. They FILL the composer rather than submit it: a turn
// costs real money against the D11 caps, and a stray tap on a suggestion
// should not spend it. Phrased for what the corpus actually holds (cs.CL
// is ~40% of it) so the first answer is a good one.
const SUGGESTED_QUESTIONS = [
  "What are the recurring themes across the cs.CL papers?",
  "Which papers propose new decoding methods, and how do they compare?",
  "Summarize recent work on multilingual instruction tuning",
] as const;

/** The machine-room agent panel: message list + timeline + composer, wired
 * to the single SSE connection owner (use-agent-stream.ts). Composition
 * only — parsing, event dispatch, and citation verification all live
 * upstream, in the hook and the store. */
export function ChatPanel() {
  const [question, setQuestion] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const status = useAgentSessionStore((state) => state.status);
  const mode = useAgentSessionStore((state) => state.mode);
  const turns = useAgentSessionStore((state) => state.turns);
  const verifiedPaperIds = useAgentSessionStore((state) => state.verifiedPaperIds);
  const closeOverlay = useUiShellStore((state) => state.closeOverlay);
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
    <div className="bg-machine border-machine-line text-machine-text flex h-full min-h-0 flex-col lg:border-l">
      <header className="border-machine-line flex items-center gap-2 border-b px-3.5 py-2.5">
        <span
          className={cn("h-2 w-2 rounded-full", mode.kind === "replay" ? "bg-amber" : "bg-teal")}
        />
        <h2 className="font-mono text-[11px] tracking-wide uppercase">agent</h2>
        <div className="ml-auto flex items-center gap-1">
          <CostBadge cost={lastTurn?.cost ?? null} />
          {/* `lg:hidden`, so the docked column has no dead tab stop. */}
          <button
            type="button"
            onClick={closeOverlay}
            aria-label="Close agent panel"
            className="text-machine-muted hover:text-machine-text flex h-9 w-9 items-center justify-center text-lg lg:hidden"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-3.5 py-3">
        {turns.length === 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-machine-muted text-sm">
              Ask about the corpus — I search, read, and compute; every step shows here with its
              cost.
            </p>
            <ul className="flex flex-col gap-1.5" aria-label="Example questions">
              {SUGGESTED_QUESTIONS.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(example);
                      inputRef.current?.focus();
                    }}
                    className="border-machine-line bg-machine-2 text-machine-text hover:border-teal hover:text-teal w-full rounded border px-3 py-2 text-left text-[13px]"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
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

      <form
        onSubmit={handleSubmit}
        // The sheet reaches the bottom edge of the screen, so the composer
        // pads past the iOS home indicator; docked, the footer already sits
        // below it and the inset is 0 anyway.
        className="border-machine-line flex gap-2 border-t p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:pb-3"
      >
        <input
          ref={inputRef}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={busy}
          aria-label="Question for the agent"
          placeholder="Ask about the corpus…"
          className="bg-machine-2 border-machine-line text-machine-text min-w-0 flex-1 rounded border px-2.5 py-2.5 text-[16px] lg:py-2 lg:text-sm"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length === 0}
          className="bg-teal-deep hover:bg-teal-deep-hover shrink-0 rounded px-4 py-2.5 text-sm font-semibold text-[#eafaf6] disabled:opacity-50 disabled:hover:bg-teal-deep lg:py-2"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
