"""LLM response parser for FinAlly chat structured outputs.

Handles:
- Clean JSON
- JSON wrapped in markdown code fences (```json ... ```)
- JSON with leading/trailing prose
- Missing optional fields (defaults to empty lists)
- Invalid / truncated JSON (falls back gracefully)
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# The canonical empty/fallback shape
_EMPTY_RESPONSE: dict = {"message": "", "trades": [], "watchlist_changes": []}


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    # Match ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
    m = fence_pattern.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _extract_json_object(text: str) -> str:
    """Extract the first {...} block from text, handling nested braces."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    # No balanced close — return from start to end (will likely fail JSON parse)
    return text[start:]


def parse_llm_response(raw: str) -> dict:
    """Parse the raw LLM output into a structured dict.

    Returns a dict with keys: message (str), trades (list), watchlist_changes (list).
    On any parse failure, message is set to the raw text and actions are empty.
    """
    if not raw or not raw.strip():
        return {**_EMPTY_RESPONSE, "message": ""}

    # Step 1: strip code fences
    cleaned = _strip_fences(raw)

    # Step 2: extract first JSON object (handles leading prose)
    json_candidate = _extract_json_object(cleaned)

    # Step 3: parse
    try:
        data = json.loads(json_candidate)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON or malformed JSON: %.200s", raw)
        return {**_EMPTY_RESPONSE, "message": raw.strip()}

    if not isinstance(data, dict):
        logger.warning("LLM JSON root is not an object: %r", data)
        return {**_EMPTY_RESPONSE, "message": raw.strip()}

    message = data.get("message", "")
    if not isinstance(message, str):
        message = str(message)

    trades = data.get("trades", [])
    if not isinstance(trades, list):
        trades = []

    watchlist_changes = data.get("watchlist_changes", [])
    if not isinstance(watchlist_changes, list):
        watchlist_changes = []

    # Validate each trade entry minimally
    valid_trades = []
    for t in trades:
        if isinstance(t, dict) and "ticker" in t and "side" in t and "quantity" in t:
            valid_trades.append(
                {
                    "ticker": str(t["ticker"]).strip().upper(),
                    "side": str(t["side"]).strip().lower(),
                    "quantity": float(t["quantity"]),
                }
            )

    # Validate each watchlist change entry minimally
    valid_wl = []
    for w in watchlist_changes:
        if isinstance(w, dict) and "ticker" in w and "action" in w:
            valid_wl.append(
                {
                    "ticker": str(w["ticker"]).strip().upper(),
                    "action": str(w["action"]).strip().lower(),
                }
            )

    return {
        "message": message,
        "trades": valid_trades,
        "watchlist_changes": valid_wl,
    }
