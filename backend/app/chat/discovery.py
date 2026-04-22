"""Discover currently-available free models on OpenRouter.

Hits GET https://openrouter.ai/api/v1/models (public — key is optional but
gives us tier-appropriate visibility) and returns model ids whose prompt
and completion pricing are both "0". Results are cached in-process until
invalidated by a persistent 404.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_HTTP_TIMEOUT_SECONDS = 10

_cached_free_models: list[str] | None = None


def _fetch_raw(api_key: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(_OPENROUTER_MODELS_URL)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("User-Agent", "FinAlly/1.0")
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("data", [])
    if not isinstance(data, list):
        return []
    return data


def _is_free(model: dict[str, Any]) -> bool:
    pricing = model.get("pricing") or {}
    prompt_price = pricing.get("prompt", "0")
    completion_price = pricing.get("completion", "0")
    try:
        return float(prompt_price) == 0.0 and float(completion_price) == 0.0
    except (TypeError, ValueError):
        return False


def discover_free_models(api_key: str) -> list[str]:
    """Fetch and return a list of free model ids prefixed with `openrouter/`.

    Models are ordered by descending context length so larger-context models
    are tried first. An empty list is returned on network failure.
    """
    try:
        raw = _fetch_raw(api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warning("OpenRouter models discovery failed: %s", exc)
        return []
    except Exception:
        logger.exception("Unexpected error discovering OpenRouter models")
        return []

    free = [m for m in raw if _is_free(m) and isinstance(m.get("id"), str)]
    free.sort(key=lambda m: m.get("context_length", 0) or 0, reverse=True)

    ids = [f"openrouter/{m['id']}" for m in free]
    logger.info("Discovered %d free OpenRouter models", len(ids))
    return ids


def get_cached_free_models(api_key: str) -> list[str]:
    """Return the cached free model list, populating it on first call."""
    global _cached_free_models
    if _cached_free_models is None:
        _cached_free_models = discover_free_models(api_key)
    return list(_cached_free_models)


def invalidate_cache() -> None:
    """Force the next call to re-fetch the free model list."""
    global _cached_free_models
    _cached_free_models = None
