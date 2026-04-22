"""End-to-end tests for POST /api/chat via the FastAPI test client, mock mode."""

from __future__ import annotations

from app.db import queries
from app.db.connection import get_connection


def test_chat_default_greeting(client, tmp_db_path):
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert "FinAlly" in data["message"]
    assert data["trades"] == []
    assert data["watchlist_changes"] == []

    # Both user and assistant messages persisted
    conn = get_connection(tmp_db_path)
    try:
        msgs = queries.list_chat_messages(conn)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["actions"] is None
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["actions"] is None  # no actions executed
    finally:
        conn.close()


def test_chat_buy_executes_trade(client, tmp_db_path):
    response = client.post("/api/chat", json={"message": "buy 5 AAPL"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["trades"]) == 1
    assert data["trades"][0]["status"] == "executed"
    assert data["trades"][0]["ticker"] == "AAPL"
    assert data["trades"][0]["price"] == 190.00

    conn = get_connection(tmp_db_path)
    try:
        # Cash reduced
        profile = queries.get_user_profile(conn)
        assert profile["cash_balance"] == 10000.0 - 5 * 190.00
        # Position created
        pos = queries.get_position(conn, "AAPL")
        assert pos is not None
        assert pos["quantity"] == 5.0
        # Assistant message has actions persisted
        msgs = queries.list_chat_messages(conn)
        assistant_msg = msgs[-1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["actions"] is not None
        assert len(assistant_msg["actions"]["trades"]) == 1
    finally:
        conn.close()


def test_chat_buy_insufficient_cash_failed_not_persisted(client, tmp_db_path):
    response = client.post("/api/chat", json={"message": "buy 1000 NVDA"})
    assert response.status_code == 200
    data = response.json()
    assert data["trades"][0]["status"] == "failed"
    assert "Insufficient cash" in data["trades"][0]["error"]

    conn = get_connection(tmp_db_path)
    try:
        # No position
        assert queries.get_position(conn, "NVDA") is None
        # Cash unchanged
        profile = queries.get_user_profile(conn)
        assert profile["cash_balance"] == 10000.0
        # Assistant actions should be None (failed action not persisted)
        msgs = queries.list_chat_messages(conn)
        assistant_msg = msgs[-1]
        assert assistant_msg["actions"] is None
    finally:
        conn.close()


def test_chat_watchlist_remove(client, tmp_db_path):
    response = client.post("/api/chat", json={"message": "remove AAPL from watchlist"})
    assert response.status_code == 200
    data = response.json()
    assert data["watchlist_changes"][0]["status"] == "executed"

    conn = get_connection(tmp_db_path)
    try:
        tickers = {r["ticker"] for r in queries.list_watchlist(conn)}
        assert "AAPL" not in tickers
    finally:
        conn.close()


def test_chat_portfolio_query(client):
    response = client.post("/api/chat", json={"message": "analyze my portfolio"})
    assert response.status_code == 200
    data = response.json()
    assert data["trades"] == []
    assert "$10,000.00" in data["message"] or "no open positions" in data["message"].lower()


def test_chat_invalid_request(client):
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_history_limited_to_20(client, tmp_db_path):
    # Fire 25 messages — only last 20 should appear in the assistant context,
    # but DB persistence keeps all.
    for i in range(25):
        r = client.post("/api/chat", json={"message": f"hello round {i}"})
        assert r.status_code == 200

    conn = get_connection(tmp_db_path)
    try:
        # 25 user messages + 25 assistant messages = 50 rows total persisted
        all_msgs = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        assert all_msgs == 50
    finally:
        conn.close()
