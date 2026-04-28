"""FastAPI REST API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.engine import get_db
from app.database.models import ActionLog, Conversation, ConversationStatus, WorkflowRun, WorkflowRunStatus, PendingAction, DashboardAlert
from app.services.demo_service import seed_demo_data
from app.services.pending_actions_service import pending_actions_service
from app.services.anticipator_service import anticipator_service
from app.config import get_settings


from app.database.schemas import (
    ConversationResponse,
    ConversationSummary,
    DiagramResponse,
    FeedbackRequest,
    HistoryResponse,
    QueryRequest,
    QueryResponse,
    UndoResponse,
    WorkflowRunResponse,
    ActionLogResponse,
    AppConfig,
)
from app.services.rollback_service import rollback_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["queries"])


# ── POST /api/v1/query ──────────────────────────────────────────

@router.post("/query", response_model=QueryResponse, status_code=202)
async def submit_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a natural-language request to the agent crew."""
    import asyncio

    # Create the conversation record
    conversation = Conversation(
        user_query=request.query,
        status=ConversationStatus.PENDING,
        source="api",
    )
    db.add(conversation)
    await db.flush()
    conv_id = conversation.id

    # Commit BEFORE spawning the background task, otherwise _process_query's
    # separate session won't be able to find this row (race condition).
    await db.commit()

    # Handle multi-modal image uploads (Base64 -> GCS)
    image_uris = []
    if request.images:
        from app.services.cloud_storage import cloud_storage_service
        import base64
        for i, img_b64 in enumerate(request.images):
            try:
                # Basic parsing of data:image/png;base64,xxxx
                if "," in img_b64:
                    header, data = img_b64.split(",", 1)
                    mime_type = header.split(";")[0].split(":")[1]
                else:
                    data = img_b64
                    mime_type = "image/jpeg"
                
                content = base64.b64decode(data)
                uri = await cloud_storage_service.upload_file(content, f"query_image_{i}.jpg", mime_type)
                image_uris.append(uri)
            except Exception as e:
                logger.error(f"Failed to process image {i}: {e}")

    # Set runtime overrides in settings (singleton)
    settings = get_settings()
    settings.runtime_notion_token = request.notion_token
    settings.runtime_notion_db_id = request.notion_database_id

    # Launch the agent processing in the background
    asyncio.create_task(
        _process_query(conv_id, request.query, request.context, request.session_id, image_uris)
    )

    return QueryResponse(
        id=conv_id,
        status="pending",
        message="Query submitted — connect to WebSocket for live trace.",
    )


async def _process_query(
    conversation_id: str, query: str, context: dict[str, Any] | None,
    session_id: str | None = None,
    image_uris: list[str] | None = None,
):
    """Background task that runs the agent crew on a query."""
    from app.database.engine import get_session_factory
    from app.services.trace_service import trace_service

    factory = get_session_factory()
    async with factory() as session:
        try:
            # Update status to RUNNING
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one()
            conv.status = ConversationStatus.RUNNING
            await session.commit()

            # Emit trace start
            await trace_service.emit_agent_start(
                conversation_id, "manager", {"query": query}
            )

            # Save start to workflow run
            wr_start = WorkflowRun(
                conversation_id=conversation_id,
                agent_name="manager",
                status=WorkflowRunStatus.RUNNING,
                input_data={"query": query}
            )
            session.add(wr_start)
            await session.commit()

            # Run the agent crew
            from app.agents.crew import run_agent_query

            agent_result = await run_agent_query(
                session_id=session_id or conversation_id,
                user_id="demo-user", # Default for demo
                query=query,
                conversation_id=conversation_id,
                image_uris=image_uris,
            )

            # Update conversation with result
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one()
            conv.final_response = agent_result.get("response", "No response generated.")
            conv.workflow_diagram = agent_result.get("diagram")
            conv.status = ConversationStatus.COMPLETED
            
            # Save end to workflow run
            wr_end = WorkflowRun(
                conversation_id=conversation_id,
                agent_name="manager",
                status=WorkflowRunStatus.COMPLETED,
                output_data={"response": conv.final_response[:200]}
            )
            session.add(wr_end)
            await session.commit()

            # Emit trace end
            await trace_service.emit_agent_end(
                conversation_id, "manager", {"response": conv.final_response[:200]}
            )

        except Exception as e:
            logger.error(f"Query processing failed: {e}", exc_info=True)
            try:
                result = await session.execute(
                    select(Conversation).where(Conversation.id == conversation_id)
                )
                conv = result.scalar_one()
                conv.status = ConversationStatus.FAILED
                conv.final_response = f"Error: {str(e)}"
                await session.commit()
            except Exception:
                pass

            await trace_service.emit_error(conversation_id, str(e))


