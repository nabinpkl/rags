"""Stratified source chunks for the golden set (D14 amendments).

Pure over a corpus.db connection: no model calls, so the sample is testable
and a redraft with the same seed sees the same chunks.

Stratified, not random: the indexed corpus is 43% cs.CL, so a random draw
would make the set a cs.CL set. Categories are visited round-robin in a
seeded order, and a paper gives at most one source per type.

"Rare" is measured against this corpus, not English: a term in at most
`golden_rare_term_max_df` chunks is distinctive enough that a question
repeating it is a keyword match rather than a test of retrieval.
"""

import random
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from evals.golden_set import GoldenType

_WORD = re.compile(r"[a-z][a-z0-9-]{3,}")
# A distinctive term an exact_match question can hinge on: an acronym, a
# model or benchmark name — mixed case or digits inside, 3 to 20 characters
# (LoRA, GRPO, SWE-bench, Qwen3). Plain capitalised words are not terms.
# Sections that restate the whole paper. A multi_hop pair drawn from one is
# answerable from that chunk alone, so neither side of a pair may be one.
_SUMMARY_SECTION = re.compile(
    r"abstract|introduction|conclu|summary|related work|literature review|__paper__", re.I
)
_TERM = re.compile(r"\b(?=[A-Za-z0-9-]*[A-Z][A-Za-z0-9-]*[A-Z0-9])[A-Z][A-Za-z0-9-]{2,19}\b")
_SKIP_SECTIONS = ("reference", "bibliograph", "acknowledg", "__paper__")


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    paper_id: str
    category: str
    section: str
    text: str


@dataclass(frozen=True)
class Source:
    """What one golden record is drafted from: one chunk, or two of one paper
    for multi_hop."""

    type: GoldenType
    chunks: tuple[SourceChunk, ...]
    # The words the question may not share with its chunk(s): the rare
    # terms, or for vocabulary_mismatch every word under its wider df bar.
    rare_terms: frozenset[str]
    anchor_term: str | None = None


def words(text: str) -> set[str]:
    """The comparison unit for the lexical rule: lowercased, a trailing
    plural dropped, so "embeddings" and "embedding" are one term."""
    return {w.removesuffix("s") for w in _WORD.findall(text.lower())}


def is_known_hard(text: str) -> bool:
    """A table (markdown rows) or math-dense chunk: D6's extraction floor."""
    table_rows = sum(1 for line in text.splitlines() if line.lstrip().startswith("|"))
    return table_rows >= 3 or text.count("$") + text.count("\\") >= 12


def load_chunks(conn: sqlite3.Connection, min_tokens: int) -> list[SourceChunk]:
    rows = conn.execute(
        "SELECT c.chunk_id, c.paper_id, c.section, c.text, c.n_tokens, p.primary_category"
        " FROM chunks c JOIN papers p ON p.arxiv_id = c.paper_id ORDER BY c.chunk_id"
    ).fetchall()
    return [
        SourceChunk(r["chunk_id"], r["paper_id"], r["primary_category"], r["section"], r["text"])
        for r in rows
        if r["n_tokens"] >= min_tokens
        and not any(s in r["section"].lower() for s in _SKIP_SECTIONS)
    ]


def document_frequency(conn: sqlite3.Connection) -> Counter[str]:
    """Chunks each term appears in, over the WHOLE index (short chunks too)."""
    df: Counter[str] = Counter()
    for (text,) in conn.execute("SELECT text FROM chunks"):
        df.update(words(text))
    return df


def rare_terms(text: str, df: Counter[str], max_df: int) -> frozenset[str]:
    return frozenset(w for w in words(text) if df[w] <= max_df)


def anchor_term(
    text: str,
    term_df: Counter[str],
    term_papers: Counter[str],
    max_df: int,
    word_df: Counter[str] | None = None,
) -> str | None:
    """The chunk's rarest distinctive term that other papers also use.

    Two papers at least: a term inside one paper only is either an extraction
    artefact or a running header repeated on every page ("ASE '26" became a
    venue-trivia question in the first smoke run). An all-caps word is an
    acronym only up to six letters; past that it is a shouted word
    ("DISTRIBUTED"). An all-caps word whose lowercase form is common is a
    shouted word too ("ANSWER", "INPUT" in prompt templates), and a hyphenated
    capitalised phrase ("Low-Level") is a phrase, not a name — both were
    anchors in the first full run."""
    common = word_df or Counter()
    terms = {
        t
        for t in _TERM.findall(text)
        if term_papers[t] >= 2
        and term_df[t] <= max_df
        and not (t.isupper() and len(t) > 6)
        and not (t.isupper() and common[t.lower().removesuffix("s")] > max_df)
        and not re.search(r"-[A-Z][a-z]", t)
    }
    return min(terms, key=lambda t: (term_df[t], t)) if terms else None


