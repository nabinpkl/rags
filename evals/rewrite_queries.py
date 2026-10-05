"""One model rewrite per golden question (D14, #18): `just rewrites`.

The agent's first move on a question is to restate it in the field's own
terms before it searches (feed-vs-agent dry run, 2026-10-05). This isolates
that move from the loop: one rewrite, no tools, no second search. The
retrieval runner scores hybrid search over the rewrite as its own row.

Rewrites are written to `rewrites.jsonl`, dataset-as-code beside the golden
set, so `just eval` stays free of model calls and repeatable. Each line
carries the question it rewrote; the runner refuses a file whose questions
no longer match the set.

The model is the one the live loop runs (`smoke_model`), since the row
measures that model's rewriting. Questions are not paper text, so nothing
here is fenced.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from askrag.config import get_settings
from pydantic import BaseModel, ConfigDict

from evals.draft_golden_set import OpenRouterClient
from evals.golden_set import GOLDEN_PATH, GoldenRecord, load_golden

REWRITES_PATH = Path(__file__).parent / "rewrites.jsonl"
# DeepSeek V4 Flash reasons before replying, and thinking spends max_tokens.
_REWRITE_TOKENS = 3000

REWRITE_SYSTEM = """You turn a researcher's query into the search query most \
likely to find the answer in arXiv computer science papers. Use the terms and \
names the field itself uses for the idea. Keep every specific name or term the \
query already contains. Reply with only the search query, at most 16 words."""


class Rewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    rewrite: str
    model: str
    seconds: float
    usd: float  # OpenRouter's billed cost for the call(s)


def load_rewrites(records: list[GoldenRecord], path: Path = REWRITES_PATH) -> dict[str, Rewrite]:
    """Rewrites keyed by record id. A missing record, or one whose question
    changed since it was rewritten, raises: scoring an old rewrite against a
    new question would report a query nobody asked."""
    rewrites = {
        r.id: r
        for r in (
            Rewrite.model_validate(json.loads(line))
            for line in path.read_text().splitlines()
            if line.strip()
        )
    }
    stale = [r.id for r in records if r.id not in rewrites or rewrites[r.id].question != r.question]
    if stale:
        raise ValueError(f"{len(stale)} questions lack a current rewrite; run `just rewrites`")
    return rewrites


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    settings = get_settings()
    records = load_golden(GOLDEN_PATH)
    client = OpenRouterClient.from_settings(settings)

    def rewrite(record: GoldenRecord) -> Rewrite:
        t0 = time.monotonic()
        usd = 0.0
        text = ""
        # One retry on an empty reply, as complete_nonempty does; both bill.
        for _ in range(2):
            text, cost = client.complete_priced(
                settings.smoke_model, REWRITE_SYSTEM, record.question, _REWRITE_TOKENS
            )
            if cost is None:
                raise ValueError(f"{record.id}: the rewrite reply carried no cost")
            usd += cost
            if text.strip():
                break
        text = " ".join(text.split()).strip("\"'")
        if not text:
            raise ValueError(f"{record.id}: empty rewrite")
        return Rewrite(
            id=record.id,
            question=record.question,
            rewrite=text,
            model=settings.smoke_model,
            seconds=time.monotonic() - t0,
            usd=usd,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rewrites = sorted(pool.map(rewrite, records), key=lambda r: r.id)
    REWRITES_PATH.write_text("".join(r.model_dump_json() + "\n" for r in rewrites))
    print(f"wrote {len(rewrites)} rewrites; tokens: {dict(client.usage)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
