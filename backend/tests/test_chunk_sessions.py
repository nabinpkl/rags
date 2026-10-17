"""Tests for askrag.sources.claude_transcripts.chunk_sessions."""

from askrag.sources.claude_transcripts.chunk_sessions import PROJECT, chunk_session, document_of
from askrag.sources.claude_transcripts.read_sessions import Session, Turn


def count(text: str) -> int:
    return len(text.split())


def split(text: str, n: int) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + n]) for i in range(0, len(words), n)]


def session(*turn_words: int) -> Session:
    turns = [
        Turn(i, f"prompt {i}", [" ".join(["w"] * (n - 2))]) for i, n in enumerate(turn_words, 1)
    ]
    return Session("s", "rags", 20261001, "title", turns)


def test_whole_turns_pack_up_to_the_cap_and_never_overlap():
    chunks = chunk_session(session(4, 4, 4), count, split, max_tokens=10)
    assert [(c.pos_start, c.pos_end) for c in chunks] == [(1, 2), (3, 3)]
    assert [c.chunk_id for c in chunks] == ["s#0", "s#1"]
    assert chunks[0].section == "prompt 1"
    assert all(c.n_tokens <= 10 for c in chunks)


def test_a_turn_over_the_cap_is_cut_into_windows_with_its_number():
    # "User: prompt N" is three words, so turns of 4 and 26 words.
    chunks = chunk_session(session(3, 25), count, split, max_tokens=10)
    assert [(c.pos_start, c.pos_end, c.n_tokens) for c in chunks] == [
        (1, 1, 4),
        (2, 2, 10),
        (2, 2, 10),
        (2, 2, 6),
    ]


def test_a_session_is_a_document_faceted_by_project():
    doc = document_of(session(3))
    assert (doc.doc_id, doc.title, doc.day, doc.version, doc.facets) == (
        "s",
        "title",
        20261001,
        None,
        ((PROJECT, "rags"),),
    )
