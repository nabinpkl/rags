"""Tests for askrag.sources.claude_transcripts.redact_secrets — written with
the shapes that must never reach an index (security-relevant, §6)."""

import pytest

from askrag.sources.claude_transcripts.redact_secrets import redact

FAKE = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"export OPENROUTER_API_KEY=sk-or-v1-{FAKE}", "api_key"),
        (f"key sk-or-v1-{FAKE} pasted", "api_key"),
        (f"ghp_{FAKE}{FAKE[:6]}", "github_token"),
        ("AKIAABCDEFGHIJKLMNOP", "aws_key"),
        (f"tskey-auth-{FAKE}", "tailscale_key"),
        (f"Authorization: Bearer {FAKE}", "bearer"),
        (f"TUNNEL_TOKEN: eyJ{FAKE}{FAKE}", "token"),
        (f"DB_PASSWORD={FAKE}", "secret"),
        ("mail me at someone.name@example.com", "email"),
        (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----",
            "private_key",
        ),
    ],
)
def test_credential_shapes_are_redacted(text, kind):
    out, counts = redact(text)
    assert f"[redacted:{kind}]" in out
    assert FAKE not in out and "@example.com" not in out and "AKIAABCD" not in out
    assert sum(counts.values()) == 1  # one secret, counted once


@pytest.mark.parametrize(
    "text",
    [
        "commit a50ed82 and e9b6763023c676ca8431644204f50c2b100d9aab",
        "session 3db730b5-4260-42fa-89e3-c06a4dc3001c",
        "max_tokens=12000 and tokens_per_minute: 1_800_000",
        "the desk-1040 screenshot and task-notification",
        "SALT=<redacted> already",
    ],
)
def test_what_a_session_is_searched_by_survives(text):
    assert redact(text) == (text, {})


def test_the_name_of_an_assigned_secret_survives():
    out, _ = redact(f"OPENROUTER_API_KEY={FAKE}")
    assert out == "OPENROUTER_API_KEY=[redacted:secret]"
