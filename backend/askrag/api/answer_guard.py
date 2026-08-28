"""The answer output boundary: §6c row 4 and citation verification (issue #36).

Two rules, one boundary — everything a user is shown as an ANSWER passes
through `harden()`:

1. **Citations are verified.** An arXiv id in the answer survives only if this
   turn actually retrieved that paper. Retrieved paper text is untrusted (§6,
   injection surface): a chunk can tell the model to cite a paper that does not
   support the claim, and a model that obeys produces a real-looking id nothing
   ever fetched. Frontend link-gating already exists but is UX, not security —
   an API client sees the raw text.

2. **Verbatim quotes are capped** at `quote_max_words` per quote and
   `max_quotes_per_paper` per paper per answer.

Row 4 is enforced HERE and not at `read_paper`. The 2026-07-06 clarification
(DECISIONS.md, issue #58) makes those two separate enforcement points: row 1 is
the MODEL's deep read, page-bounded by `read_paper_max_tokens`, and applying
row 4's caps there would break a real deep read. Row 4 governs what a USER is
shown. Nothing in this module is reachable from the model-facing tool path.

Detection is verbatim-overlap, not quotation marks. Quotation marks are a model
behavior, and the case that matters most — an injected instruction to dump a
section — is exactly the case where the model has been told not to mark it.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from askrag.config import Settings
from askrag.traces import ToolCallRecord

_logger = logging.getLogger(__name__)

# arXiv ids as they appear in generated prose: bare, `arXiv:`-prefixed, or in a
# link, optionally version-suffixed. Old-style ids (hep-th/9901001) are out of
# scope for the same reason extract_citations.py excludes them: the corpus is
# new-style only, so an old-style id can never be one this turn retrieved.
_ID_IN_TEXT = re.compile(r"(?<![\w.])(\d{4}\.\d{4,5})(v\d+)?(?![\d])")
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class HardenedAnswer:
    """What actually left, plus what was removed so it can be logged."""

    text: str
    stripped_ids: tuple[str, ...] = ()
    capped_quotes: int = 0
    dropped_quotes: int = 0
    _spans: tuple[Any, ...] = field(default=(), repr=False)

    @property
    def changed(self) -> bool:
        return bool(self.stripped_ids) or bool(self.capped_quotes) or bool(self.dropped_quotes)


def retrieved_paper_ids(tool_calls: Sequence[ToolCallRecord]) -> frozenset[str]:
    """Papers this turn actually retrieved — the citation allow-list.

    Successful `search_corpus` results contribute their citations' paper ids;
    successful `read_paper` calls contribute the paper they read (it produces
    no Citations of its own — known gap, issue #27). A FAILED call contributes
    nothing: otherwise merely asking for a paper would authorize citing it.
    """
    allowed: set[str] = set()
    for call in tool_calls:
        if not call.ok:
            continue
        allowed.update(citation.paper_id for citation in call.citations)
        if call.name == "read_paper":
            paper_id = call.args.get("paper_id")
            if isinstance(paper_id, str) and paper_id:
                allowed.add(paper_id)
    return frozenset(allowed)


def fetch_sources(
    conn: sqlite3.Connection, tool_calls: Sequence[ToolCallRecord]
) -> dict[str, list[str]]:
    """The text this turn let the model see, per paper — `harden`'s `sources`.

    Kept beside `harden` rather than inside it so `harden` stays pure and is
    testable without a corpus; kept out of the route so the query lives once.

    For a `read_paper` call this returns EVERY chunk of that paper, not just
    the pages read. That is deliberately a superset: it costs one extra query
    and closes the hole where a model reads pages 1-5, then quotes page 9 from
    an earlier turn's context. Over-inclusion can only cap more, never less.
    """
    chunk_ids: set[str] = set()
    paper_ids: set[str] = set()
    for call in tool_calls:
        if not call.ok:
            continue
        chunk_ids.update(c.chunk_id for c in call.citations)
        if call.name == "read_paper":
            paper_id = call.args.get("paper_id")
            if isinstance(paper_id, str) and paper_id:
                paper_ids.add(paper_id)

    sources: dict[str, list[str]] = {}
    if paper_ids:
        marks = ",".join("?" * len(paper_ids))
        rows = conn.execute(
            f"SELECT paper_id, text FROM chunks WHERE paper_id IN ({marks})",  # noqa: S608
            tuple(paper_ids),
        ).fetchall()
        for paper_id, text in rows:
            sources.setdefault(paper_id, []).append(text)
    if chunk_ids:
        marks = ",".join("?" * len(chunk_ids))
        rows = conn.execute(
            f"SELECT paper_id, text FROM chunks WHERE chunk_id IN ({marks})",  # noqa: S608
            tuple(chunk_ids),
        ).fetchall()
        for paper_id, text in rows:
            if paper_id not in paper_ids:  # already have every chunk of those
                sources.setdefault(paper_id, []).append(text)
    return sources


def _normalized_words(text: str) -> list[tuple[str, int, int]]:
    """(lowercased word, start, end) — the unit both caps are measured in.

    Normalizing away case and whitespace is what stops a reformatted dump from
    laundering itself past the overlap check.
    """
    return [(m.group(0).lower(), m.start(), m.end()) for m in _WORD.finditer(text)]


def _shingles(words: Sequence[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def _source_index(sources: dict[str, list[str]], size: int) -> dict[tuple[str, ...], set[str]]:
    """Every `size`-word window of every source, mapped to the papers holding it.

    A window can belong to more than one paper (identical boilerplate, or the
    same passage quoted in two papers), which is why the value is a set — the
    per-paper budget must not be charged to an arbitrary single owner.
    """
    index: dict[tuple[str, ...], set[str]] = {}
    for paper_id, texts in sources.items():
        for text in texts:
            words = [w for w, _, _ in _normalized_words(text)]
            for shingle in _shingles(words, size):
                index.setdefault(shingle, set()).add(paper_id)
    return index


def _verbatim_runs(
    text: str, sources: dict[str, list[str]], max_words: int
) -> list[tuple[int, int, frozenset[str]]]:
    """Maximal runs of `text` that appear verbatim in a source, as word-index
    spans [start, end) over the answer, each with the papers it came from.

    A run is only interesting once it is longer than the cap, so the probe
    window is `max_words + 1`: if no window of that length matches, no quote
    exceeds the limit and there is nothing to truncate.
    """
    words = _normalized_words(text)
    if not words or not sources:
        return []
    probe = max_words + 1
    if len(words) < probe:
        return []

    index = _source_index(sources, probe)
    runs: list[tuple[int, int, frozenset[str]]] = []
    i = 0
    plain = [w for w, _, _ in words]
    while i <= len(plain) - probe:
        owners = index.get(tuple(plain[i : i + probe]))
        if owners is None:
            i += 1
            continue
        # Extend one word at a time for as long as the run stays verbatim.
        end = i + probe
        while end < len(plain):
            nxt = index.get(tuple(plain[end - probe + 1 : end + 1]))
            if nxt is None:
                break
            owners = owners | nxt
            end += 1
        runs.append((i, end, frozenset(owners)))
        i = end
    return runs


def _short_quote_runs(
    text: str, sources: dict[str, list[str]], min_words: int
) -> list[tuple[int, int, frozenset[str]]]:
    """Verbatim runs at least `min_words` long — used to COUNT quotes per paper.

    Distinct from `_verbatim_runs`, which finds only over-length ones. A quote
    short enough to be legal still consumes one of the paper's three slots.
    """
    words = [w for w, _, _ in _normalized_words(text)]
    if len(words) < min_words or not sources:
        return []
    index = _source_index(sources, min_words)
    runs: list[tuple[int, int, frozenset[str]]] = []
    i = 0
    while i <= len(words) - min_words:
        owners = index.get(tuple(words[i : i + min_words]))
        if owners is None:
            i += 1
            continue
        end = i + min_words
        while end < len(words):
            nxt = index.get(tuple(words[end - min_words + 1 : end + 1]))
            if nxt is None:
                break
            owners = owners | nxt
            end += 1
        runs.append((i, end, frozenset(owners)))
        i = end
    return runs


def _cut(text: str, words: list[tuple[str, int, int]], start: int, end: int, keep: int) -> str:
    """Replace answer words [start, end) with their first `keep`, marked."""
    cut_from = words[start + keep][1] if keep else words[start][1]
    # An ellipsis, not a policy sentence. A bracketed rule name dropped into
    # mid-sentence prose made real answers incoherent (measured on a live turn,
    # 2026-08-28); "[…]" is the ordinary scholarly elision mark, so the reader
    # can see something was cut without the sentence falling apart. What was
    # cut, and why, goes to the log — that is where an audit looks.
    return text[:cut_from] + "[…]" + text[words[end - 1][2] :]


def harden(
    text: str,
    *,
    tool_calls: Sequence[ToolCallRecord],
    sources: dict[str, list[str]],
    settings: Settings,
) -> HardenedAnswer:
    """Apply both output-side rules to one answer, and report what changed.

    `sources` maps paper_id -> the texts this turn let the model see. It is
    supplied by the caller (which owns the db handle) rather than fetched here,
    so this module stays pure and testable without a corpus.
    """
    if not text.strip():
        return HardenedAnswer(text=text)

    quote_words = settings.quote_max_words
    per_paper = settings.max_quotes_per_paper

    # 1. Truncate over-length verbatim runs, longest-offset first so earlier
    #    spans keep their character offsets valid.
    capped = 0
    for start, end, _ in sorted(_verbatim_runs(text, sources, quote_words), reverse=True):
        words = _normalized_words(text)
        text = _cut(text, words, start, end, keep=quote_words)
        capped += 1

    # 2. Enforce the per-paper quote budget over what remains. Counting runs at
    #    a short floor catches the sequential-excerpt case the long-run check
    #    cannot: many legal quotes that together rebuild a section.
    dropped = 0
    runs = _short_quote_runs(text, sources, min_words=settings.quote_min_words)
    used: dict[str, int] = {}
    over: list[tuple[int, int]] = []
    for start, end, owners in runs:
        # One span charges one slot per owning paper; a span shared by two
        # papers is still a single quote, not two.
        if all(used.get(p, 0) >= per_paper for p in owners):
            over.append((start, end))
            continue
        for paper_id in owners:
            used[paper_id] = used.get(paper_id, 0) + 1
    for start, end in sorted(over, reverse=True):
        words = _normalized_words(text)
        text = _cut(text, words, start, end, keep=0)
        dropped += 1

    # 3. Strip citations to papers this turn never retrieved.
    allowed = retrieved_paper_ids(tool_calls)
    stripped: list[str] = []

    def _check(match: re.Match[str]) -> str:
        arxiv_id = match.group(1)
        if arxiv_id in allowed:
            return match.group(0)
        if arxiv_id not in stripped:
            stripped.append(arxiv_id)
        return "[citation removed: not retrieved this turn]"

    text = _ID_IN_TEXT.sub(_check, text)

    result = HardenedAnswer(
        text=text,
        stripped_ids=tuple(stripped),
        capped_quotes=capped,
        dropped_quotes=dropped,
    )
    if result.changed:
        _logger.warning(
            "askrag.api.answer_guard: hardened an answer",
            extra={
                "askrag.stripped_ids": list(result.stripped_ids),
                "askrag.capped_quotes": capped,
                "askrag.dropped_quotes": dropped,
            },
        )
    return result
