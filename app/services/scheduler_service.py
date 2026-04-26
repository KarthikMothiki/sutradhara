"""Tier 3 — Proactive/autonomous scheduled jobs using APScheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Scheduler Singleton ─────────────────────────────────────────
scheduler = AsyncIOScheduler()

async def proactive_audit_job():
    """Trigger the Anticipator for a full system health check."""
    from app.services.anticipator_service import anticipator_service
    await anticipator_service.run_proactive_audit()


async def daily_briefing_job():
    """Compile today's calendar events + overdue Notion tasks into a summary.

    Runs every morning at the configured time. Invokes the Manager agent
    with a synthetic query and stores the result as a conversation.
    """
    logger.info("🌅 Running Daily Briefing job…")
    try:
        from app.services.anticipator_service import anticipator_service
        await anticipator_service.run_proactive_audit()
        
        from app.agents.crew import run_agent_query  # lazy import to avoid circular

        result = await run_agent_query(
            query=(
                "Give me my daily briefing: "
                "1. List all my meetings and events for today "
                "2. Show any overdue or high-priority tasks from Notion "
                "3. Summarize any schedule conflicts "
                "4. Suggest the top 3 things I should focus on today"
            ),
            source="scheduler:daily_briefing",
        )
        logger.info(f"Daily briefing completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Daily briefing failed: {e}", exc_info=True)


async def meeting_prep_job():
    """15 min before each meeting, surface related Notion pages.

    Runs every 15 minutes. Checks for upcoming meetings in the next 15-30 min
    window and generates prep summaries.
    """
    logger.info("📋 Running Meeting Prep job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Check my calendar for any meetings starting in the next 15-30 minutes. "
                "For each upcoming meeting: "
                "1. Find related Notion pages by matching the meeting title/topic "
                "2. Create a 3-bullet preparation summary "
                "3. List any relevant tasks or action items"
            ),
            source="scheduler:meeting_prep",
        )
        logger.info(f"Meeting prep completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Meeting prep failed: {e}", exc_info=True)


async def weekly_review_job():
    """Friday evening: summarize the week and suggest next week's priorities."""
    logger.info("📊 Running Weekly Review job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Generate my weekly review: "
                "1. List all meetings attended this week "
                "2. List all Notion tasks completed this week "
                "3. List any tasks that are overdue or carried over "
                "4. Identify patterns (busiest day, most productive day) "
                "5. Suggest top 5 priorities for next week"
            ),
            source="scheduler:weekly_review",
        )
        logger.info(f"Weekly review completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Weekly review failed: {e}", exc_info=True)


async def conflict_detection_job():
    """Monitor calendar for double-bookings and alert the user."""
    logger.info("⚠️ Running Conflict Detection job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Check my calendar for the next 7 days and identify: "
                "1. Any overlapping/double-booked time slots "
                "2. Back-to-back meetings with no break "
                "3. Meetings that conflict with focus time blocks "
                "Report any conflicts found with suggestions for resolution."
            ),
            source="scheduler:conflict_detection",
        )
        logger.info(f"Conflict detection completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Conflict detection failed: {e}", exc_info=True)


async def smart_rescheduling_check_job():
    """Check if any deep-work blocks should be rescheduled based on context."""
    logger.info("🧠 Running Smart Rescheduling check…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Analyze my schedule for today and tomorrow: "
                "1. Identify any 'Focus Time' or 'Deep Work' blocks "
                "2. Check if they conflict with newly added meetings "
                "3. If there are conflicts, suggest alternative time slots "
                "4. Report what was found (don't make changes automatically)"
            ),
            source="scheduler:smart_reschedule",
        )
        logger.info(
            f"Smart rescheduling check completed: {result.get('status', 'unknown')}"
        )
    except Exception as e:
        logger.error(f"Smart rescheduling check failed: {e}", exc_info=True)


async def focus_weekly_plan_job():
    """Monday morning: Instruct Focus Agent to generate a weekly plan."""
    logger.info("📅 Running Focus Weekly Plan job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Generate my weekly focus plan. Read my priorities, read my calendar, compute "
                "the deadline math, find free slots, and propose focus blocks. "
                "Do NOT create any blocks or calendar events until I confirm."
            ),
            source="scheduler:focus_weekly_plan",
        )
        logger.info(f"Focus weekly plan completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Focus weekly plan failed: {e}", exc_info=True)


