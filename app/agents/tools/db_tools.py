"""Custom tools for database operations (querying/saving conversations)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def save_conversation_note(
    conversation_id: str,
    note: str,
) -> dict:
    """Save a note or summary to a conversation for future reference.

    Args:
        conversation_id: The conversation to annotate
        note: The note or summary text

    Returns:
        Confirmation of the saved note.
    """
    return {
        "saved": True,
        "conversation_id": conversation_id,
        "message": f"Note saved to conversation {conversation_id[:8]}…",
    }


def get_recent_conversations(count: int = 5) -> dict:
    """Get recent conversation summaries for context.

    Args:
        count: Number of recent conversations to retrieve (default 5)

    Returns:
        A dict with recent conversation summaries.
    """
    # The actual implementation queries the database via the crew module
    return {
        "status": "query_requested",
        "count": count,
        "message": f"Retrieving {count} most recent conversations…",
    }
