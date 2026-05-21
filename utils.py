"""Shared utilities for the research agent."""
from __future__ import annotations
import json
import re


def extract_json(text: str) -> dict | list:
    """
    Robustly extract the first complete JSON object or array from LLM output.

    Handles:
    - Markdown code fences
    - Leading/trailing prose
    - Truncated responses (unterminated strings, unclosed braces)
    """
    if not text:
        raise ValueError("empty text")

    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Find the first { or [
    start = -1
    opener, closer = None, None
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            start = i
            opener = ch
            closer = '}' if ch == '{' else ']'
            break

    if start == -1:
        raise ValueError("no JSON object or array found")

    # Walk forward tracking brace depth and string state
    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    if end != -1:
        # Complete JSON found
        return json.loads(text[start:end])

    # ── Truncated response — attempt salvage ──────────────────────────────────
    # Strategy: strip back to the last comma (end of a complete key-value pair),
    # then close the object.  This recovers partial perception / decision dicts
    # so the agent can still use whatever fields were generated.
    fragment = text[start:].rstrip()
    last_comma = fragment.rfind(',')
    if last_comma > 0:
        fragment = fragment[:last_comma]
    else:
        # No comma — only the opener exists; return empty container
        return {} if opener == '{' else []

    fragment = fragment.rstrip(',').rstrip()
    fragment += closer * max(depth, 1)

    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        # Last resort: return empty container so callers can use fallback logic
        return {} if opener == '{' else []