def _round_robin(
    pools: dict[str, list[SourceChunk]], n: int, rng: random.Random
) -> list[SourceChunk]:
    """Up to n chunks, one category at a time, one per paper."""
    order = sorted(pools)
    rng.shuffle(order)
    for pool in pools.values():
        rng.shuffle(pool)
    picked: list[SourceChunk] = []
    seen_papers: set[str] = set()
    while len(picked) < n and any(pools[c] for c in order):
        for category in order:
            pool = pools[category]
            while pool:
                chunk = pool.pop()
                if chunk.paper_id not in seen_papers:
                    picked.append(chunk)
                    seen_papers.add(chunk.paper_id)
                    break
            if len(picked) == n:
                break
    return picked


def sample_sources(
    chunks: list[SourceChunk],
    df: Counter[str],
    quota: dict[str, int],
    *,
    seed: int,
    rare_max_df: int,
    mismatch_max_df: int,
    multi_hop_min_shared: int,
) -> list[Source]:
    rng = random.Random(seed)
    term_df: Counter[str] = Counter()
    paper_terms: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        found = set(_TERM.findall(chunk.text))
        term_df.update(found)
        paper_terms[chunk.paper_id] |= found
    term_papers: Counter[str] = Counter()
    for found in paper_terms.values():
        term_papers.update(found)

    hard, prose = [], []
    for chunk in chunks:
        (hard if is_known_hard(chunk.text) else prose).append(chunk)
    used: set[str] = set()

    def pools(candidates: list[SourceChunk]) -> dict[str, list[SourceChunk]]:
        by_category: dict[str, list[SourceChunk]] = defaultdict(list)
        for chunk in candidates:
            if chunk.chunk_id not in used:
                by_category[chunk.category].append(chunk)
        return by_category

    def take(candidates: list[SourceChunk], n: int) -> list[SourceChunk]:
        picked = _round_robin(pools(candidates), n, rng)
        used.update(c.chunk_id for c in picked)
        return picked

    sources: list[Source] = []
    anchored = [c for c in prose if anchor_term(c.text, term_df, term_papers, rare_max_df, df)]
    for chunk in take(anchored, quota.get(GoldenType.EXACT_MATCH, 0)):
        sources.append(
            Source(
                GoldenType.EXACT_MATCH,
                (chunk,),
                rare_terms(chunk.text, df, rare_max_df),
                anchor_term(chunk.text, term_df, term_papers, rare_max_df, df),
            )
        )
    for type_, candidates in ((GoldenType.KNOWN_HARD, hard), (GoldenType.SINGLE_HOP, prose)):
        for chunk in take(candidates, quota.get(type_, 0)):
            sources.append(Source(type_, (chunk,), rare_terms(chunk.text, df, rare_max_df)))

    # multi_hop: two body chunks (no summary section) of one paper, in
    # different sections, naming the same things: the one sharing the most rare terms, at least
    # multi_hop_min_shared. Only chunks that have such a partner are sampled.
    by_paper: dict[str, list[SourceChunk]] = defaultdict(list)
    body = [c for c in prose if not _SUMMARY_SECTION.search(c.section)]
    for chunk in body:
        by_paper[chunk.paper_id].append(chunk)
    rare_of = {c.chunk_id: rare_terms(c.text, df, rare_max_df) for c in body}

    def partners(first: SourceChunk) -> list[tuple[int, SourceChunk]]:
        return [
            (shared, c)
            for c in by_paper[first.paper_id]
            if c.section != first.section
            and c.chunk_id not in used
            and (shared := len(rare_of[first.chunk_id] & rare_of[c.chunk_id]))
            >= multi_hop_min_shared
        ]

    pairable = [c for c in body if partners(c)]
    for first in take(pairable, quota.get(GoldenType.MULTI_HOP, 0)):
        ranked = partners(first)
        if not ranked:
            continue
        best = max(shared for shared, _ in ranked)
        second = rng.choice([c for shared, c in ranked if shared == best])
        used.add(second.chunk_id)
        pair = (first, second)
        sources.append(
            Source(GoldenType.MULTI_HOP, pair, rare_of[first.chunk_id] | rare_of[second.chunk_id])
        )

    # vocabulary_mismatch: chunks that name a method, model or benchmark, so
    # a searcher who has not read the paper has to describe it. Sampled last,
    # so adding this type moved none of the other types' sources.
    for chunk in take(anchored, quota.get(GoldenType.VOCABULARY_MISMATCH, 0)):
        sources.append(
            Source(
                GoldenType.VOCABULARY_MISMATCH,
                (chunk,),
                rare_terms(chunk.text, df, mismatch_max_df),
            )
        )
    return sources
