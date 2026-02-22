"""Shared utilities for the Chic Homz agent."""

import json
import re


def parse_llm_json(raw: str, fallback=None):
    """
    Parse JSON from LLM output, handling markdown fences and edge cases.

    Handles:
    - Clean JSON
    - ```json ... ``` wrapped
    - ``` ... ``` wrapped (no language tag)
    - JSON embedded in surrounding text
    - JSON arrays

    Returns fallback (default: {}) if parsing fails entirely.
    """
    if fallback is None:
        fallback = {}

    if not raw or not raw.strip():
        return fallback

    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Try direct parse first (fastest path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract a JSON object from surrounding text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to extract a JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return fallback