# ── GET /api/v1/query/{id} ──────────────────────────────────────

@router.get("/query/{conversation_id}", response_model=ConversationResponse)
async def get_query_result(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the status and result of a conversation."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.workflow_runs),
            selectinload(Conversation.action_logs),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=conv.id,
        user_query=conv.user_query,
        final_response=conv.final_response,
        status=conv.status.value,
        workflow_diagram=conv.workflow_diagram,
        source=conv.source,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        workflow_runs=[
            WorkflowRunResponse(
                id=wr.id,
                agent_name=wr.agent_name,
                tool_called=wr.tool_called,
                input_data=wr.input_data,
                output_data=wr.output_data,
                status=wr.status.value,
                error_message=wr.error_message,
                duration_ms=wr.duration_ms,
                created_at=wr.created_at,
            )
            for wr in conv.workflow_runs
        ],
        action_logs=[
            ActionLogResponse(
                id=al.id,
                action_type=al.action_type,
                service=al.service,
                resource_id=al.resource_id,
                is_reversed=al.is_reversed,
                created_at=al.created_at,
            )
            for al in conv.action_logs
        ],
    )


# ── GET /api/v1/query/{id}/diagram ──────────────────────────────

@router.get("/query/{conversation_id}/diagram", response_model=DiagramResponse)
async def get_workflow_diagram(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the Mermaid workflow diagram for a conversation."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return DiagramResponse(
        conversation_id=conv.id,
        diagram=conv.workflow_diagram,
        message="Diagram available" if conv.workflow_diagram else "No diagram generated",
    )


# ── POST /api/v1/query/{id}/undo ────────────────────────────────

