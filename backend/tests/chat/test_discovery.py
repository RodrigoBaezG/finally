"""Tests for OpenRouter free model discovery."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.chat import discovery
from app.chat.discovery import (
    _is_free,
    discover_free_models,
    get_cached_free_models,
    invalidate_cache,
)


def test_is_free_zero_pricing():
    assert _is_free({"pricing": {"prompt": "0", "completion": "0"}}) is True


def test_is_free_rejects_paid():
    assert _is_free({"pricing": {"prompt": "0.0001", "completion": "0.0002"}}) is False


def test_is_free_handles_missing_pricing():
    assert _is_free({}) is True  # defaults "0"/"0" → free


def test_is_free_handles_bad_values():
    assert _is_free({"pricing": {"prompt": "not-a-number", "completion": "0"}}) is False


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_discover_free_models_filters_and_prefixes(monkeypatch):
    payload = {
        "data": [
            {"id": "meta-llama/llama-3.3-70b-instruct:free",
             "pricing": {"prompt": "0", "completion": "0"},
             "context_length": 128000},
            {"id": "anthropic/claude-sonnet-4-6",
             "pricing": {"prompt": "0.003", "completion": "0.015"},
             "context_length": 200000},
            {"id": "google/gemma-2-9b-it:free",
             "pricing": {"prompt": "0", "completion": "0"},
             "context_length": 8192},
        ]
    }

    def _fake_urlopen(req, timeout=0):
        return _FakeResponse(payload)

    monkeypatch.setattr(discovery.urllib.request, "urlopen", _fake_urlopen)
    result = discover_free_models("fake-key")

    assert result == [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/google/gemma-2-9b-it:free",
    ]


def test_discover_returns_empty_on_network_error(monkeypatch):
    def _raising(req, timeout=0):
        import urllib.error
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(discovery.urllib.request, "urlopen", _raising)
    assert discover_free_models("fake-key") == []


def test_cache_populated_and_reused(monkeypatch):
    invalidate_cache()
    call_count = {"n": 0}

    def _counted_discover(api_key):
        call_count["n"] += 1
        return ["openrouter/foo:free"]

    with patch("app.chat.discovery.discover_free_models", _counted_discover):
        first = get_cached_free_models("k")
        second = get_cached_free_models("k")

    assert first == ["openrouter/foo:free"]
    assert second == ["openrouter/foo:free"]
    assert call_count["n"] == 1  # cached, not re-fetched

    invalidate_cache()


def test_invalidate_triggers_refetch(monkeypatch):
    invalidate_cache()
    call_count = {"n": 0}

    def _counted_discover(api_key):
        call_count["n"] += 1
        return ["openrouter/foo:free"]

    with patch("app.chat.discovery.discover_free_models", _counted_discover):
        get_cached_free_models("k")
        invalidate_cache()
        get_cached_free_models("k")

    assert call_count["n"] == 2

    invalidate_cache()
