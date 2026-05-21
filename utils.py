"""Shared utilities for the research agent."""
from __future__ import annotations
import json
import re


def extract_json(text: str) -> dict | list:
    """
    Robustly extract the first complete JSON object or array from LLM output.
    Handles markdown fences, leading prose, and truncated responses.
    """
    if not text:
        raise ValueError("empty text")

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Find the first { or [ and walk to the matching closer
    start = -1
    opener, closer = None, None
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            start = i
            opener, closer = ch, ('}' if ch == '{' else ']')
            break

    if start == -1:
        raise ValueError("no JSON object or array found in text")

    depth = 0
    in_string = False
    escape_next = False
    end = start

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

    json_str = text[start:end]

    # If we never closed (truncated response), attempt salvage by closing open braces
    if depth > 0:
        json_str = json_str.rstrip().rstrip(',') + (closer * depth)

    return json.loads(json_str)
