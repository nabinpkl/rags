"""The terminal REPL (#24) — the ONE terminal entrypoint for the agent loop,
milestone 3's exit artifact. No question arg -> interactive multi-turn REPL;
one question arg -> a single one-shot turn. Replaces `askrag.agent.loop`'s
former `main`/`_print_event` (DECISIONS.md 2026-07-07: one CLI, one way) —
`just repl` and `just smoke-agent` both point here now.

Cheap-first (owner directive 2026-07-06, DECISIONS.md): set
`ASKRAG_AGENT_API_BASE_URL` + `OPENROUTER_API_KEY` to route through
`smoke_model` via OpenRouter; leave both unset to hit real Anthropic/Haiku
(D3) directly.
"""

import argparse
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from askrag import db, telemetry
from askrag.agent.loop import (
    AgentEvent,
    ModelClient,
    TurnResult,
    anthropic_client_from_settings,
    run_turn,
)
from askrag.api import sse_events
from askrag.config import Settings, get_settings

# New-style arXiv ids only (corpus.db's papers.arxiv_id, D9) — YYMM.NNNNN,
# optionally version-suffixed in the answer text even though the stored id
# itself never carries the version.
_ARXIV_ID_RE = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")


def _cited_ids(text: str) -> set[str]:
    return set(_ARXIV_ID_RE.findall(text))


def _verify_citations(text: str, *, settings: Settings) -> None:
    """Terminal analogue of §6's server-side citation verification (the full
    per-answer gate is #30): looks every cited arXiv id up read-only in
    corpus.db, flagging any that doesn't resolve — proof the answer's
    citations are grounded, not hallucinated."""
    ids = _cited_ids(text)
    if not ids:
        return
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        for paper_id in sorted(ids):
            row = conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (paper_id,)).fetchone()
            status = "verified" if row is not None else "NOT FOUND IN CORPUS.DB"
            print(f"  [citation] {paper_id}: {status}", file=sys.stderr)
    finally:
        conn.close()


def _print_timeline_event(event: AgentEvent) -> None:
    """The visible tool-call timeline (acceptance: "visible tool timeline"),
    rendered through `sse_events.translate()` so the terminal and the future
    SSE stream describe the same shapes (#24 defines them; #30 wires HTTP)."""
    sse = sse_events.translate(event)
    if isinstance(sse, sse_events.ToolCallEvent):
        print(f"  -> {sse.name}({sse.args})", file=sys.stderr)
    elif isinstance(sse, sse_events.ToolResultSummaryEvent):
        status = "ok" if sse.ok else f"error: {sse.error}"
        print(f"     {status}", file=sys.stderr)
    elif isinstance(sse, sse_events.UiActionEvent):
        print(f"  -> ui:{sse.action}({sse.args})", file=sys.stderr)
    # thinking/text/done: text is printed once from the final TurnResult
    # below (the TEXT AgentEvent carries the same string, D2), done's
    # stop_reason/run_id are printed from TurnResult too — no double-print.


@dataclass
class ReplSession:
    """One REPL run's accumulated state: the running message history (D2's
    `messages` thread between turns) and the running session cost
    (acceptance: "running session cost")."""

    client: ModelClient
    settings: Settings
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    messages: list[Any] = field(default_factory=list)
    total_cost_usd: float = 0.0

    def ask(self, question: str) -> TurnResult:
        result = run_turn(
            self.messages,
            question,
            session_id=self.session_id,
            ip="127.0.0.1",
            client=self.client,
            settings=self.settings,
            on_event=_print_timeline_event,
        )
        self.messages = result.messages
        self.total_cost_usd += result.cost_usd

        print(f"\n{result.text}\n")
        _verify_citations(result.text, settings=self.settings)
        print(
            f"[{result.stop_reason.value}, {len(result.tool_calls)} tool call(s), "
            f"{result.tokens_in}+{result.tokens_out} tokens this turn, "
            f"${result.cost_usd:.4f} this turn, ${self.total_cost_usd:.4f} session total]",
            file=sys.stderr,
        )
        return result


def _interactive(session: ReplSession) -> None:
    print("askRAG terminal REPL. Ask a question; 'quit' or Ctrl-D to exit.", file=sys.stderr)
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            print(file=sys.stderr)
            return
        if not question or question in {"quit", "exit"}:
            return
        session.ask(question)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="ask one question and exit; omit for the interactive REPL",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    telemetry.init(settings)
    try:
        session = ReplSession(client=anthropic_client_from_settings(settings), settings=settings)
        if args.question is not None:
            session.ask(args.question)
        else:
            _interactive(session)
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
