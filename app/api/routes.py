"""FastAPI REST API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.engine import get_db
from app.database.models import ActionLog, Conversation, ConversationStatus, WorkflowRun, WorkflowRunStatus, PendingAction
from app.services.demo_service import seed_demo_data
from app.services.pending_actions_service import pending_actions_service


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

    # Launch the agent processing in the background
    asyncio.create_task(
        _process_query(conv_id, request.query, request.context, request.session_id)
    )

    return QueryResponse(
        id=conv_id,
        status="pending",
        message="Query submitted — connect to WebSocket for live trace.",
    )


async def _process_query(
    conversation_id: str, query: str, context: dict[str, Any] | None,
    session_id: str | None = None,
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
                query=query,
                conversation_id=conversation_id,
                context=context,
                session_id=session_id,
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


# ── POST /api/v1/demo/seed ──────────────────────────────────────

@router.post("/demo/seed")
async def trigger_demo_seed(
    db: AsyncSession = Depends(get_db),
):
    """Seed the database with a known good state for demo purposes."""
    return await seed_demo_data(db)


# ── POST /api/v1/actions/{id}/approve ───────────────────────────

@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Execute a pending staged action."""
    result = await pending_actions_service.approve(db, action_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── POST /api/v1/actions/{id}/reject ────────────────────────────

@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Reject and dismiss a pending staged action."""
    success = await pending_actions_service.reject(db, action_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"status": "rejected"}


