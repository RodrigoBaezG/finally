"""FinAlly chat (LLM) subsystem.

Exports the FastAPI router mounted at /api/chat.
"""

from app.chat.router import router

__all__ = ["router"]
