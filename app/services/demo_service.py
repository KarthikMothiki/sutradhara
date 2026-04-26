"""Demo Service — seeds session state with rich, named data for the 90-second demo.

When DEMO_MODE=true, CalendarService and NotionService return this data instead of
making live MCP calls. This is the safety net for the entire sprint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Conversation, ConversationStatus, WorkflowRun, WorkflowRunStatus, DashboardAlert

logger = logging.getLogger(__name__)

# ── Rich Seed Data (from the plan — specific names, real conflicts) ──────────

def _rel(days: int, hour: int, minute: int = 0) -> str:
    """Return an ISO datetime string relative to today."""
    d = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) + timedelta(days=days)
    return d.isoformat()


DEMO_CALENDAR = [
    {
        "id": "evt_001",
        "summary": "Series A Partner Call — Sequoia",
        "start": {"dateTime": _rel(1, 9, 0)},
        "end":   {"dateTime": _rel(1, 9, 45)},
        "attendees": [{"email": "sarah@sequoia.com", "displayName": "Sarah Chen"}, {"email": "marcus@company.com", "displayName": "Marcus Okafor"}],
        "description": "Q2 metrics review. Deck must be updated before this call.",
    },
    {
        "id": "evt_002",
        "summary": "Engineering Standup",
        "start": {"dateTime": _rel(1, 9, 15)},   # ⚠ intentional conflict with evt_001
        "end":   {"dateTime": _rel(1, 9, 45)},
        "attendees": [{"email": "priya@company.com", "displayName": "Priya Nair"}],
        "description": "Sprint 14 daily sync.",
    },
    {
        "id": "evt_003",
        "summary": "Sprint 14 Retrospective",
        "start": {"dateTime": _rel(2, 14, 0)},
        "end":   {"dateTime": _rel(2, 16, 0)},
        "attendees": [],
        "description": "Cover deployment pipeline delays and auth refactor timeline.",
    },
    {
        "id": "evt_004",
        "summary": "1:1 — Priya Nair",
        "start": {"dateTime": _rel(2, 15, 30)},  # ⚠ intentional conflict with evt_003
        "end":   {"dateTime": _rel(2, 16, 0)},
        "attendees": [{"email": "priya@company.com", "displayName": "Priya Nair"}],
        "description": "",
    },
    {
        "id": "evt_005",
        "summary": "Product Strategy Review",
        "start": {"dateTime": _rel(3, 10, 0)},
        "end":   {"dateTime": _rel(3, 12, 0)},
        "attendees": [{"email": "sarah@sequoia.com", "displayName": "Sarah Chen"}],
        "description": "Q3 roadmap alignment with Sarah.",
    },
]

DEMO_NOTION = [
    {
        "id": "task_001",
        "title": "Update Q2 Metrics Deck for Sequoia Call",
        "priority": "high",
        "due": "tomorrow",
        "project": "Series A",
        "notes": "Sarah specifically asked for churn data and CAC/LTV ratio.",
        "status": "To Do",
    },
    {
        "id": "task_002",
        "title": "Review PR #47 — Auth Refactor",
        "priority": "high",
        "due": "today",
        "project": "Engineering",
        "notes": "Priya flagged a security concern in session management.",
        "status": "In Progress",
    },
    {
        "id": "task_003",
        "title": "Prepare Sprint 14 Retrospective Notes",
        "priority": "high",
        "due": "in 2 days",
        "project": "Engineering",
        "notes": "Cover deployment pipeline delays and auth refactor timeline.",
        "status": "To Do",
    },
    {
        "id": "task_004",
        "title": "Write ADR — Caching Strategy for API Layer",
        "priority": "medium",
        "due": "this week",
        "project": "Engineering",
        "notes": "",
        "status": "Backlog",
    },
    {
        "id": "task_005",
        "title": "Schedule Q3 Roadmap Sync with Sarah",
        "priority": "medium",
        "due": "this week",
        "project": "Product",
        "notes": "Sarah mentioned availability on Thursday afternoons.",
        "status": "To Do",
    },
    {
        "id": "task_006",
        "title": "Update Deployment Runbook — v2 Infra",
        "priority": "low",
        "due": "next week",
        "project": "Engineering",
        "notes": "",
        "status": "Backlog",
    },
]

# Conflict pairs (pre-computed for the canvas cards)
DEMO_CONFLICTS = [
    {
        "eventA": {"id": "evt_001", "summary": "Series A Partner Call — Sequoia", "start": {"dateTime": _rel(1, 9, 0)}},
        "eventB": {"id": "evt_002", "summary": "Engineering Standup", "start": {"dateTime": _rel(1, 9, 15)}},
        "overlap": 30,
    },
    {
        "eventA": {"id": "evt_003", "summary": "Sprint 14 Retrospective", "start": {"dateTime": _rel(2, 14, 0)}},
        "eventB": {"id": "evt_004", "summary": "1:1 — Priya Nair", "start": {"dateTime": _rel(2, 15, 30)}},
        "overlap": 30,
    },
]

# Pre-built briefing summary for the morning card
DEMO_BRIEFING = {
    "meetings": 5,
    "tasks": 6,
    "conflicts": 2,
    "high_priority_tasks": 3,
    "insight": (
        "You have a conflict tomorrow at 9:00 AM: your Sequoia call overlaps "
        "with Engineering Standup. The Q2 Metrics Deck is due before that call — "
        "I'd suggest blocking an hour tonight to update it."
    ),
}

# ── Seed Function ────────────────────────────────────────────────────────────

async def seed_demo_data(db: AsyncSession) -> dict:
    """Seed the database with rich demo data and proactive alerts."""
    logger.info("🎬 Seeding demo data with rich named dataset...")
    
    # Clear existing alerts to prevent duplicates in the UI
    from sqlalchemy import delete
    await db.execute(delete(DashboardAlert))
    
    # Add some proactive alerts to the sidebar
    alerts = [
        DashboardAlert(
            title="Focus Opportunity",
            message="I found a 2-hour gap on Wednesday afternoon. Suggesting a Deep Work block.",
            severity="info"
        ),
        DashboardAlert(
            title="Notion Deadline",
            message="PR #47 Review is due today. Priya is waiting for your feedback.",
            severity="warning"
        ),
        DashboardAlert(
            title="Calendar Conflict",
            message="Your Sequoia call overlaps with the Engineering Standup tomorrow at 9:00 AM.",
            severity="error"
        ),
    ]
    db.add_all(alerts)
    
    # ── G2/G4: Scripted Demo Action ────────────────────────
    # Ensure a conversation exists for the demo action to link to
    from app.database.models import Conversation, PendingAction
    from sqlalchemy import select
    
    # Check if demo_session exists
    conv_q = await db.execute(select(Conversation).where(Conversation.id == "demo_session"))
    if not conv_q.scalar_one_or_none():
        db.add(Conversation(
            id="demo_session",
            user_query="Give me my daily briefing",
            status="completed"
        ))
        logger.info("🎬 [SEED] Creating demo_session conversation.")

    # We insert a hardcoded pending action so "Approve" works instantly in the demo
    demo_action = PendingAction(
        id="demo_seq_001",
        conversation_id="demo_session",
        action_type="update_calendar",
        service="google_calendar",
        proposed_payload={"eventId": "evt_002", "start": "10:15"},
        status="pending"
    )
    # Check if exists first to avoid primary key error
    existing_q = await db.execute(select(PendingAction).where(PendingAction.id == "demo_seq_001"))
    existing = existing_q.scalar_one_or_none()
    if not existing:
        db.add(demo_action)
        logger.info("🎬 [SEED] Adding demo_seq_001 to database.")
    else:
        existing.status = "pending" # Reset if it was already used
        logger.info("🎬 [SEED] Resetting existing demo_seq_001 to pending.")

    await db.commit()
    logger.info("✅ Demo data seeded — 5 events, 6 tasks, 3 dashboard alerts, 1 demo action.")
    
    return {
        "status": "seeded",
        "events": len(DEMO_CALENDAR),
        "tasks": len(DEMO_NOTION),
        "conflicts": len(DEMO_CONFLICTS),
        "message": "Demo mode active. Sidebar and tools are primed.",
    }


# ── Accessors (used by calendar/notion tool wrappers) ────────────────────────

def get_demo_calendar() -> list[dict]:
    return DEMO_CALENDAR


def get_demo_notion() -> list[dict]:
    return DEMO_NOTION


def get_demo_conflicts() -> list[dict]:
    return DEMO_CONFLICTS


def get_demo_briefing() -> dict:
    return DEMO_BRIEFING
