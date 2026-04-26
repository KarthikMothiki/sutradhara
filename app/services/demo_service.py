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
        "title": "Series A Partner Call — Sequoia",
        "start": _rel(1, 9, 0),
        "end":   _rel(1, 9, 45),
        "attendees": ["Sarah Chen (Sequoia)", "Marcus Okafor (CFO)"],
        "description": "Q2 metrics review. Deck must be updated before this call.",
    },
    {
        "id": "evt_002",
        "title": "Engineering Standup",
        "start": _rel(1, 9, 15),   # ⚠ intentional conflict with evt_001
        "end":   _rel(1, 9, 45),
        "attendees": ["Priya Nair", "Dev Team"],
        "description": "Sprint 14 daily sync.",
    },
    {
        "id": "evt_003",
        "title": "Sprint 14 Retrospective",
        "start": _rel(2, 14, 0),
        "end":   _rel(2, 16, 0),
        "attendees": ["Full Team"],
        "description": "Cover deployment pipeline delays and auth refactor timeline.",
    },
    {
        "id": "evt_004",
        "title": "1:1 — Priya Nair",
        "start": _rel(2, 15, 30),  # ⚠ intentional conflict with evt_003
        "end":   _rel(2, 16, 0),
        "attendees": ["Priya Nair"],
        "description": "",
    },
    {
        "id": "evt_005",
        "title": "Product Strategy Review",
        "start": _rel(3, 10, 0),
        "end":   _rel(3, 12, 0),
        "attendees": ["Sarah Chen", "Karthik Mothiki"],
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
        "eventA": {"id": "evt_001", "title": "Series A Partner Call — Sequoia", "start": _rel(1, 9, 0)},
        "eventB": {"id": "evt_002", "title": "Engineering Standup", "start": _rel(1, 9, 15)},
        "overlap": 30,
    },
    {
        "eventA": {"id": "evt_003", "title": "Sprint 14 Retrospective", "start": _rel(2, 14, 0)},
        "eventB": {"id": "evt_004", "title": "1:1 — Priya Nair", "start": _rel(2, 15, 30)},
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
            title="Calendar Conflict",
            message="Your Sequoia call overlaps with the Engineering Standup tomorrow at 9:00 AM.",
            severity="high",
        ),
        DashboardAlert(
            title="Notion Deadline",
            message="PR #47 Review is due today. Priya is waiting for your feedback.",
            severity="medium",
        ),
        DashboardAlert(
            title="Focus Opportunity",
            message="I found a 2-hour gap on Wednesday afternoon. Suggesting a Deep Work block.",
            severity="low",
        )
    ]
    for alert in alerts:
        db.add(alert)
    
    await db.commit()
    logger.info("✅ Demo data seeded — 5 events, 6 tasks, 3 dashboard alerts.")
    
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
