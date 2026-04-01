"""Custom tools for undo/rollback operations."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_reversible_action(
    conversation_id: str,
    action_type: str,
    service: str,
    resource_id: str,
    forward_data: dict | None = None,
    reverse_data: dict | None = None,
) -> dict:
    """Log a reversible action for future undo capability.

    Call this after every mutating operation (create, update, delete)
    so the system can undo it later if requested.

    Args:
        conversation_id: The conversation this action belongs to
        action_type: Type of action (create_event, update_page, etc.)
        service: External service (calendar, notion)
        resource_id: ID of the resource that was created/modified
        forward_data: Data used to perform the action
        reverse_data: Data needed to undo the action

    Returns:
        Confirmation of the logged action.
    """
    # This will be called synchronously by the agent; the actual DB write
    # happens asynchronously via the crew module's callback system
    return {
        "logged": True,
        "action_type": action_type,
        "service": service,
        "resource_id": resource_id,
        "message": f"Action logged: {action_type} on {service}/{resource_id}. Can be undone.",
    }


def undo_last_action() -> dict:
    """Undo the most recent reversible action.

    This triggers the rollback service to find and reverse the last
    logged action across all conversations.

    Returns:
        Status of the undo operation.
    """
    # The actual implementation is handled by the crew module which has
    # access to the async database session
    return {
        "status": "undo_requested",
        "message": "Undo request submitted. The system will reverse the last action.",
    }


def undo_conversation_actions(conversation_id: str) -> dict:
    """Undo all actions from a specific conversation.

    Reverses all logged actions from a conversation in LIFO order
    (last action first).

    Args:
        conversation_id: ID of the conversation whose actions to undo

    Returns:
        Status of the undo operation.
    """
    return {
        "status": "undo_conversation_requested",
        "conversation_id": conversation_id,
        "message": f"Will undo all actions from conversation {conversation_id[:8]}…",
    }
