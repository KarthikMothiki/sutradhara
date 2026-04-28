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

    async def execute_undo(self, session: AsyncSession, action: ActionLog) -> dict:
        """Perform the actual API call to reverse an action."""
        from app.config import get_settings
        if get_settings().demo_mode:
            logger.info(f"🎭 DEMO MODE: Simulating undo of {action.action_type}")
            await self.mark_reversed(session, action.id)
            return {"success": True, "mode": "demo"}

        try:
            if action.service == "calendar":
                from app.auth.google_auth import build_calendar_service
                service = build_calendar_service()
                
                if action.action_type == "create_event":
                    # Reverse: Delete the event
                    service.events().delete(calendarId='primary', eventId=action.resource_id).execute()
                    await self.mark_reversed(session, action.id)
                    return {"success": True, "reversed": "deleted_event"}
                
                if action.action_type in ["update_event", "update_calendar"]:
                    # Reverse: Patch back to original data
                    if not action.reverse_data:
                        return {"error": "No reverse data found for update"}
                    service.events().patch(calendarId='primary', eventId=action.resource_id, body=action.reverse_data).execute()
                    await self.mark_reversed(session, action.id)
                    return {"success": True, "reversed": "restored_event"}

            elif action.service == "notion":
                from app.auth.notion_auth import get_notion_client
                client = get_notion_client()
                
                if action.action_type == "create_notion_page":
                    # Reverse: Archive the page
                    await client.pages.update(page_id=action.resource_id, archived=True)
                    await self.mark_reversed(session, action.id)
                    return {"success": True, "reversed": "archived_page"}

                if action.action_type == "update_notion_page":
                    # Reverse: Patch back to original data
                    if not action.reverse_data:
                        return {"error": "No reverse data found for update"}
                    await client.pages.update(page_id=action.resource_id, properties=action.reverse_data)
                    await self.mark_reversed(session, action.id)
                    return {"success": True, "reversed": "restored_page"}

            return {"error": f"Undo logic not implemented for {action.service}/{action.action_type}"}
        except Exception as e:
            logger.error(f"Undo failed for action {action.id}: {e}")
            return {"error": str(e)}


# ── Singleton ───────────────────────────────────────────────────
rollback_service = RollbackService()
