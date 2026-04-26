import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent dir to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth.google_auth import build_calendar_service
from app.auth.notion_auth import get_notion_client
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

async def seed_notion():
    try:
        client = get_notion_client()
        db_id = get_settings().notion_database_id
        if not db_id:
            logger.warning("No NOTION_DATABASE_ID found. Skipping Notion seeding.")
            return

        tasks = [
            {"title": "Prepare sprint retrospective notes", "priority": "High", "status": "To Do"},
            {"title": "Review PR #47 — auth refactor", "priority": "High", "status": "In Progress"},
            {"title": "Update deployment runbook", "priority": "Medium", "status": "Backlog"},
            {"title": "Schedule team sync on Q2 roadmap", "priority": "Medium", "status": "To Do"},
            {"title": "Fix CSS bug in sidebar", "priority": "Low", "status": "Backlog"},
            {"title": "Write Q1 performance self-review", "priority": "High", "status": "To Do"},
        ]

        logger.info(f"Seeding {len(tasks)} tasks to Notion database {db_id}...")
        for task in tasks:
            await client.pages.create(
                parent={"database_id": db_id},
                properties={
                    "Name": {"title": [{"text": {"content": task["title"]}}]},
                    "Status": {"status": {"name": task["status"]}},
                    "Priority": {"select": {"name": task["priority"]}},
                }
            )
        logger.info("✅ Notion seeded successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to seed Notion: {e}")

def seed_calendar():
    try:
        service = build_calendar_service()
        if not service:
            logger.warning("No Google Calendar credentials. Skipping Calendar seeding.")
            return

        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # We need overlapping events to trigger conflict detection
        events = [
            {"summary": "Morning Sync", "start": tomorrow.replace(hour=9, minute=0, second=0).isoformat() + "Z", "end": tomorrow.replace(hour=9, minute=45, second=0).isoformat() + "Z"},
            {"summary": "Project Review", "start": tomorrow.replace(hour=9, minute=30, second=0).isoformat() + "Z", "end": tomorrow.replace(hour=10, minute=30, second=0).isoformat() + "Z"}, # Conflict
            {"summary": "Design Workshop", "start": tomorrow.replace(hour=14, minute=0, second=0).isoformat() + "Z", "end": tomorrow.replace(hour=16, minute=0, second=0).isoformat() + "Z"},
            {"summary": "1:1 with Sarah", "start": tomorrow.replace(hour=15, minute=0, second=0).isoformat() + "Z", "end": tomorrow.replace(hour=15, minute=45, second=0).isoformat() + "Z"}, # Conflict
            {"summary": "All Hands", "start": (tomorrow + timedelta(days=1)).replace(hour=11, minute=0, second=0).isoformat() + "Z", "end": (tomorrow + timedelta(days=1)).replace(hour=12, minute=0, second=0).isoformat() + "Z"},
        ]

        logger.info(f"Seeding {len(events)} events to Google Calendar...")
        for event in events:
            body = {
                'summary': event["summary"],
                'start': {'dateTime': event["start"]},
                'end': {'dateTime': event["end"]},
            }
            service.events().insert(calendarId='primary', body=body).execute()
        logger.info("✅ Google Calendar seeded successfully with conflicts.")
    except Exception as e:
        logger.error(f"❌ Failed to seed Calendar: {e}")

async def main():
    logger.info("🎬 Starting Demo Seed Script...")
    seed_calendar()
    await seed_notion()
    logger.info("✨ Seed complete. You are ready for the 90-second demo.")

if __name__ == "__main__":
    asyncio.run(main())