@router.post("/query/{conversation_id}/undo", response_model=UndoResponse)
async def undo_conversation_actions(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Undo all reversible actions from a conversation."""
    # Get undoable actions
    actions = await rollback_service.get_undoable_actions(db, conversation_id)

    if not actions:
        return UndoResponse(
            success=True, undone_actions=0, details=["No actions to undo."]
        )

    details = []
    undone = 0

    for action in actions:
        try:
            # Execute the reverse operation via MCP
            from app.agents.crew import execute_reverse_action

            await execute_reverse_action(action)
            await rollback_service.mark_reversed(db, action.id)
            details.append(
                f"✅ Reversed {action.action_type} on {action.service}/{action.resource_id}"
            )
            undone += 1
        except Exception as e:
            details.append(
                f"❌ Failed to reverse {action.action_type}: {str(e)}"
            )

    await db.commit()

    return UndoResponse(success=undone > 0, undone_actions=undone, details=details)


# ── GET /api/v1/history ─────────────────────────────────────────

@router.get("/history", response_model=HistoryResponse)
async def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List past conversations with pagination."""
    offset = (page - 1) * per_page

    # Get total count
    count_result = await db.execute(select(func.count(Conversation.id)))
    total = count_result.scalar() or 0

    # Get page of conversations
    result = await db.execute(
        select(Conversation)
        .order_by(Conversation.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    conversations = result.scalars().all()

    return HistoryResponse(
        conversations=[
            ConversationSummary(
                id=c.id,
                user_query=c.user_query,
                status=c.status.value,
                source=c.source,
                created_at=c.created_at,
            )
            for c in conversations
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


# ── POST /api/v1/query/{id}/feedback ────────────────────────────

@router.post("/query/{conversation_id}/feedback")
async def submit_feedback(
    conversation_id: str,
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rate a conversation response (stored for future improvement)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # For now, just log the feedback. Can be extended with a Feedback table.
    logger.info(
        f"Feedback for {conversation_id[:8]}…: {request.rating}/5"
        f"{' — ' + request.comment if request.comment else ''}"
    )

    return {"status": "ok", "message": "Thank you for your feedback!"}


# ── Intelligence Suite Endpoints ──────────────────────────────

@router.get("/intelligence/alerts")
async def get_dashboard_alerts(db: AsyncSession = Depends(get_db)):
    """Fetch active proactive alerts from the Anticipator."""
    from app.database.models import DashboardAlert
    result = await db.execute(
        select(DashboardAlert)
        .where(DashboardAlert.is_dismissed == False)
        .order_by(DashboardAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    return [{
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "severity": a.severity,
        "created_at": a.created_at
    } for a in alerts]

@router.post("/intelligence/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Dismiss a dashboard alert."""
    from app.database.models import DashboardAlert
    result = await db.execute(select(DashboardAlert).where(DashboardAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert:
        alert.is_dismissed = True
        await db.commit()
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Alert not found")

@router.post("/intelligence/briefing")
async def trigger_live_briefing(db: AsyncSession = Depends(get_db)):
    """Trigger a live proactive audit and return the latest insights."""
    await anticipator_service.run_proactive_audit()
    # Fetch the alerts generated
    result = await db.execute(
        select(DashboardAlert)
        .order_by(DashboardAlert.created_at.desc())
        .limit(5)
    )
    alerts = result.scalars().all()
    return {
        "status": "ok",
        "alerts": [{
            "title": a.title,
            "message": a.message,
            "severity": a.severity
        } for a in alerts]
    }

@router.get("/demo/seed")
async def seed_demo(db: AsyncSession = Depends(get_db)):
    """Seed the database with rich demo data for the judge's walk-through. Only works in Demo Mode."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Demo seeding is disabled in Live Mode. Switch to Demo Mode in Settings first."
        )
    return await seed_demo_data(db)

# ── Draft-Approval Flow Endpoints ──────────────────────────────

@router.get("/actions/pending")
async def get_pending_actions(
    conversation_id: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """List pending actions that require human approval."""
    from app.database.models import PendingAction
    query = select(PendingAction).where(PendingAction.status == "pending")
    if conversation_id:
        query = query.where(PendingAction.conversation_id == conversation_id)
    
    result = await db.execute(query)
    actions = result.scalars().all()
    
    return [{
        "id": a.id,
        "conversation_id": a.conversation_id,
        "action_type": a.action_type,
        "service": a.service,
        "payload": a.proposed_payload,
        "status": a.status,
        "created_at": a.created_at
    } for a in actions]

@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, db: AsyncSession = Depends(get_db)):
    """Approve and execute a staged action."""
    return await pending_actions_service.approve(db, action_id)

@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, db: AsyncSession = Depends(get_db)):
    """Reject and dismiss a staged action."""
    success = await pending_actions_service.reject(db, action_id)
    if success:
        return {"status": "rejected", "action_id": action_id}
    raise HTTPException(status_code=404, detail="Action not found")

@router.post("/actions/{action_id}/reset")
async def reset_action(action_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a rejected/failed action back to pending so it can be retried."""
    from app.database.models import PendingAction
    from sqlalchemy import select
    result = await db.execute(select(PendingAction).where(PendingAction.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action.status = "pending"
    await db.commit()
    return {"status": "reset", "action_id": action_id}


# ── Configuration Endpoints ─────────────────────────────────────

@router.get("/config", response_model=AppConfig)
async def get_config():
    """Get the current application configuration."""
    settings = get_settings()
    return AppConfig(
        demo_mode=settings.demo_mode,
        notion_token_present=bool(settings.notion_token or settings.runtime_notion_token),
        notion_db_present=bool(settings.notion_database_id or settings.runtime_notion_db_id)
    )

@router.post("/config", response_model=AppConfig)
async def update_config(config: AppConfig):
    """Update the application configuration at runtime."""
    settings = get_settings()
    settings.demo_mode = config.demo_mode
    logger.info(f"⚙️ Runtime config update: DEMO_MODE={settings.demo_mode}")
    return await get_config()