async def focus_weekly_review_job():
    """Friday evening: Instruct Focus Agent to review the week."""
    logger.info("📈 Running Focus Weekly Review job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Run a weekly review of my focus blocks: compare planned vs actual focus blocks, "
                "calculate hours completed per goal, update pace estimates, and flag any goals "
                "that fell behind and need catch-up next week."
            ),
            source="scheduler:focus_weekly_review",
        )
        logger.info(f"Focus weekly review completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Focus weekly review failed: {e}", exc_info=True)


async def focus_deadline_alert_job():
    """Daily check for upcoming deadlines within 48 hours."""
    logger.info("🚨 Running Focus Deadline Alert job…")
    try:
        from app.agents.crew import run_agent_query

        result = await run_agent_query(
            query=(
                "Check all my active priorities for deadlines within the next 48 hours. "
                "If any are at risk, alert me with exact hours remaining, hours needed per day "
                "to finish, and a proposed intensive schedule."
            ),
            source="scheduler:focus_deadline_alert",
        )
        logger.info(f"Focus deadline alert completed: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Focus deadline alert failed: {e}", exc_info=True)


def setup_scheduler() -> None:
    """Configure and start all scheduled jobs based on settings."""
    settings = get_settings()

    if not settings.scheduler_enabled:
        logger.info("Scheduler is disabled via settings.")
        return

    # Parse briefing time
    try:
        hour, minute = map(int, settings.daily_briefing_time.split(":"))
    except ValueError:
        hour, minute = 8, 0

    # Parse weekly review time
    try:
        review_hour, review_minute = map(int, settings.weekly_review_time.split(":"))
    except ValueError:
        review_hour, review_minute = 18, 0

    # ── Job 1: Daily Briefing ───────────────────────────────
    scheduler.add_job(
        daily_briefing_job,
        "cron",
        hour=hour,
        minute=minute,
        id="daily_briefing",
        name="Daily Briefing",
        replace_existing=True,
    )

    # ── Job 2: Meeting Prep (every 15 min) ──────────────────
    scheduler.add_job(
        meeting_prep_job,
        "interval",
        minutes=15,
        id="meeting_prep",
        name="Meeting Prep",
        replace_existing=True,
    )

    # ── Job 3: Weekly Review ────────────────────────────────
    scheduler.add_job(
        weekly_review_job,
        "cron",
        day_of_week=settings.weekly_review_day[:3].lower(),
        hour=review_hour,
        minute=review_minute,
        id="weekly_review",
        name="Weekly Review",
        replace_existing=True,
    )

    # ── Job 4: Conflict Detection (every 30 min) ───────────
    scheduler.add_job(
        conflict_detection_job,
        "interval",
        minutes=30,
        id="conflict_detection",
        name="Conflict Detection",
        replace_existing=True,
    )

    # ── Job 5: Smart Rescheduling (every hour) ─────────────
    scheduler.add_job(
        smart_rescheduling_check_job,
        "interval",
        hours=1,
        id="smart_rescheduling",
        name="Smart Rescheduling Check",
        replace_existing=True,
    )

    # ── Focus Agent Jobs ───────────────────────────────────
    scheduler.add_job(
        focus_weekly_plan_job,
        "cron",
        day_of_week="mon",
        hour=7,
        minute=0,
        id="focus_weekly_plan",
        name="Focus Weekly Plan",
        replace_existing=True,
    )

    scheduler.add_job(
        focus_weekly_review_job,
        "cron",
        day_of_week="fri",
        hour=18,
        minute=0,
        id="focus_weekly_review",
        name="Focus Weekly Review",
        replace_existing=True,
    )

    scheduler.add_job(
        focus_deadline_alert_job,
        "cron",
        hour=9,  # Check every morning at 9am
        minute=0,
        id="focus_deadline_alert",
        name="Focus Deadline Alert",
        replace_existing=True,
    )

    # ── Job 6: Proactive Audit (every 4 hours) ─────────────
    scheduler.add_job(
        proactive_audit_job,
        "interval",
        hours=4,
        id="proactive_audit",
        name="Proactive System Audit",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "📅 Scheduler started with 6 jobs: "
        f"Daily Briefing ({hour:02d}:{minute:02d}), "
        f"Meeting Prep (every 15 min), "
        f"Weekly Review ({settings.weekly_review_day} {review_hour:02d}:{review_minute:02d}), "
        f"Conflict Detection (every 30 min), "
        f"Smart Rescheduling (every hour), "
        f"Proactive Audit (every 4 hours)"
    )


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
