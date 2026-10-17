"""Both prompt sets fence the excerpt and tell the models it is data (§6)."""

import pytest

from evals.draft_prompts import ARXIV, CLAUDE_TRANSCRIPTS


@pytest.mark.parametrize("prompts", [ARXIV, CLAUDE_TRANSCRIPTS])
def test_the_excerpt_is_fenced_and_untrusted(prompts):
    for system in (prompts.draft_system, prompts.grade_system):
        assert f"<{prompts.fence}>" in system
        assert "untrusted" in system


def test_the_transcript_prompts_speak_of_sessions_not_papers():
    assert "researcher" not in CLAUDE_TRANSCRIPTS.draft_system
    assert "arXiv" not in CLAUDE_TRANSCRIPTS.draft_system
    assert "session" in CLAUDE_TRANSCRIPTS.draft_system
