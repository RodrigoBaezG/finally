"""Tests for app.chat.parser.parse_llm_response."""

from __future__ import annotations

from app.chat.parser import parse_llm_response


def test_clean_json():
    raw = '{"message": "hi", "trades": [], "watchlist_changes": []}'
    result = parse_llm_response(raw)
    assert result["message"] == "hi"
    assert result["trades"] == []
    assert result["watchlist_changes"] == []


def test_fenced_json():
    raw = '```json\n{"message": "hello", "trades": []}\n```'
    result = parse_llm_response(raw)
    assert result["message"] == "hello"
    assert result["trades"] == []


def test_fenced_without_language():
    raw = '```\n{"message": "hi"}\n```'
    result = parse_llm_response(raw)
    assert result["message"] == "hi"


def test_json_with_leading_prose():
    raw = 'Here is the response:\n{"message": "hi", "trades": []}'
    result = parse_llm_response(raw)
    assert result["message"] == "hi"


def test_json_with_trailing_prose():
    raw = '{"message": "hi"} — hope that helps!'
    result = parse_llm_response(raw)
    assert result["message"] == "hi"


def test_missing_trades_field_defaults_empty():
    raw = '{"message": "hi"}'
    result = parse_llm_response(raw)
    assert result["trades"] == []
    assert result["watchlist_changes"] == []


def test_non_json_text_returns_raw_as_message():
    raw = "I cannot respond in JSON."
    result = parse_llm_response(raw)
    assert result["message"] == raw
    assert result["trades"] == []


def test_empty_string():
    result = parse_llm_response("")
    assert result["message"] == ""
    assert result["trades"] == []


def test_truncated_json():
    raw = '{"message": "hi", "trades": [{"ticker": "AAPL",'
    result = parse_llm_response(raw)
    # Can't parse — falls back to message = raw text
    assert "trades" in result
    assert result["trades"] == []


def test_trade_normalization():
    raw = '{"message": "", "trades": [{"ticker": "  aapl  ", "side": "BUY", "quantity": "5"}]}'
    result = parse_llm_response(raw)
    assert result["trades"] == [
        {"ticker": "AAPL", "side": "buy", "quantity": 5.0}
    ]


def test_watchlist_normalization():
    raw = (
        '{"message": "", "watchlist_changes": '
        '[{"ticker": "pypl", "action": "ADD"}]}'
    )
    result = parse_llm_response(raw)
    assert result["watchlist_changes"] == [{"ticker": "PYPL", "action": "add"}]


def test_skips_malformed_trade_entries():
    raw = (
        '{"message": "", "trades": ['
        '{"ticker": "AAPL", "side": "buy", "quantity": 5},'
        '{"missing": "fields"},'
        '"not a dict"'
        ']}'
    )
    result = parse_llm_response(raw)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["ticker"] == "AAPL"


def test_root_not_an_object():
    raw = '["hello", "world"]'
    result = parse_llm_response(raw)
    # Falls back to raw-as-message
    assert result["trades"] == []


def test_nested_braces_in_message():
    raw = '{"message": "Analyze { nested } braces", "trades": []}'
    result = parse_llm_response(raw)
    assert result["message"] == "Analyze { nested } braces"
