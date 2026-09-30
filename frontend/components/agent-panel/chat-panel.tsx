"use client";

import { X } from "lucide-react";
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
}: {
  scope?: ChatScope;
  /** Unscoped, the agent reads the indexed set. Its size, when known, goes
   * in the boundary line so the reader sees how far the answers can reach. */
  paperCount?: number;
} = {}) {
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
    void ask(trimmed, scope?.foundationId);
  }

  return (
    <div className="bg-machine border-machine-line text-machine-text flex h-full min-h-0 flex-col lg:border-l">
      {/* 57px, the rail's and the canvas's header height, so the three
          columns' top rules meet as one line. */}
      <header className="border-machine-line flex h-[57px] shrink-0 items-center gap-2 border-b px-3.5">
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
            className="text-machine-muted hover:bg-machine-2 hover:text-machine-text flex size-11 items-center justify-center rounded transition-colors lg:hidden motion-reduce:transition-none"
          >
            <X className="size-5" aria-hidden />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3.5 py-3">
        {turns.length === 0 && (
          // The boundary line leads, at reading strength: it is what the
          // reader has to know before asking. The starters sit at the foot,
          // beside the composer they fill, not stranded at the top of an
          // empty column.
          <div className="flex flex-1 flex-col gap-3">
            <p className="text-machine-text text-sm leading-relaxed text-pretty">
              {scope
                ? `Answers come from ${scope.label} — I search and read those papers, and every step shows here with its cost.`
                : `I read ${paperCount === undefined ? "the papers listed here" : `these ${paperCount.toLocaleString()} papers`} and no others. I search, read, and compute, and every step shows here with its cost.`}
            </p>
            <ul className="mt-auto flex flex-col gap-1.5" aria-label="Example questions">
              {(scope?.starters ?? SUGGESTED_QUESTIONS).map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(example);
                      inputRef.current?.focus();
                    }}
                    className="border-machine-line bg-machine-2 text-machine-text hover:border-machine-accent hover:text-machine-accent w-full rounded border px-3 py-2 text-left text-[13px] leading-snug transition-colors motion-reduce:transition-none"
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
