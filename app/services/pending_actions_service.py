"""Service for managing actions that require human-in-the-loop approval."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PendingAction
from app.services.trace_service import trace_service

logger = logging.getLogger(__name__)

class PendingActionsService:
    """Manages the lifecycle of 'Draft Actions'."""

    async def create_draft(
        self,
        db: AsyncSession,
        conversation_id: str,
        action_type: str,
        service: str,
        payload: dict[str, Any],
        agent_name: str | None = None
    ) -> str:
        """Creates a pending action and notifies the UI via WebSocket."""
        action_id = str(uuid4())
        draft = PendingAction(
            id=action_id,
            conversation_id=conversation_id,
            action_type=action_type,
            service=service,
            proposed_payload=payload,
            status="pending"
        )
        db.add(draft)
        await db.commit()

        # Emit the DRAFT_ACTION canvas event
        # This will render the DraftCard on the UI
        description = self._generate_description(action_type, payload)
        await trace_service.emit_canvas_event(
            conversation_id=conversation_id,
            event_type="DRAFT_ACTION",
            data={
                "action_id": action_id,
                "title": f"Proposed {action_type.replace('_', ' ').title()}",
                "description": description,
                "payload": payload
            },
            agent_name=agent_name
        )

        return action_id

    async def get_action(self, db: AsyncSession, action_id: str) -> PendingAction | None:
        result = await db.execute(select(PendingAction).where(PendingAction.id == action_id))
        return result.scalar_one_or_none()

    async def approve(self, db: AsyncSession, action_id: str) -> dict:
        """Executes the pending action."""
        action = await self.get_action(db, action_id)
        if not action or action.status != "pending":
            return {"error": "Action not found or already processed"}

        # Execute based on service
        result = await self._execute_action(action)
        
        if "error" not in result:
            action.status = "executed"
            await db.commit()
            
            # Emit success to UI
            await trace_service.emit_canvas_event(
                conversation_id=action.conversation_id,
                event_type="IMPACT_UPDATE",
                data={
                    "conflicts_resolved": 1 if "event" in action.action_type.lower() else 0,
                    "tasks_updated": 1 if "page" in action.action_type.lower() else 0,
                    "minutes_saved": 15
                }
            )
        
        return result

    async def reject(self, db: AsyncSession, action_id: str) -> bool:
        action = await self.get_action(db, action_id)
        if action:
            action.status = "rejected"
            await db.commit()
            return True
        return False

    def _generate_description(self, action_type: str, payload: dict) -> str:
        if action_type == "create_event":
            return f"Create a new event: **{payload.get('title')}** from {payload.get('start')} to {payload.get('end')}."
        if action_type == "update_event":
            return f"Update event **{payload.get('title', payload.get('eventId'))}**."
        if action_type == "create_notion_page":
            return f"Create a new Notion page: **{payload.get('title')}**."
        return f"Execute {action_type} with payload {payload}"

    async def _execute_action(self, action: PendingAction) -> dict:
        """Low-level execution of the tool logic."""
        from app.config import get_settings
        settings = get_settings()

        # ── DEMO MODE BYPASS ────────────────────────────────────
        if settings.demo_mode:
            logger.info(f"🎭 DEMO MODE: Simulating execution of {action.action_type}")
            return {"success": True, "id": f"demo_{action.id[:8]}", "mode": "demo"}
        # ── END DEMO MODE BYPASS ───────────────────────────────

        try:
            if action.service == "calendar":
                from app.auth.google_auth import build_calendar_service
                service = build_calendar_service()
                p = action.proposed_payload
                
                if action.action_type == "create_event":
                    body = {
                        'summary': p.get('title'),
                        'description': p.get('description', ''),
                        'start': {'dateTime': p.get('start')},
                        'end': {'dateTime': p.get('end')},
                        'attendees': [{'email': e} for e in p.get('attendees', [])],
                    }
                    res = service.events().insert(calendarId='primary', body=body).execute()
                    return {"success": True, "id": res.get("id")}
                
            elif action.service == "notion":
                from app.auth.notion_auth import get_notion_client
                client = get_notion_client()
                p = action.proposed_payload
                
                if action.action_type == "create_notion_page":
                    from app.config import get_settings
                    db_id = get_settings().notion_database_id
                    res = await client.pages.create(
                        parent={"database_id": db_id},
                        properties={
                            "Name": {"title": [{"text": {"content": p.get("title")}}]},
                            "Status": {"select": {"name": p.get("status", "To Do")}}
                        }
                    )
                    return {"success": True, "id": res.get("id")}
                    
            return {"error": f"Execution logic not implemented for {action.action_type}"}
        except Exception as e:
            logger.error(f"Failed to execute pending action {action.id}: {e}")
            return {"error": str(e)}

pending_actions_service = PendingActionsService()
