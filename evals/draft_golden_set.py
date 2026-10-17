"""Draft and check the golden set (D14, amended 2026-09-30): `just golden`.

For each sampled source (sample_sources.py) the drafter writes one question,
its answer, and the verbatim span that supports it. Then the record is
checked with no human in the loop:

1. Deterministic: the span sits inside its chunk, it is at most
   quote_max_words, the lexical rule for its type holds, and the question
   is at most golden_question_max_words (a search query, not a prompt).
2. Closed-book: the checker answers the question with NO passage.
3. Grading: the checker, given the passage, says whether the passage alone
   answers the question, whether the drafted answer is right, whether its
   own closed-book answer was, whether a researcher would type it, and
   whether the expected answer would be wrong for the query as typed.

Every record is written, culled or not, with its checks, so the file shows
what the checks removed; `GoldenRecord.counts()` decides membership. Each
checked record is also checkpointed (draft_progress.py), so a killed run
resumes where it stopped.

Chunk text is untrusted paper content (§6): it is fenced in every prompt and
the models are told it is data. Model output is parsed as JSON and validated;
an unparseable reply culls that candidate and is counted, never dropped.
"""

import argparse
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import anthropic
from askrag import db
from askrag.config import Settings, get_settings

from evals.draft_progress import ProgressLog, load_progress, signature
from evals.draft_prompts import DraftPrompts
from evals.eval_sources import EVAL_SOURCES, EvalSource
from evals.golden_set import (
    Difficulty,
    DraftedRecord,
    GoldenChecks,
    GoldenType,
    dump_golden,
    load_drafted,
)
from evals.model_client import ModelClient
from evals.sample_sources import (
    Source,
    document_frequency,
    load_chunks,
    sample_sources,
    words,
)

# Both golden models reason before replying, and thinking spends max_tokens:
# at 20 tokens both returned an empty text block (probed 2026-09-30), and at
# 6,000 the drafter still ended on thinking alone in 22 of 109 drafts. At
# 3,000 the checker came back empty or cut mid-JSON on 9 of 219 (2026-10-05).
_DRAFT_TOKENS = 12000
_CHECK_TOKENS = 6000
_MARKUP = re.compile(r"[*_#`>|]+")


