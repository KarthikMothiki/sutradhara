"""Demo Service — seeds the database with a 'known good' state for the 90-second demo.

This ensures the demo is repeatable even if the live Google Calendar or Notion 
APIs are empty or unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Conversation, ConversationStatus, WorkflowRun, WorkflowRunStatus

logger = logging.getLogger(__name__)

# ── Demo Data ───────────────────────────────────────────────────

DEMO_CONFLICTS = [
    {"title": "Morning Sync", "start": "09:00", "end": "09:45"},
    {"title": "Project Review", "start": "09:30", "end": "10:30"},  # overlaps with sync
    {"title": "Design Workshop", "start": "14:00", "end": "16:00"},
    {"title": "1:1 with Sarah", "start": "15:00", "end": "15:45"},  # overlaps with workshop
]

DEMO_NOTION_TASKS = [
    {"title": "Prepare sprint retrospective notes", "priority": "high", "due": "tomorrow", "status": "To Do"},
    {"title": "Review PR #47 — auth refactor", "priority": "high", "due": "today", "status": "In Progress"},
    {"title": "Update deployment runbook", "priority": "medium", "due": "in 3 days", "status": "Backlog"},
    {"title": "Schedule team sync on Q2 roadmap", "priority": "medium", "due": "this week", "status": "To Do"},
]

async def seed_demo_data(db: AsyncSession) -> dict:
    """Populates the database with a 'Morning Briefing' conversation.
    
    This allows the judge to see a completed 'Chief of Staff' state immediately.
    """
    logger.info("🎬 Seeding demo data...")
    
    # 1. Create a "Daily Briefing" conversation that happened at 8am today
    now = datetime.now(timezone.utc)
    eight_am = now.replace(hour=8, minute=0, second=0, microsecond=0)
    
    conv_id = str(uuid4())
    briefing_conv = Conversation(
        id=conv_id,
        user_query="Give me my daily briefing.",
        final_response=(
            "Shubh Prabhat! I've analyzed your day. You have a productive morning ahead, "
            "but I've flagged 2 scheduling conflicts. I've also prioritized 3 Notion tasks for you."
        ),
        status=ConversationStatus.COMPLETED,
        source="scheduler:daily_briefing",
        created_at=eight_am,
    )
    
    # Add some mock workflow runs to show "The Loom" in action
    runs = [
        WorkflowRun(
            conversation_id=conv_id,
            agent_name="manager",
            status=WorkflowRunStatus.COMPLETED,
            input_data={"query": "Daily Briefing"},
            output_data={"response": "Decomposing to Scheduler and Planner..."},
            created_at=eight_am + timedelta(seconds=1)
        ),
        WorkflowRun(
            conversation_id=conv_id,
            agent_name="scheduler_specialist",
            tool_called="list_events",
            status=WorkflowRunStatus.COMPLETED,
            output_data={"events": DEMO_CONFLICTS},
            created_at=eight_am + timedelta(seconds=5)
        ),
        WorkflowRun(
            conversation_id=conv_id,
            agent_name="notion_specialist",
            tool_called="query_notion_database",
            status=WorkflowRunStatus.COMPLETED,
            output_data={"pages": DEMO_NOTION_TASKS},
            created_at=eight_am + timedelta(seconds=10)
        )
    ]
    
    db.add(briefing_conv)
    for run in runs:
        db.add(run)
    
    await db.commit()
    logger.info(f"✅ Demo conversation {conv_id[:8]} seeded.")
    
    return {
        "status": "success",
        "conversation_id": conv_id,
        "message": "Demo mode seeded. Refresh the app to see your morning briefing."
    }
