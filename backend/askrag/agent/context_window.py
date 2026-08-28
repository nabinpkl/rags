"""Evict stale tool results to keep one turn's running message list under the
per-message token ceiling (D1/D2).

Token counts here are a pre-call ESTIMATE (tiktoken, `tokenizer_encoding`)
used only to decide when to evict; the loop's real cost/budget accounting
comes from the API's `usage` field on each response, not this estimate.

Evict-only for v1, not evict-then-summarize (DECISIONS.md 2026-07-06):
summarizing needs an extra model call, which breaks the API-free test story
(house rule — tests never call an LLM) and spends part of the very budget it
is trying to save. Revisit trigger: eviction demonstrably drops context an
answer needed.

Messages carry two block shapes at once: assistant content is Anthropic SDK
objects (`TextBlock`/`ToolUseBlock`, attribute access), while `tool_result`
blocks are plain dicts the loop constructs itself (`ToolResultBlockParam`-
shaped). `_block_type`/`_block_get` read either uniformly.
"""

from typing import Any

import tiktoken

from askrag.config import Settings, get_settings

_EVICTED_STUB = "[evicted: earlier {tool} result]"


def _block_type(block: Any) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def _block_get(block: Any, key: str) -> Any:
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _message_content(message: Any) -> Any:
    return (
        message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    )


def _is_stub(text: Any) -> bool:
    return isinstance(text, str) and text.startswith("[evicted: earlier")


def _block_token_text(block: Any) -> str:
    block_type = _block_type(block)
    if block_type == "text":
        return _block_get(block, "text") or ""
    if block_type == "tool_use":
        return str(_block_get(block, "input"))
    if block_type == "tool_result":
        content = _block_get(block, "content")
        return content if isinstance(content, str) else ""
    return ""


def estimate_tokens(messages: list[Any], *, settings: Settings | None = None) -> int:
    """A pre-call token estimate over the whole running messages list."""
    settings = settings if settings is not None else get_settings()
    encoding = tiktoken.get_encoding(settings.tokenizer_encoding)
    total = 0
    for message in messages:
        content = _message_content(message)
        if isinstance(content, str):
            total += len(_encode(encoding, content))
        elif isinstance(content, list):
            for block in content:
                text = _block_token_text(block)
                if text:
                    total += len(_encode(encoding, text))
    return total


def _encode(encoding: tiktoken.Encoding, text: str) -> list[int]:
    """Tokenize, treating control-token spellings as ordinary text.

    Messages here carry TOOL RESULTS, i.e. retrieved paper text (§6: untrusted).
    A paper quoting "<|endofprompt|>" would otherwise raise inside the budget
    estimate and kill a live turn mid-answer — a corpus string taking down a
    request is exactly the class of thing the fence exists to prevent.
    """
    return encoding.encode(text, disallowed_special=())


def _tool_use_names(messages: list[Any]) -> dict[str, str]:
    """tool_use_id -> tool name, scanned from every message's tool_use blocks
    so an evicted tool_result's stub can still name which tool it stood for
    (a tool_result block itself carries no name, only the id it answers)."""
    names: dict[str, str] = {}
    for message in messages:
        content = _message_content(message)
        if not isinstance(content, list):
            continue
        for block in content:
            if _block_type(block) == "tool_use":
                names[_block_get(block, "id")] = _block_get(block, "name")
    return names


def _copy_message(message: Any) -> Any:
    content = _message_content(message)
    if isinstance(message, dict) and isinstance(content, list):
        return {**message, "content": [dict(b) if isinstance(b, dict) else b for b in content]}
    return dict(message) if isinstance(message, dict) else message


def evict_oldest(
    messages: list[Any], *, ceiling_tokens: int, settings: Settings | None = None
) -> list[Any]:
    """Return a copy of `messages` with the oldest tool_result content
    replaced by a short stub, one block at a time, until the estimate fits
    under `ceiling_tokens` or nothing is left to evict. Never touches the
    LAST message (the turn's newest content) and never touches anything but
    `tool_result` blocks — the system prompt lives outside this list
    entirely, and the current user turn is always the most recent message.
    """
    settings = settings if settings is not None else get_settings()
    messages = [_copy_message(m) for m in messages]
    if len(messages) <= 1:
        return messages

    tool_names = _tool_use_names(messages)
    protected = len(messages) - 1

    while estimate_tokens(messages, settings=settings) > ceiling_tokens:
        target: tuple[list[Any], int, Any] | None = None
        for message in messages[:protected]:
            content = _message_content(message)
            if not isinstance(content, list):
                continue
            for i, block in enumerate(content):
                if _block_type(block) == "tool_result" and not _is_stub(
                    _block_get(block, "content")
                ):
                    target = (content, i, block)
                    break
            if target is not None:
                break
        if target is None:
            break  # nothing left to evict; over budget accepted (the step cap is the real backstop)

        content, i, block = target
        tool_use_id = _block_get(block, "tool_use_id")
        stub = _EVICTED_STUB.format(tool=tool_names.get(tool_use_id, "tool"))
        content[i] = {"type": "tool_result", "tool_use_id": tool_use_id, "content": stub}

    return messages
