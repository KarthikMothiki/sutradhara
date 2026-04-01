"""Undo/rollback engine — logs mutating actions and reverses them on demand."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ActionLog

logger = logging.getLogger(__name__)


class RollbackService:
    """Manages action logging and undo/rollback operations.

    Every mutating action (create_event, create_page, etc.) is logged with:
    - forward_data: what was created/modified
    - reverse_data: what's needed to undo it

    Undo executes the reverse operation via the appropriate MCP tool.
    """

    # Map action_type → the reverse action_type for display
    REVERSE_MAP: dict[str, str] = {
        "create_event": "delete_event",
        "update_event": "update_event",  # reverse uses the original data
        "delete_event": "create_event",
        "create_page": "archive_page",
        "update_page": "update_page",
        "archive_page": "create_page",
    }

    async def log_action(
        self,
        session: AsyncSession,
        conversation_id: str,
        action_type: str,
        service: str,
        resource_id: str,
        forward_data: dict[str, Any] | None = None,
        reverse_data: dict[str, Any] | None = None,
    ) -> ActionLog:
        """Log a reversible action to the database."""
        action = ActionLog(
            conversation_id=conversation_id,
            action_type=action_type,
            service=service,
            resource_id=resource_id,
            forward_data=forward_data,
            reverse_data=reverse_data,
        )
        session.add(action)
        await session.flush()
        logger.info(
            f"Logged action: {action_type} on {service}/{resource_id} "
            f"(conv={conversation_id[:8]}…)"
        )
        return action

    async def get_undoable_actions(
        self, session: AsyncSession, conversation_id: str
    ) -> list[ActionLog]:
        """Get all non-reversed actions for a conversation, newest first."""
        result = await session.execute(
            select(ActionLog)
            .where(
                ActionLog.conversation_id == conversation_id,
                ActionLog.is_reversed == False,  # noqa: E712
            )
            .order_by(ActionLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_last_undoable_action(
        self, session: AsyncSession
    ) -> ActionLog | None:
        """Get the most recent non-reversed action across all conversations."""
        result = await session.execute(
            select(ActionLog)
            .where(ActionLog.is_reversed == False)  # noqa: E712
            .order_by(ActionLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_reversed(
        self, session: AsyncSession, action_id: str
    ) -> None:
        """Mark an action as reversed."""
        result = await session.execute(
            select(ActionLog).where(ActionLog.id == action_id)
        )
        action = result.scalar_one_or_none()
        if action:
            action.is_reversed = True
            await session.flush()

    async def undo_conversation(
        self, session: AsyncSession, conversation_id: str
    ) -> list[ActionLog]:
        """Get all actions to undo for a conversation (LIFO order)."""
        return await self.get_undoable_actions(session, conversation_id)


# ── Singleton ───────────────────────────────────────────────────
rollback_service = RollbackService()
