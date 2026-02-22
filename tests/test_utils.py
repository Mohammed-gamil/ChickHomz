"""Tests for parse_llm_json utility — Decision #9A."""

from utils import parse_llm_json


def test_clean_json():
    assert parse_llm_json('{"key": "value"}') == {"key": "value"}


def test_json_with_markdown_fence():
    raw = '```json\n{"key": "value"}\n```'
    assert parse_llm_json(raw) == {"key": "value"}


def test_json_with_bare_fence():
    raw = '```\n{"key": "value"}\n```'
    assert parse_llm_json(raw) == {"key": "value"}


def test_json_with_trailing_text():
    raw = '{"key": "value"}\n\nSome explanation here'
    assert parse_llm_json(raw) == {"key": "value"}


def test_invalid_json_returns_fallback():
    assert parse_llm_json("not json at all", {"default": True}) == {"default": True}


def test_empty_string_returns_fallback():
    assert parse_llm_json("", {"default": True}) == {"default": True}


def test_none_fallback():
    assert parse_llm_json("bad") == {}


def test_arabic_content():
    raw = '{"title": "ركنة خشب", "price": 5000}'
    result = parse_llm_json(raw)
    assert result["title"] == "ركنة خشب"
    assert result["price"] == 5000


def test_nested_json():
    raw = '{"budget_signals": {"implicit_range": [0, 5000], "price_sensitive": true}}'
    result = parse_llm_json(raw)
    assert result["budget_signals"]["implicit_range"] == [0, 5000]


def test_json_array():
    raw = '[{"id": "1", "score": 90}, {"id": "2", "score": 80}]'
    result = parse_llm_json(raw)
    assert isinstance(result, list)
    assert len(result) == 2


def test_json_in_surrounding_text():
    raw = 'Here is the analysis:\n{"key": "value"}\nEnd of analysis.'
    assert parse_llm_json(raw) == {"key": "value"}
