"use client";

import { CornerDownRight, Loader2, Sparkles, X } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { cn } from "@/lib/utils";
import { ToolTimeline } from "@/components/agent-panel/tool-timeline";
import { CostBadge } from "@/components/agent-panel/cost-badge";
import { MessageMarkdown } from "@/components/agent-panel/message-markdown";
import { ReplayBanner } from "@/components/agent-panel/replay-banner";

// First-run starters. They FILL the composer rather than submit it: a turn
// costs real money against the D11 caps, and a stray tap on a suggestion
// should not spend it. Phrased for what the corpus actually holds (cs.CL
// is ~40% of it) so the first answer is a good one, and in words rather than
// arXiv codes, since a starter is read before the reader knows the codes.
const SUGGESTED_QUESTIONS = [
  "What are the recurring themes across the natural language processing papers?",
  "Which papers propose new decoding methods, and how do they compare?",
  "Summarize recent work on multilingual instruction tuning",
] as const;

export interface ChatScope {
  /** The landing-page claim this conversation is about. Sent to the server,
   * which resolves it to that claim's indexed papers; the client never names
   * a paper set (routes_chat._resolve_scope). */
  foundationId: string;
  /** What the scope is, in the reader's words — shown above the composer so
   * the answer's boundaries are visible before the question is asked. */
  label: string;
  starters: readonly string[];
}

/** The machine-room agent panel: message list + timeline + composer, wired
 * to the single SSE connection owner (use-agent-stream.ts). Composition
 * only — parsing, event dispatch, and citation verification all live
 * upstream, in the hook and the store.
 *
 * `scope` makes this the landing page's ask surface too, rather than a second
 * chat implementation: same store, same SSE path, same timeline — only the
 * starters and the server-side paper scope differ. */
export function ChatPanel({
  scope,
  paperCount,
  onClose,
}: {
  scope?: ChatScope;
  /** Unscoped, the agent reads the indexed set. Its size, when known, goes
   * in the boundary line so the reader sees how far the answers can reach. */
  paperCount?: number;
  /** Where the panel can be put away (the RAG demo). Omitted where it is
   * part of the page, like the landing page's ask surface, and then there is
   * no close control to press. */
  onClose?: () => void;
} = {}) {
  const [question, setQuestion] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const startersLabelId = useId();
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
    void ask(trimmed, scope?.foundationId);
  }

  return (
    <div className="bg-machine border-machine-line text-machine-text flex h-full min-h-0 flex-col lg:border-l">
      {/* 57px, the rail's and the canvas's header height, so the three
          columns' top rules meet as one line. */}
      {/* Sized like the rail's brand head (a 26px tile and a 15-17px name),
          so the two columns' heads read as the same kind of object. The tile
          turns amber in replay, the state the old status dot carried. */}
      <header className="border-machine-line flex h-[57px] shrink-0 items-center gap-2.5 border-b px-4">
        <span
          className={cn(
            "text-teal-deep-label grid size-[26px] shrink-0 place-items-center rounded-[6px]",
            mode.kind === "replay" ? "bg-amber" : "bg-teal-deep",
          )}
          aria-hidden
        >
          <Sparkles className="size-3.5" />
        </span>
        <h2 className="text-machine-text text-[15px] font-semibold">Agent</h2>
        <div className="ml-auto flex items-center gap-1">
          <CostBadge cost={lastTurn?.cost ?? null} />
          {/* 44px for touch, 36px where a pointer aims at it. */}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close agent panel"
              className="text-machine-muted hover:bg-machine-2 hover:text-machine-text flex size-11 items-center justify-center rounded transition-colors motion-reduce:transition-none lg:size-9"
            >
              <X className="size-5 lg:size-4" aria-hidden />
            </button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-8 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          // One composed block, centred in the column so the panel has no
          // dead middle: what the agent is, how far it reaches, and what to
          // try. The starters are plain rows rather than boxed buttons, so
          // the block reads as one object and not as a stack of cards.
          <div className="my-auto flex flex-col py-6">
            <span
              className="bg-machine-2 border-machine-line text-machine-text grid size-14 place-items-center rounded-2xl border"
              aria-hidden
            >
              <Sparkles className="size-6" />
            </span>
            <p className="text-machine-text mt-5 text-[22px] leading-tight font-semibold text-balance">
              Ask about these papers
            </p>
            <p className="text-machine-muted mt-2 text-[14px] leading-relaxed text-pretty">
              {scope
                ? `Answers come from ${scope.label}, and every step shows here with its cost.`
                : `I read ${paperCount === undefined ? "the papers listed here" : `these ${paperCount.toLocaleString()} papers`} and no others. Every search and read shows here with its cost.`}
            </p>
            <p id={startersLabelId} className="text-machine-muted mt-7 text-[13px] font-medium">
              Try asking
            </p>
            <ul className="mt-1.5 flex flex-col" aria-labelledby={startersLabelId}>
              {(scope?.starters ?? SUGGESTED_QUESTIONS).map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(example);
                      inputRef.current?.focus();
                    }}
                    className="group text-machine-text hover:bg-machine-2 -mx-2 flex w-[calc(100%+1rem)] items-start gap-3 rounded px-2 py-2 text-left text-[14px] leading-snug transition-colors motion-reduce:transition-none"
                  >
                    <CornerDownRight
                      className="text-machine-muted group-hover:text-machine-accent mt-0.5 size-4 shrink-0"
                      aria-hidden
                    />
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {turns.map((turn) => {
          // A step that is still out shows its own spinner in the timeline.
          // Between steps, and before the first answer word, nothing on
          // screen would move, so the turn says it is thinking.
          const thinking =
            busy &&
            turn === lastTurn &&
            turn.answer.length === 0 &&
            !turn.timeline.some((entry) => entry.result === null);
          return (
            <div key={turn.id} className="flex flex-col gap-4">
              <p className="bg-machine-2 max-w-[85%] self-end rounded-2xl rounded-br-md px-3.5 py-2.5 text-[14px] leading-relaxed text-pretty">
                {turn.question}
              </p>
              {/* The agent's side of the turn, marked with the header's tile
                  so who is speaking needs no label. */}
              <div className="flex items-start gap-3">
                <span
                  className="bg-machine-2 border-machine-line text-machine-text mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg border"
                  aria-hidden
                >
                  <Sparkles className="size-3.5" />
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <ToolTimeline entries={turn.timeline} />
                  {thinking && (
                    <p className="text-machine-muted flex items-center gap-2 text-[13px]">
                      <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden />
                      Thinking
                    </p>
                  )}
                  {turn.answer.length > 0 && (
                    <MessageMarkdown text={turn.answer} verifiedPaperIds={verifiedPaperIds} />
                  )}
                </div>
              </div>
            </div>
          );
        })}
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
          placeholder="Ask about these papers…"
          className="bg-machine-2 border-machine-line text-machine-text placeholder:text-machine-muted min-w-0 flex-1 rounded border px-2.5 py-2.5 text-[16px] disabled:opacity-60 lg:py-2 lg:text-sm"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length === 0}
          className="bg-teal-deep hover:bg-teal-deep-hover shrink-0 rounded px-4 py-2.5 text-sm font-semibold text-teal-deep-label disabled:opacity-50 disabled:hover:bg-teal-deep lg:py-2"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
