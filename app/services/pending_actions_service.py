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
        logger.info(f"🔍 [APPROVE] Looking for action: {action_id}")
        action = await self.get_action(db, action_id)
        
        if not action:
            logger.error(f"❌ [APPROVE] Action {action_id} NOT FOUND in database.")
            return {"error": "Action not found"}
            
        if action.status != "pending":
            logger.warning(f"⚠️ [APPROVE] Action {action_id} found but status is '{action.status}' (expected 'pending').")
            return {"error": f"Action already processed (status: {action.status})"}

        logger.info(f"✅ [APPROVE] Action {action_id} found and is pending. Proceeding to execution.")

        # Execute based on service
        result = await self._execute_action(action)
        
        if "error" not in result:
            action.status = "executed"
            
            # ── G4: LOG FOR ROLLBACK ─────────────────────────────
            from app.services.rollback_service import rollback_service
            await rollback_service.log_action(
                session=db,
                conversation_id=action.conversation_id,
                action_type=action.action_type,
                service=action.service,
                resource_id=result.get("id"),
                forward_data=action.proposed_payload,
                reverse_data=result.get("reverse_data") # Original state
            )
            # ── END G4 ──────────────────────────────────────────

            await db.commit()
            
            # Emit success to UI
            await trace_service.emit_canvas_event(
                conversation_id=action.conversation_id,
                event_type="IMPACT_UPDATE",
                data={
                    "conflicts_resolved": 1 if any(x in action.action_type.lower() for x in ["event", "calendar"]) else 0,
                    "tasks_updated": 1 if any(x in action.action_type.lower() for x in ["page", "notion"]) else 0,
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
        insight = payload.get("insight", "")
        insight_str = f"\n\n**Proactive Insight:** {insight}" if insight else ""

        if action_type == "create_event":
            return f"Create a new event: **{payload.get('title')}** from {payload.get('start')} to {payload.get('end')}.{insight_str}"
        
        if action_type in ["update_event", "update_calendar"]:
            start_time = payload.get("start", "")
            time_str = f" to **{start_time}**" if start_time else ""
            return f"Reschedule **{payload.get('title', 'this event')}**{time_str} to resolve a conflict.{insight_str}"
            
        if action_type == "create_notion_page":
            return f"Create a new Notion page: **{payload.get('title')}** in your task database.{insight_str}"
            
        if action_type == "update_notion_page":
            updates = []
            if payload.get("status"): updates.append(f"status to **{payload.get('status')}**")
            if payload.get("priority"): updates.append(f"priority to **{payload.get('priority')}**")
            if payload.get("due_date"): updates.append(f"due date to **{payload.get('due_date')}**")
            
            update_str = ", ".join(updates)
            return f"Update **{payload.get('title', 'this task')}**: set {update_str}.{insight_str}"

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
                
                if action.action_type in ["update_event", "update_calendar"]:
                    event_id = p.get("eventId")
                    
                    # ── G4: FETCH CURRENT STATE FOR REVERSE ───────
                    current = service.events().get(calendarId='primary', eventId=event_id).execute()
                    reverse_data = {
                        "summary": current.get("summary"),
                        "start": current.get("start"),
                        "end": current.get("end"),
                        "description": current.get("description")
                    }
                    # ── END G4 ───────────────────────────────────

                    # Patch the event with new times if provided
                    body = {}
                    if p.get("start"): body["start"] = {"dateTime": p.get("start")}
                    if p.get("end"): body["end"] = {"dateTime": p.get("end")}
                    if p.get("title"): body["summary"] = p.get("title")
                    
                    res = service.events().patch(calendarId='primary', eventId=event_id, body=body).execute()
                    return {"success": True, "id": res.get("id"), "reverse_data": reverse_data}
                
            elif action.service == "notion":
                from app.auth.notion_auth import get_notion_client
                client = get_notion_client()
                p = action.proposed_payload
                
                if action.action_type == "create_notion_page":
                    from app.config import get_settings
                    db_id = p.get("database_id") or get_settings().notion_database_id

                    # Build properties — Notion has distinct types for Status vs Select
                    props: dict = {
                        "Name": {"title": [{"text": {"content": p.get("title", "New Task")}}]},
                    }

                    # Status property uses Notion's native "status" type (NOT "select")
                    status_val = p.get("status", "To Do")
                    props["Status"] = {"status": {"name": status_val}}

                    # Priority is typically a Select property in Notion databases
                    if p.get("priority"):
                        props["Priority"] = {"select": {"name": p["priority"]}}

                    # Due Date
                    if p.get("due_date") or p.get("deadline"):
                        date_str = p.get("due_date") or p.get("deadline")
                        props["Due Date"] = {"date": {"start": date_str}}

                    # ── Support for research content/briefing ────────────────
                    children = []
                    if p.get("content"):
                        children.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": p["content"]}}]
                            }
                        })

                    res = await client.pages.create(
                        parent={"database_id": db_id},
                        properties=props,
                        children=children
                    )
                    return {"success": True, "id": res.get("id")}

                if action.action_type == "update_notion_page":
                    page_id = p.get("page_id") or p.get("id")
                    if not page_id:
                        return {"error": "No page_id in payload for update_notion_page"}

                    # ── G4: FETCH CURRENT STATE FOR REVERSE ───────
                    current = await client.pages.retrieve(page_id=page_id)
                    # We only care about the properties we are about to overwrite
                    reverse_data = {}
                    curr_props = current.get("properties", {})
                    for key in ["Status", "Priority", "Name", "Due Date"]:
                        if key in curr_props:
                            reverse_data[key] = curr_props[key]
                    # ── END G4 ───────────────────────────────────

                    props = {}
                    if p.get("status"):
                        props["Status"] = {"status": {"name": p["status"]}}
                    if p.get("priority"):
                        props["Priority"] = {"select": {"name": p["priority"]}}
                    if p.get("due_date"):
                        props["Due Date"] = {"date": {"start": p["due_date"]}}
                    if p.get("title"):
                        props["Name"] = {"title": [{"text": {"content": p["title"]}}]}

                    res = await client.pages.update(page_id=page_id, properties=props)
                    return {"success": True, "id": res.get("id"), "reverse_data": reverse_data}
                    
            return {"error": f"Execution logic not implemented for {action.action_type}"}
        except Exception as e:
            logger.error(f"Failed to execute pending action {action.id}: {e}")
            return {"error": str(e)}

pending_actions_service = PendingActionsService()
