"""Sessions -> index documents and chunks (D21).

A document is a session; its one facet is the project it ran in. A chunk is
consecutive whole turns packed up to `chunk_size_tokens` (the arXiv chunk
cap, D7), so a position is a turn number and `pos_start`-`pos_end` name the
turns a hit spans. A turn longer than the cap is cut into token windows that
all carry its number. Turns are the natural boundary here, as sections are in
a paper, so there is no overlap. The section label is the head of the first
turn's prompt: what the person asked, the way a paper's heading names a part.
"""

from collections.abc import Callable
from dataclasses import dataclass

from askrag.retrieval.build_index import IndexChunk, IndexDocument
from askrag.sources.claude_transcripts.read_sessions import Session

PROJECT = "project"
_SECTION_CHARS = 80


@dataclass(frozen=True)
class Piece:
    turn: int
    prompt: str
    text: str
    n_tokens: int


def _pieces(
    session: Session,
    count: Callable[[str], int],
    split: Callable[[str, int], list[str]],
    max_tokens: int,
) -> list[Piece]:
    pieces: list[Piece] = []
    for turn in session.turns:
        text = turn.text
        n = count(text)
        if n <= max_tokens:
            pieces.append(Piece(turn.index, turn.prompt, text, n))
            continue
        for window in split(text, max_tokens):
            pieces.append(Piece(turn.index, turn.prompt, window, count(window)))
    return pieces


def chunk_session(
    session: Session,
    count: Callable[[str], int],
    split: Callable[[str, int], list[str]],
    max_tokens: int,
) -> list[IndexChunk]:
    chunks: list[IndexChunk] = []
    group: list[Piece] = []

    def flush() -> None:
        if not group:
            return
        text = "\n\n".join(p.text for p in group)
        chunks.append(
            IndexChunk(
                chunk_id=f"{session.session_id}#{len(chunks)}",
                doc_id=session.session_id,
                section=group[0].prompt[:_SECTION_CHARS],
                pos_start=group[0].turn,
                pos_end=group[-1].turn,
                text=text,
                n_tokens=count(text),
            )
        )
        group.clear()

    used = 0
    for piece in _pieces(session, count, split, max_tokens):
        # A window of a long turn stands alone; whole turns pack together.
        if group and used + piece.n_tokens > max_tokens:
            flush()
            used = 0
        group.append(piece)
        used += piece.n_tokens
    flush()
    return chunks


def document_of(session: Session) -> IndexDocument:
    return IndexDocument(
        doc_id=session.session_id,
        title=session.title,
        day=session.day,
        version=None,
        facets=((PROJECT, session.project),),
    )
