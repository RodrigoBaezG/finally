"""Chat service: orchestrates LLM call + auto-execution of returned actions."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

from app.chat.discovery import get_cached_free_models, invalidate_cache
from app.chat.execution import (
    TradeResult,
    WatchlistResult,
    execute_trade,
    execute_watchlist_change,
)
from app.chat.mock import generate_mock_response
from app.chat.parser import parse_llm_response
from app.chat.prompt import SYSTEM_PROMPT, build_portfolio_context
from app.db import queries
from app.market.cache import PriceCache

logger = logging.getLogger(__name__)

_LLM_TIMEOUT_SECONDS = 30
_HISTORY_LIMIT = 20
# Per-call cap on how many models from the chain we'll actually try before
# giving up with an error. Discovery may return 50+ free models — we don't
# want a single chat call to spend 30s trying 20 broken ones.
_MAX_MODEL_ATTEMPTS = 6

# Minimal fallback used only if OpenRouter's /models endpoint is unreachable.
_HARDCODED_FALLBACK = [
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/google/gemma-2-9b-it:free",
    "openrouter/deepseek/deepseek-chat:free",
]


def _is_mock_mode() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def _get_model_chain(api_key: str) -> list[str]:
    """Return the ordered list of models to try.

    Precedence:
      1. FINALLY_LLM_MODEL env var (comma-separated) — explicit user override.
      2. Live OpenRouter /api/v1/models endpoint, filtered to pricing == 0.
      3. Hardcoded fallback list (only if #2 fails).
    """
    override = os.environ.get("FINALLY_LLM_MODEL", "").strip()
    if override:
        return [m.strip() for m in override.split(",") if m.strip()]

    discovered = get_cached_free_models(api_key)
    if discovered:
        return discovered

    return list(_HARDCODED_FALLBACK)


def _build_llm_messages(
    system_prompt: str,
    portfolio_context: str,
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """Compose the message list sent to LiteLLM."""
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": f"Current portfolio state (JSON):\n{portfolio_context}",
        },
    ]
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_llm(messages: list[dict]) -> str:
    """Call LiteLLM → OpenRouter and return the raw text content.

    Returns an empty-but-valid JSON string on network / API errors so
    the rest of the pipeline can handle it gracefully.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENROUTER_API_KEY not set — cannot call LLM")
        return json.dumps(
            {
                "message": (
                    "I can't reach the language model right now — the server is missing "
                    "an OPENROUTER_API_KEY. Ask the administrator to configure it."
                ),
                "trades": [],
                "watchlist_changes": [],
            }
        )

    import litellm

    def _call_one(model: str, use_json_mode: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "api_key": api_key,
            "timeout": _LLM_TIMEOUT_SECONDS,
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = litellm.completion(**kwargs)
        return response["choices"][0]["message"]["content"] or ""

    # First pass: try up to _MAX_MODEL_ATTEMPTS models from the chain.
    # Second pass (only if the first ended in NotFoundError): invalidate the
    # discovery cache, re-fetch the live list, and try again. This recovers
    # automatically when OpenRouter retires a model between fetches.
    for attempt_round in (1, 2):
        models = _get_model_chain(api_key)[:_MAX_MODEL_ATTEMPTS]
        last_exc: Exception | None = None
        last_model: str = ""
        all_404 = True

        for model in models:
            try:
                return _call_one(model, use_json_mode=True)
            except litellm.BadRequestError as exc:
                # Some models (e.g., several on Google AI Studio) reject the
                # response_format=json_object flag. Retry once without it —
                # the parser handles plain-text with embedded JSON gracefully.
                if "json" in str(exc).lower():
                    logger.info("Model %s rejected JSON mode; retrying without it", model)
                    try:
                        return _call_one(model, use_json_mode=False)
                    except Exception as exc2:
                        logger.warning("Retry without JSON mode also failed on %s: %s", model, exc2)
                        last_exc = exc2
                        last_model = model
                        all_404 = False
                        continue
                logger.warning("BadRequest on %s: %s", model, exc)
                last_exc = exc
                last_model = model
                all_404 = False
                continue
            except litellm.RateLimitError as exc:
                logger.warning("Rate limited on %s: %s", model, exc)
                last_exc = exc
                last_model = model
                all_404 = False
                continue
            except litellm.NotFoundError as exc:
                logger.warning("Model %s not found: %s", model, exc)
                last_exc = exc
                last_model = model
                continue
            except Exception as exc:
                logger.exception("LiteLLM call failed for model %s: %s", model, exc)
                last_exc = exc
                last_model = model
                all_404 = False
                break

        # If everything was 404, the discovery snapshot is stale — refresh and retry once.
        if attempt_round == 1 and all_404 and isinstance(last_exc, litellm.NotFoundError):
            logger.info("All candidate models returned 404; refreshing discovery cache")
            invalidate_cache()
            continue

        break  # Either we got a non-404 failure, or we've already retried

    exc_name = type(last_exc).__name__ if last_exc else "UnknownError"
    hint = ""
    if isinstance(last_exc, litellm.RateLimitError):
        hint = (
            " All tried free models are currently rate-limited upstream. "
            "Wait a minute and retry, or set a paid model in FINALLY_LLM_MODEL "
            "(same id without the `:free` suffix) to use your OpenRouter credits."
        )
    elif isinstance(last_exc, litellm.NotFoundError):
        hint = (
            f" The last model tried ('{last_model}') was rejected by OpenRouter (404) "
            "and the live-discovered list also couldn't produce a working model. "
            "Browse https://openrouter.ai/models and set FINALLY_LLM_MODEL in .env."
        )
    return json.dumps(
        {
            "message": f"Sorry - I couldn't reach the model ({exc_name}).{hint}",
            "trades": [],
            "watchlist_changes": [],
        }
    )


def _persist_messages(
    conn: sqlite3.Connection,
    user_message: str,
    assistant_message: str,
    trade_results: list[TradeResult],
    watchlist_results: list[WatchlistResult],
    user_id: str = "default",
) -> None:
    """Persist user + assistant messages; only successful actions go in actions JSON."""
    queries.insert_chat_message(conn, "user", user_message, actions=None, user_id=user_id)

    executed_actions: dict[str, list[dict]] = {"trades": [], "watchlist_changes": []}
    for t in trade_results:
        if t.status == "executed":
            executed_actions["trades"].append(
                {
                    "ticker": t.ticker,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": t.price,
                }
            )
    for w in watchlist_results:
        if w.status == "executed":
            executed_actions["watchlist_changes"].append(
                {"ticker": w.ticker, "action": w.action}
            )

    actions_to_store = executed_actions if (
        executed_actions["trades"] or executed_actions["watchlist_changes"]
    ) else None

    queries.insert_chat_message(
        conn,
        "assistant",
        assistant_message,
        actions=actions_to_store,
        user_id=user_id,
    )


def _serialize_trade_result(t: TradeResult) -> dict:
    return {
        "ticker": t.ticker,
        "side": t.side,
        "quantity": t.quantity,
        "price": t.price,
        "status": t.status,
        "error": t.error,
    }


def _serialize_watchlist_result(w: WatchlistResult) -> dict:
    return {
        "ticker": w.ticker,
        "action": w.action,
        "status": w.status,
        "error": w.error,
    }


def handle_chat(
    conn: sqlite3.Connection,
    cache: PriceCache,
    user_message: str,
    user_id: str = "default",
) -> dict[str, Any]:
    """Full chat pipeline: build context, call LLM (or mock), execute, persist.

    Returns a JSON-serializable dict matching the frontend contract:
        {"message": str, "trades": [{ticker, side, quantity, price, status, error}],
         "watchlist_changes": [{ticker, action, status, error}]}
    """
    portfolio_context = build_portfolio_context(conn, cache, user_id)

    if _is_mock_mode():
        logger.info("LLM_MOCK=true — generating mock response")
        try:
            ctx_data = json.loads(portfolio_context)
        except (json.JSONDecodeError, TypeError):
            ctx_data = {}
        parsed = generate_mock_response(user_message, ctx_data)
    else:
        history = queries.list_chat_messages(conn, user_id=user_id, limit=_HISTORY_LIMIT)
        messages = _build_llm_messages(
            SYSTEM_PROMPT, portfolio_context, history, user_message
        )
        raw = _call_llm(messages)
        parsed = parse_llm_response(raw)

    trade_results: list[TradeResult] = []
    for trade in parsed.get("trades", []):
        result = execute_trade(
            conn=conn,
            cache=cache,
            ticker=trade["ticker"],
            side=trade["side"],
            quantity=float(trade["quantity"]),
            user_id=user_id,
        )
        trade_results.append(result)

    watchlist_results: list[WatchlistResult] = []
    for change in parsed.get("watchlist_changes", []):
        result = execute_watchlist_change(
            conn=conn,
            ticker=change["ticker"],
            action=change["action"],
            user_id=user_id,
        )
        watchlist_results.append(result)

    # Record a portfolio snapshot if any trades executed successfully
    if any(t.status == "executed" for t in trade_results):
        try:
            from app.api.portfolio import _record_snapshot

            _record_snapshot(conn, cache, user_id)
        except Exception:
            logger.exception("Failed to record post-trade snapshot")

    _persist_messages(
        conn,
        user_message,
        parsed.get("message", ""),
        trade_results,
        watchlist_results,
        user_id=user_id,
    )

    return {
        "message": parsed.get("message", ""),
        "trades": [_serialize_trade_result(t) for t in trade_results],
        "watchlist_changes": [_serialize_watchlist_result(w) for w in watchlist_results],
    }


__all__ = ["handle_chat"]
