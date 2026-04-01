"""Focus Agent Tools.

This module provides tools for the Focus Agent to query and modify
the new SQLite tables (UserPriorities, FocusBlocks, ProgressLog) as well as
delegate queries to the Calendar and Notion specialists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.engine import get_session_factory
from app.database.models import ActionLog, FocusBlocks, FocusBlockStatus, ProgressLog, UserPriorities

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def read_user_priorities() -> list[dict[str, Any]]:
    """Read all active goals from UserPriorities table sorted by priority_rank."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(UserPriorities).where(UserPriorities.is_active == True).order_by(UserPriorities.priority_rank.asc())
        result = await session.execute(stmt)
        priorities = result.scalars().all()
        return [
            {
                "id": p.id,
                "goal_name": p.goal_name,
                "priority_rank": p.priority_rank,
                "weekly_hours_target": p.weekly_hours_target,
                "total_hours_remaining": p.total_hours_remaining,
                "deadline": p.deadline.isoformat() if p.deadline else None,
                "notes": p.notes,
            }
            for p in priorities
        ]


async def set_user_priority(
    goal_name: str,
    priority_rank: int,
    weekly_hours_target: float,
    total_hours_remaining: float,
    deadline: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Create or update a priority entry.
    
    Args:
        goal_name: The name of the goal
        priority_rank: Priority rank (1 is highest)
        weekly_hours_target: Target hours per week
        total_hours_remaining: Estimated total hours left
        deadline: ISO 8601 datetime string (optional)
        notes: Free text context
    """
    factory = get_session_factory()
    async with factory() as session:
        # Check if rank exists and shift if needed (simple implementation: bump everyone >= priority_rank)
        # For simplicity, we just insert/update for now.
        stmt = select(UserPriorities).where(UserPriorities.goal_name == goal_name)
        result = await session.execute(stmt)
        priority = result.scalars().first()

        parsed_deadline = datetime.fromisoformat(deadline) if deadline else None

        if priority:
            priority.priority_rank = priority_rank
            priority.weekly_hours_target = weekly_hours_target
            priority.total_hours_remaining = total_hours_remaining
            priority.deadline = parsed_deadline
            priority.notes = notes
            priority.is_active = True
        else:
            priority = UserPriorities(
                goal_name=goal_name,
                priority_rank=priority_rank,
                weekly_hours_target=weekly_hours_target,
                total_hours_remaining=total_hours_remaining,
                deadline=parsed_deadline,
                notes=notes,
            )
            session.add(priority)
        
        await session.commit()
        await session.refresh(priority)
        return {"status": "success", "id": priority.id, "goal_name": priority.goal_name}


async def create_focus_block(
    goal_id: int,
    start_datetime: str,
    end_datetime: str,
    notes: str = "",
) -> dict[str, Any]:
    """Create a FocusBlock record with status=proposed."""
    factory = get_session_factory()
    async with factory() as session:
        start_dt = datetime.fromisoformat(start_datetime)
        end_dt = datetime.fromisoformat(end_datetime)
        duration = int((end_dt - start_dt).total_seconds() / 60)

        block = FocusBlocks(
            goal_id=goal_id,
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            duration_minutes=duration,
            status=FocusBlockStatus.PROPOSED,
            notes=notes,
        )
        session.add(block)
        await session.commit()
        await session.refresh(block)
        
        return {
            "id": block.id,
            "goal_id": block.goal_id,
            "status": block.status.value,
            "scheduled_start": start_datetime,
            "scheduled_end": end_datetime,
        }


async def confirm_focus_block(block_id: int, conversation_id: str | None = None) -> dict[str, Any]:
    """Change block status to confirmed and call Calendar Specialist to create event.
    
    Requires conversation_id for Rollback ActionLog support.
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(FocusBlocks).options(selectinload(FocusBlocks.goal)).where(FocusBlocks.id == block_id)
        result = await session.execute(stmt)
        block = result.scalars().first()

        if not block:
            return {"error": f"Block ID {block_id} not found."}
        
        if not block.goal:
            return {"error": f"Goal for Block ID {block_id} not found."}

        # Create calendar event
        from app.agents.crew import _get_calendar_function_tools
        calendar_tools = _get_calendar_function_tools()
        create_event = next(t for t in calendar_tools if t.__name__ == "create_event")
        
        title = f"Focus: {block.goal.goal_name}"
        event_result = create_event(
            title=title,
            start=block.scheduled_start.isoformat(),
            end=block.scheduled_end.isoformat(),
            description=block.notes or "",
        )

        if "error" in event_result:
            return {"error": f"Calendar creation failed: {event_result['error']}"}
        
        calendar_event_id = event_result["id"]
        block.calendar_event_id = calendar_event_id
        block.status = FocusBlockStatus.CONFIRMED

        # Log for Rollback
        if conversation_id:
            action_log = ActionLog(
                conversation_id=conversation_id,
                action_type="create_event",
                service="calendar",
                resource_id=calendar_event_id,
                forward_data={"block_id": block.id, "goal_name": block.goal.goal_name},
                reverse_data={"event_id": calendar_event_id},
            )
            session.add(action_log)

        await session.commit()
        return {"status": "confirmed", "block_id": block.id, "calendar_event_id": calendar_event_id}


async def mark_block_complete(
    block_id: int, hours_completed: float, completion_notes: str = ""
) -> dict[str, Any]:
    """Log progress, update hours_remaining on goal, update pace estimate."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(FocusBlocks).options(selectinload(FocusBlocks.goal)).where(FocusBlocks.id == block_id)
        result = await session.execute(stmt)
        block = result.scalars().first()

        if not block or not block.goal:
            return {"error": "Block or Goal not found"}
        
        block.status = FocusBlockStatus.COMPLETED
        block.actual_end = _utcnow()

        pace_adjustment = hours_completed / (block.duration_minutes / 60.0) if block.duration_minutes > 0 else 1.0

        p_log = ProgressLog(
            focus_block_id=block.id,
            goal_id=block.goal_id,
            hours_completed=hours_completed,
            completion_notes=completion_notes,
            pace_adjustment=pace_adjustment,
        )
        session.add(p_log)
        
        block.goal.total_hours_remaining = max(0.0, block.goal.total_hours_remaining - hours_completed)
        
        await session.commit()
        return {
            "status": "completed",
            "hours_logged": hours_completed,
            "remaining_target": block.goal.total_hours_remaining,
        }


async def read_focus_blocks(date_from: str, date_to: str) -> list[dict[str, Any]]:
    """Read scheduled and completed focus blocks in a date range."""
    factory = get_session_factory()
    async with factory() as session:
        dt_from = datetime.fromisoformat(date_from)
        dt_to = datetime.fromisoformat(date_to)
        stmt = select(FocusBlocks).where(
            FocusBlocks.scheduled_start >= dt_from,
            FocusBlocks.scheduled_end <= dt_to
        )
        result = await session.execute(stmt)
        blocks = result.scalars().all()
        return [
            {
                "id": b.id,
                "goal_id": b.goal_id,
                "status": b.status.value,
                "scheduled_start": b.scheduled_start.isoformat(),
                "scheduled_end": b.scheduled_end.isoformat(),
                "duration_minutes": b.duration_minutes,
            }
            for b in blocks
        ]


async def read_progress_log(goal_id: int) -> list[dict[str, Any]]:
    """Read completion history and pace data for a specific goal."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(ProgressLog).where(ProgressLog.goal_id == goal_id).order_by(ProgressLog.logged_at.desc())
        result = await session.execute(stmt)
        logs = result.scalars().all()
        return [
            {
                "id": p.id,
                "hours_completed": p.hours_completed,
                "completion_notes": p.completion_notes,
                "pace_adjustment": p.pace_adjustment,
                "logged_at": p.logged_at.isoformat(),
            }
            for p in logs
        ]


def list_calendar_events(start_date: str, end_date: str) -> dict[str, Any]:
    from app.agents.crew import _get_calendar_function_tools
    calendar_tools = _get_calendar_function_tools()
    list_ev = next(t for t in calendar_tools if t.__name__ == "list_events")
    return list_ev(start_date, end_date)


def find_free_slots(date: str, min_duration_minutes: int) -> dict[str, Any]:
    from app.agents.crew import _get_calendar_function_tools
    calendar_tools = _get_calendar_function_tools()
    find_fr = next(t for t in calendar_tools if t.__name__ == "find_free_slots")
    return find_fr(date, duration_minutes=min_duration_minutes)


def read_notion_tasks(filter_property: str = "", filter_value: str = "") -> dict[str, Any]:
    from app.agents.crew import _get_notion_function_tools
    notion_tools = _get_notion_function_tools()
    query_notion = next(t for t in notion_tools if t.__name__ == "query_notion_database")
    return query_notion(filter_property=filter_property, filter_value=filter_value)


async def generate_weekly_plan() -> dict[str, Any]:
    """Execute the full planning cycle.
    
    This is a meta-tool available to the Focus Agent to instruct itself,
    but it primarily does the meta-reasoning via the system prompt loop.
    We just return an acknowledgment to let the LLM do the 8-step process.
    """
    return {
        "instruction": "Initiate the 8-step REASONING PROCESS exactly as defined in your system prompt. "
        "Load context via read_user_priorities() and list_calendar_events(), then proceed step-by-step."
    }

def get_focus_agent_tools():
    """Returns the list of tools to provide to the Focus Agent."""
    return [
        read_user_priorities,
        set_user_priority,
        create_focus_block,
        confirm_focus_block,
        mark_block_complete,
        read_focus_blocks,
        read_progress_log,
        list_calendar_events,
        find_free_slots,
        read_notion_tasks,
        generate_weekly_plan,
    ]
