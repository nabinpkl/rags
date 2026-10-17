"""Secrets and email addresses out of transcript text, before anything is
stored or embedded (D21).

Session logs hold real credentials: keys pasted into a prompt, an `.env`
printed by a command, a token in a curl header. Every match is replaced by
`[redacted:<kind>]` and only the per-kind COUNT is ever logged. The patterns
are the known credential shapes plus `NAME=value` assignments whose name says
key, token, secret, password or salt; git hashes and UUIDs are left alone
because they are what a session is searched by.
"""

import re
from collections import Counter

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    ),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("tailscale_key", re.compile(r"\btskey-[A-Za-z0-9-]{20,}")),
    # JWTs and base64 JSON blobs (a Cloudflare tunnel token is one).
    ("token", re.compile(r"\beyJ[A-Za-z0-9+/=_-]{30,}(?:\.[A-Za-z0-9+/=_-]{10,}){0,2}")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "assignment",
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|SALT)[A-Z0-9_]*)"
            r"(\s*[=:]\s*['\"]?)([^\s'\"<>\[]{16,})"
        ),
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)


def redact(text: str) -> tuple[str, Counter[str]]:
    """The text with every match replaced, and how many of each kind."""
    counts: Counter[str] = Counter()
    for kind, pattern in _PATTERNS:

        def replace(match: re.Match[str], kind: str = kind) -> str:
            counts[kind] += 1
            if kind == "assignment":
                return f"{match.group(1)}{match.group(2)}[redacted:secret]"
            return f"[redacted:{kind}]"

        text = pattern.sub(replace, text)
    return text, counts
