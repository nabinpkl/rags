"""answer_guard: nothing leaves in an answer that the turn did not retrieve.

Spec §6c row 4 is enforced HERE — at answer assembly, server-side, per answer.
Row 1 (`read_paper`'s model-facing deep read) is deliberately untouched: the
2026-07-06 clarification makes them two different enforcement points, and
re-applying row 4's caps at the model-read boundary would break a real deep
read.

Every test here describes an attack or a leak, not a formatting preference.
"""

import pytest

from askrag.api import answer_guard
from askrag.config import Settings
from askrag.traces import Citation, ToolCallRecord

SETTINGS = Settings(_env_file=None)  # ty: ignore[unknown-argument]

# ~100 words of "source" text the model legitimately read — long enough to
# carve four separate quotes that each clear `quote_min_words`.
SOURCE = (
    "Qwen3 uses a three stage pre training process that begins with general "
    "knowledge then moves to reasoning data and finally extends the context "
    "window to thirty two thousand tokens which the report describes as the "
    "long context stage of training and this sentence exists only to push the "
    "passage past fifty words in total length overall so that the truncation "
    "path has something to truncate and the per paper budget has four distinct "
    "excerpts to count rather than one continuous run of shared terminology "
    "drawn from a single sentence of the report itself"
)


def _call(name: str, args: dict, citations=(), ok: bool = True) -> ToolCallRecord:
    return ToolCallRecord(name=name, args=args, ok=ok, citations=tuple(citations))


def _sources(text: str = SOURCE, paper_id: str = "2505.09388") -> dict[str, list[str]]:
    return {paper_id: [text]}


# --- citation verification ------------------------------------------------


def test_an_id_the_turn_never_retrieved_is_stripped():
    """THE injection case: retrieved paper text tells the model to cite a paper.

    The model obeys and writes a real-looking arXiv id. Nothing retrieved it,
    so it must not reach the user as a citation.
    """
    text = "This follows from arXiv:2505.09388 and also from arXiv:1234.56789."
    result = answer_guard.harden(
        text,
        tool_calls=(_call("search_corpus", {}, [Citation("2505.09388", "2505.09388#0")]),),
        sources={},
        settings=SETTINGS,
    )

    assert "2505.09388" in result.text
    assert "1234.56789" not in result.text
    assert result.stripped_ids == ("1234.56789",)


def test_a_paper_read_via_read_paper_counts_as_retrieved():
    """read_paper contributes no Citations (known gap #27), but the model DID
    read it — treating it as unretrieved would strip legitimate citations."""
    text = "See arXiv:2505.09388 for the training recipe."
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources={},
        settings=SETTINGS,
    )

    assert "2505.09388" in result.text
    assert result.stripped_ids == ()


def test_a_failed_tool_call_does_not_authorize_its_id():
    """An errored read is not a retrieval — otherwise asking for a paper would
    be enough to cite it."""
    text = "As shown in arXiv:2505.09388."
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}, ok=False),),
        sources={},
        settings=SETTINGS,
    )

    assert result.stripped_ids == ("2505.09388",)


def test_versioned_and_prefixed_forms_of_a_retrieved_id_survive():
    text = "See arXiv:2505.09388v2 and https://arxiv.org/abs/2505.09388 for detail."
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources={},
        settings=SETTINGS,
    )

    assert result.stripped_ids == ()
    assert "2505.09388v2" in result.text


# --- §6c row 4: verbatim quote caps ---------------------------------------