def parse_json(reply: str) -> dict:
    """The first {...} object in a reply; models wrap JSON in prose or fences."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object in reply: {reply[:120]!r}")
    return json.loads(reply[start : end + 1])


def normalize(text: str) -> str:
    """Markdown markup and whitespace removed, lowercased: extraction puts
    ** and _ around words, and a model copying a span drops them."""
    return " ".join(_MARKUP.sub(" ", text).split()).lower()


def fenced(source: Source, prompts: DraftPrompts) -> str:
    parts = []
    for i, chunk in enumerate(source.chunks, start=1):
        label = f" {i}" if len(source.chunks) > 1 else ""
        parts.append(
            f"Excerpt{label} (section: {chunk.section}):\n"
            f"<{prompts.fence}>\n{chunk.text}\n</{prompts.fence}>"
        )
    return "\n\n".join(parts)


def draft_prompt(source: Source, prompts: DraftPrompts) -> str:
    brief = prompts.type_briefs[source.type].format(anchor=source.anchor_term)
    banned = ", ".join(sorted(source.rare_terms)) or "(none)"
    return f"{fenced(source, prompts)}\n\n{brief}\nBanned terms: {banned}"


def lexical_rule(question: str, source: Source) -> bool:
    if source.type is GoldenType.EXACT_MATCH:
        return source.anchor_term is not None and source.anchor_term.lower() in question.lower()
    return not (words(question) & source.rare_terms)


def spans_verbatim(spans: list[str], source: Source) -> bool:
    """Every span inside a chunk, and for multi_hop one span per chunk.

    A span elided with an ellipsis despite the prompt is checked piece by
    piece: each piece must still be verbatim."""
    texts = [normalize(c.text) for c in source.chunks]
    spans = [piece for s in spans for piece in re.split(r"…|\.\.\.", s) if normalize(piece)]
    if not spans:
        return False
    if not all(any(normalize(s) in t for t in texts) for s in spans):
        return False
    return all(any(normalize(s) in t for s in spans) for t in texts)


def record_id(source: Source) -> str:
    return f"{source.type.value}-{source.chunks[0].chunk_id}"


def run_signature(settings: Settings, ev: EvalSource) -> str:
    """Everything besides the source that shapes a record: a checkpoint from
    a run that differs in any of these is not reused."""
    return signature(
        [
            ev.draft_model(settings),
            ev.check_model(settings),
            ev.prompts.draft_system,
            ev.prompts.closed_book_system,
            ev.prompts.grade_system,
            json.dumps({t.value: b for t, b in ev.prompts.type_briefs.items()}),
            _DRAFT_TOKENS,
            _CHECK_TOKENS,
            settings.golden_question_max_words,
            settings.quote_max_words,
            settings.golden_rare_term_max_df,
            settings.golden_mismatch_max_shared_df,
        ]
    )


def check_record(
    source: Source, draft: dict, client: ModelClient, settings: Settings, ev: EvalSource
) -> DraftedRecord:
    check_model = ev.check_model(settings)
    spans = [str(s) for s in draft["spans"]]
    question, answer = str(draft["question"]), str(draft["answer"])
    closed_book = client.complete_nonempty(
        check_model, ev.prompts.closed_book_system, question, _CHECK_TOKENS
    )
    grade = parse_json(
        client.complete_nonempty(
            check_model,
            ev.prompts.grade_system,
            f"{fenced(source, ev.prompts)}\n\nQuestion: {question}\nProposed answer: {answer}\n"
            f"Closed-book answer: {closed_book}",
            _CHECK_TOKENS,
        )
    )
    first = source.chunks[0]
    return DraftedRecord(
        id=record_id(source),
        question=question,
        type=source.type,
        expected_paper_id=first.doc_id,
        expected_chunk_ids=[c.chunk_id for c in source.chunks],
        expected_passage=" … ".join(spans),
        expected_answer=answer,
        difficulty=Difficulty(draft["difficulty"]),
        anchor_term=source.anchor_term,
        draft_model=ev.draft_model(settings),
        checks=GoldenChecks(
            passage_verbatim=spans_verbatim(spans, source),
            passage_within_cap=all(len(s.split()) <= settings.quote_max_words for s in spans),
            lexical_rule=lexical_rule(question, source),
            question_within_cap=len(question.split()) <= settings.golden_question_max_words,
            grounded=bool(grade["grounded"]),
            substantive=bool(grade["substantive"]),
            answer_correct=bool(grade["answer_correct"]),
            closed_book_correct=bool(grade["closed_book_correct"]),
            natural=bool(grade["natural"]),
            unambiguous=bool(grade["unambiguous"]),
            check_model=check_model,
            note=str(grade.get("note", "")),
        ),
    )


def draft_one(
    source: Source, client: ModelClient, settings: Settings, ev: EvalSource
) -> DraftedRecord:
    system = ev.prompts.draft_system.replace("{max_words}", str(settings.quote_max_words)).replace(
        "{max_question_words}", str(settings.golden_question_max_words)
    )
    draft = parse_json(
        client.complete_nonempty(
            ev.draft_model(settings), system, draft_prompt(source, ev.prompts), _DRAFT_TOKENS
        )
    )
    return check_record(source, draft, client, settings, ev)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--source", choices=sorted(EVAL_SOURCES), default="arxiv")
    parser.add_argument("--limit", type=int, default=None, help="draft only the first N sources")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--types",
        nargs="+",
        type=GoldenType,
        default=None,
        help="redraft only these types; the file keeps every other type's records",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    ev = EVAL_SOURCES[args.source]
    progress_path = ev.progress_path(settings)
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    conn = db.connect_corpus(ev.spec.index(settings).db_path)
    try:
        chunks = load_chunks(conn, settings.golden_min_chunk_tokens, ev.spec.stratum_facet)
        df = document_frequency(conn)
    finally:
        conn.close()
    sources = sample_sources(
        chunks,
        df,
        ev.quota(settings),
        seed=settings.golden_seed,
        rare_max_df=settings.golden_rare_term_max_df,
        mismatch_max_df=settings.golden_mismatch_max_shared_df,
        multi_hop_min_shared=settings.golden_multi_hop_min_shared_terms,
        per_doc=ev.per_doc(settings),
    )
    if args.types:
        sources = [s for s in sources if s.type in args.types]
    sources = sources[: args.limit]
    sig = run_signature(settings, ev)
    # A checkpoint resumes only for the same source: same id AND the same
    # chunks, since a multi_hop id names its first chunk only.
    checkpoint = load_progress(sig, progress_path)
    resumed = [
        checkpoint[record_id(s)]
        for s in sources
        if record_id(s) in checkpoint
        and checkpoint[record_id(s)].expected_chunk_ids == [c.chunk_id for c in s.chunks]
    ]
    done_ids = {r.id for r in resumed}
    sources = [s for s in sources if record_id(s) not in done_ids]
    print(
        f"drafting {len(sources)} sources, {len(resumed)} resumed from {progress_path.name}",
        file=sys.stderr,
    )

    client = ev.client(settings)
    progress = ProgressLog(sig, progress_path)
    failures: list[str] = []
    done = Counter[str]()

    def attempt(source: Source) -> DraftedRecord | None:
        try:
            record = draft_one(source, client, settings, ev)
            progress.append(record)
            return record
        except (ValueError, KeyError, TypeError, anthropic.APIError) as exc:
            failures.append(f"{source.chunks[0].chunk_id}: {exc}")
            return None
        finally:
            done["n"] += 1
            print(f"  {done['n']}/{len(sources)}", file=sys.stderr, flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = resumed + [r for r in pool.map(attempt, sources) if r is not None]
    if args.types:
        kept_others = [
            r for r in load_drafted(ev.drafted_path(settings)) if r.type not in args.types
        ]
        records = kept_others + records
    records.sort(key=lambda r: r.id)
    dump_golden(records, ev.drafted_path(settings), ev.golden_path(settings))
    # Failed drafts are not checkpointed, so keeping the file lets a rerun
    # retry only them; a run with none has nothing left to resume.
    if not failures:
        progress_path.unlink(missing_ok=True)

    kept = [r for r in records if r.counts()]
    by_type = Counter(r.type.value for r in kept)
    print(f"wrote {len(records)} records, {len(kept)} count: {dict(sorted(by_type.items()))}")
    culled = Counter(
        name
        for r in records
        if not r.counts()
        for name, failed in (
            ("passage_verbatim", not r.checks.passage_verbatim),
            ("passage_within_cap", not r.checks.passage_within_cap),
            ("lexical_rule", not r.checks.lexical_rule),
            ("question_within_cap", not r.checks.question_within_cap),
            ("grounded", not r.checks.grounded),
            ("substantive", not r.checks.substantive),
            ("answer_correct", not r.checks.answer_correct),
            ("closed_book_correct", r.checks.closed_book_correct),
            ("natural", not r.checks.natural),
            ("unambiguous", not r.checks.unambiguous),
        )
        if failed
    )
    print(f"cull reasons (a record can fail several): {dict(culled)}")
    print(f"unparseable or failed drafts: {len(failures)}")
    if failures:
        print(f"kept {progress_path.name}: rerun to retry only the failed drafts")
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    print(f"tokens: {dict(client.usage)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