def test_a_verbatim_run_over_the_word_cap_is_truncated():
    """Raw retrieved chunks are never dumped to the UI (§6c row 4)."""
    result = answer_guard.harden(
        f'The report says: "{SOURCE}"',
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.capped_quotes == 1
    quoted_words = len(SOURCE.split())
    assert len(result.text.split()) < quoted_words
    assert "three stage pre training" in result.text  # the first 50 words survive
    assert "past fifty words in total length overall" not in result.text


def test_a_short_verbatim_quote_is_left_alone():
    """The cap is 50 words, not "no quoting" — a cited short quote is the
    documented, permitted behavior."""
    short = " ".join(SOURCE.split()[:12])
    result = answer_guard.harden(
        f'It says "{short}" (arXiv:2505.09388).',
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.capped_quotes == 0
    assert short in result.text


def test_paraphrase_is_never_touched():
    """Only VERBATIM overlap is capped. Generated prose in our own words is
    explicitly permitted (§6c row 3), and capping it would gut the product."""
    text = (
        "Qwen3 trains in three phases: broad knowledge first, then reasoning-"
        "heavy data, then a longer context window. The report frames this as a "
        "deliberate curriculum rather than one undifferentiated pre-training run "
        "over a single mixed corpus of text drawn from many different domains."
    )
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.capped_quotes == 0
    assert result.text == text


def test_more_than_three_quotes_from_one_paper_are_dropped():
    """≤3 quotes per paper per answer — the sequential-excerpt reconstruction
    guard. Four legal-length quotes still breach the per-paper limit."""
    words = SOURCE.split()
    quotes = [" ".join(words[i : i + 16]) for i in (0, 18, 36, 54)]
    text = " and ".join(f'"{q}"' for q in quotes)
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.dropped_quotes == 1
    assert quotes[0] in result.text
    assert quotes[3] not in result.text


OTHER_SOURCE = (
    "DeepSeekMath introduces group relative policy optimization which removes "
    "the value network from the usual actor critic setup and estimates the "
    "baseline from a group of sampled outputs instead of a learned critic "
    "which lowers memory pressure during training and removes one whole model "
    "from the optimization loop entirely as the report explains at length"
)


def test_the_per_paper_budget_is_per_paper():
    """Three quotes from each of two papers is not six quotes from one.

    A single shared budget would silently halve what a multi-paper answer may
    quote, which is the common case for a co-citation question.
    """
    a = SOURCE.split()
    b = OTHER_SOURCE.split()
    quotes = [" ".join(a[i : i + 16]) for i in (0, 18, 36)]
    quotes += [" ".join(b[i : i + 16]) for i in (0, 18, 36)]
    text = " and ".join(f'"{q}"' for q in quotes)

    result = answer_guard.harden(
        text,
        tool_calls=(
            _call("read_paper", {"paper_id": "2505.09388"}),
            _call("read_paper", {"paper_id": "2402.03300"}),
        ),
        sources={"2505.09388": [SOURCE], "2402.03300": [OTHER_SOURCE]},
        settings=SETTINGS,
    )

    assert result.dropped_quotes == 0
    for quote in quotes:
        assert quote in result.text


def test_a_fourth_quote_from_one_paper_is_dropped_even_beside_another_paper():
    """The per-paper budget is a cap, not a per-answer allowance to spend
    anywhere — four from one paper breaches it however many papers are cited."""
    a = SOURCE.split()
    quotes = [" ".join(a[i : i + 16]) for i in (0, 18, 36, 54)]
    quotes.append(" ".join(OTHER_SOURCE.split()[:16]))
    text = " and ".join(f'"{q}"' for q in quotes)

    result = answer_guard.harden(
        text,
        tool_calls=(
            _call("read_paper", {"paper_id": "2505.09388"}),
            _call("read_paper", {"paper_id": "2402.03300"}),
        ),
        sources={"2505.09388": [SOURCE], "2402.03300": [OTHER_SOURCE]},
        settings=SETTINGS,
    )

    assert result.dropped_quotes == 1
    assert quotes[4] in result.text  # the other paper's quote is unaffected


def test_whitespace_and_case_do_not_defeat_the_cap():
    """Reformatting a dump must not launder it past the check."""
    laundered = SOURCE.upper().replace(" ", "\n  ")
    result = answer_guard.harden(
        laundered,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.capped_quotes == 1


def test_hardening_reports_what_it_changed():
    """Stripped + logged, per the issue — a silent guard cannot be audited."""
    result = answer_guard.harden(
        f'"{SOURCE}" per arXiv:9999.99999',
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.changed
    assert result.stripped_ids == ("9999.99999",)
    assert result.capped_quotes == 1


def test_a_clean_answer_is_returned_unchanged():
    text = "Qwen3 trains in three stages (arXiv:2505.09388)."
    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.text == text
    assert not result.changed


@pytest.mark.parametrize("empty", ["", "   "])
def test_an_empty_answer_is_not_an_error(empty):
    result = answer_guard.harden(empty, tool_calls=(), sources={}, settings=SETTINGS)
    assert result.text == empty
    assert not result.changed


# --- no full-text egress path (issue #36 acceptance) ----------------------


def test_only_one_api_path_reads_chunk_text_and_it_is_capped():
    """The grep half of #36's acceptance, as a test so it cannot rot.

    Chunk text may be READ in exactly two places in the API layer:
    `routes_explorer._cited_excerpts`, which word-caps what it returns, and
    `answer_guard.fetch_sources`, which never emits what it reads — it exists
    only to detect verbatim overlap. A third reader is a new egress path and
    must justify itself here.
    """
    import pathlib
    import re

    api = pathlib.Path(__file__).resolve().parents[1] / "askrag" / "api"
    reader = re.compile(r"text\s+FROM\s+chunks", re.IGNORECASE)
    found = {
        path.name
        for path in api.glob("*.py")
        if any(reader.search(line) for line in path.read_text().splitlines())
    }

    assert found == {"routes_explorer.py", "answer_guard.py"}, (
        f"new chunk-text reader in the API layer: {found}"
    )


def test_the_excerpt_endpoint_caps_every_row_it_returns():
    """The one egress path applies both §6c row 4 limits, not just one."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "askrag" / "api" / "routes_explorer.py"
    ).read_text()

    assert '_cap_words(r["text"], settings.quote_max_words)' in source
    assert "settings.max_quotes_per_paper" in source


def test_fetch_sources_output_never_reaches_a_response_model():
    """answer_guard reads chunk text but must not hand it onward.

    `harden` returns a HardenedAnswer whose only text field is the ANSWER —
    the sources it compared against are local to the call.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(answer_guard.HardenedAnswer)}
    assert fields == {"text", "stripped_ids", "capped_quotes", "dropped_quotes", "_spans"}


def test_shared_terminology_does_not_burn_the_quote_budget():
    """The floor that makes the ≤3 rule usable (config.quote_min_words).

    A live Qwen3 answer tripped the per-paper limit NINE times on phrases like
    "increasing the proportion of STEM, coding, reasoning" — technical wording
    any faithful answer reuses. §6c row 4 targets substantial excerpts and
    sequential-excerpt section reconstruction; neither is reachable in runs
    this short, and enforcing there mangles honest answers into incoherence.
    """
    words = SOURCE.split()
    phrases = [" ".join(words[i : i + 6]) for i in (0, 12, 24, 36, 48, 60)]
    text = " and then it says ".join(f'"{p}"' for p in phrases)

    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.dropped_quotes == 0
    assert not result.changed


def test_an_elided_quote_leaves_readable_prose():
    """The remediation must not be worse than the breach.

    A bracketed policy sentence dropped mid-paragraph made a real answer
    incoherent; "[…]" is the ordinary elision mark and keeps the sentence
    standing. What was cut goes to the log, not into the reader's paragraph.
    """
    words = SOURCE.split()
    quotes = [" ".join(words[i : i + 16]) for i in (0, 18, 36, 54)]
    text = " and ".join(f'"{q}"' for q in quotes)

    result = answer_guard.harden(
        text,
        tool_calls=(_call("read_paper", {"paper_id": "2505.09388"}),),
        sources=_sources(),
        settings=SETTINGS,
    )

    assert result.dropped_quotes == 1
    assert "[…]" in result.text
    assert "§6c" not in result.text
    assert "quote removed" not in result.text
