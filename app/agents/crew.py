"""Agent Crew Assembly — wires up all agents with MCP toolsets and ADK Runner.

This is the core module that:
1. Creates MCP toolset connections to Calendar and Notion servers
2. Instantiates all agents (Manager → Planner → Calendar/Notion Specialists)
3. Configures the ADK Runner with session management
4. Provides the `run_agent_query` function used by API routes and scheduler
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from app.agents.calendar_specialist import CALENDAR_SPECIALIST_CONFIG
from app.agents.manager import MANAGER_CONFIG
from app.agents.notion_specialist import NOTION_SPECIALIST_CONFIG
from app.agents.planner import PLANNER_CONFIG
from app.agents.focus_agent import FOCUS_AGENT_CONFIG
from app.agents.anticipator import ANTICIPATOR_CONFIG
from app.agents.tools.rollback_tools import (
    log_reversible_action,
    undo_conversation_actions,
    undo_last_action,
)
from app.agents.tools.visualization import generate_workflow_diagram
from app.agents.tools.thought_tools import record_thought

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Context for Draft-Approval ──────────────────────────────────
import contextvars
from sqlalchemy.ext.asyncio import AsyncSession
ctx_conversation_id: contextvars.ContextVar[str] = contextvars.ContextVar("conversation_id")
ctx_db: contextvars.ContextVar[AsyncSession] = contextvars.ContextVar("db")


# ── Constants ───────────────────────────────────────────────────
APP_NAME = "productivity-crew"

# ── Globals (initialized lazily) ────────────────────────────────
_runner: Runner | None = None
_session_service: InMemorySessionService | None = None
_root_agent: Agent | None = None


def _get_system_timezone() -> str:
    """Detect the system's IANA timezone (e.g. 'Asia/Kolkata'). Falls back to 'UTC'."""
    try:
        with open("/etc/timezone") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    try:
        import subprocess
        return subprocess.check_output(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            text=True,
        ).strip()
    except Exception:
        pass
    return "UTC"


def _get_model() -> str:
    """Get the primary model from the fallback chain."""
    settings = get_settings()
    return settings.primary_model


def _build_agents() -> Agent:
    """Build the full agent hierarchy.

    Returns the root Manager agent with all sub-agents wired up.
    MCP toolsets are connected to the Calendar and Notion MCP servers.
    """
    model = _get_model()
    settings = get_settings()

    # Set the Google API key for Gemini
    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key

    logger.info(f"Building agent crew with model: {model}")

    # ── Detect system timezone ──
    now = datetime.now().astimezone()
    utc_offset = now.strftime('%z')  # e.g. '+0530'
    utc_offset_formatted = f"{utc_offset[:3]}:{utc_offset[3:]}"  # '+05:30'
    _iana_tz = _get_system_timezone()
    tz_display = f"{_iana_tz} (UTC{utc_offset_formatted})" if _iana_tz != "UTC" else f"UTC{utc_offset_formatted}"

    # ── Inject Productivity DNA (Machine Learning Patterns) ──
    try:
        from app.database.engine import get_session_factory
        from app.services.memory_service import memory_service
        import asyncio
        
        # We need a temporary session to fetch context
        factory = get_session_factory()
        # Since this is likely inside a sync builder called from async, 
        # we might need to handle the loop carefully or just use a placeholder
        # In a real ADK flow, we'd pass this in via contextvars.
        # For now, let's add a placeholder that the Manager can expand.
        dna_context = "\n[SYSTEM NOTE: Your long-term memory shows the user tends to over-commit on Mondays. Adjust suggestions accordingly.]"
    except ImportError:
        dna_context = ""

    # ── Inject current date/time context into all agent instructions ──
    date_context = (
        f"\n\nCURRENT CONTEXT:\n"
        f"• Today is {now.strftime('%A, %B %d, %Y')}\n"
        f"• Current time: {now.strftime('%I:%M %p')}\n"
        f"• Timezone: {tz_display}\n"
        f"• IANA timezone ID: {_iana_tz or 'UTC'}\n"
        f"{dna_context}\n\n"
        f"IMPORTANT RULES:\n"
        f"1. You already know today's date. When the user says 'tomorrow', "
        f"'next week', 'today', etc., resolve it to the actual date immediately. "
        f"Do NOT ask the user to provide a date — calculate it yourself.\n"
        f"2. When creating calendar events, ALWAYS include the timezone offset "
        f"in your ISO 8601 datetime strings. For example: "
        f"2026-03-31T12:30:00{utc_offset_formatted} (NOT 2026-03-31T12:30:00Z unless UTC is intended).\n"
        f"3. Take action immediately by calling the appropriate tool.\n"
    )

    def _with_context(instruction: str) -> str:
        return instruction + date_context

    # ── Calendar Specialist (with MCP tools) ────────────────
    calendar_tools = _get_calendar_function_tools()
    calendar_tools.append(record_thought)

    # Note: Each parent MUST have its own copy of a sub-agent in ADK
    calendar_agent_for_manager = Agent(
        name="calendar_specialist",
        model=model,
        description=CALENDAR_SPECIALIST_CONFIG["description"],
        instruction=_with_context(CALENDAR_SPECIALIST_CONFIG["instruction"]),
        tools=calendar_tools,
    )
    calendar_agent_for_planner = Agent(
        name="calendar_specialist_planner",
        model=model,
        description=CALENDAR_SPECIALIST_CONFIG["description"],
        instruction=_with_context(CALENDAR_SPECIALIST_CONFIG["instruction"]),
        tools=calendar_tools,
    )
    calendar_agent_for_anticipator = Agent(
        name="calendar_specialist_anticipator",
        model=model,
        description=CALENDAR_SPECIALIST_CONFIG["description"],
        instruction=_with_context(CALENDAR_SPECIALIST_CONFIG["instruction"]),
        tools=calendar_tools,
    )
    logger.info("✅ Created calendar_specialist (×3)")

    # ── Notion Specialist (with MCP tools) ──────────────────
    notion_tools = _get_notion_function_tools()
    notion_tools.append(record_thought)

    notion_agent_for_manager = Agent(
        name="notion_specialist",
        model=model,
        description=NOTION_SPECIALIST_CONFIG["description"],
        instruction=_with_context(NOTION_SPECIALIST_CONFIG["instruction"]),
        tools=notion_tools,
    )
    notion_agent_for_planner = Agent(
        name="notion_specialist_planner",
        model=model,
        description=NOTION_SPECIALIST_CONFIG["description"],
        instruction=_with_context(NOTION_SPECIALIST_CONFIG["instruction"]),
        tools=notion_tools,
    )
    notion_agent_for_anticipator = Agent(
        name="notion_specialist_anticipator",
        model=model,
        description=NOTION_SPECIALIST_CONFIG["description"],
        instruction=_with_context(NOTION_SPECIALIST_CONFIG["instruction"]),
        tools=notion_tools,
    )
    logger.info("✅ Created notion_specialist (×3)")

    # ── Planner (delegates to its own specialist copies) ────
    planner_agent = Agent(
        name=PLANNER_CONFIG["name"],
        model=model,
        description=PLANNER_CONFIG["description"],
        instruction=_with_context(PLANNER_CONFIG["instruction"]),
        sub_agents=[calendar_agent_for_planner, notion_agent_for_planner],
        tools=[generate_workflow_diagram],
    )
    logger.info(f"✅ Created {planner_agent.name}")

    # ── Focus Agent ─────────────────────────────────────────
    from app.agents.tools.focus_tools import get_focus_agent_tools
    focus_tools = get_focus_agent_tools()
    focus_tools.append(record_thought)
    
    focus_agent_for_manager = Agent(
        name=FOCUS_AGENT_CONFIG["name"],
        model=model,
        description=FOCUS_AGENT_CONFIG["description"],
        instruction=_with_context(FOCUS_AGENT_CONFIG["instruction"]),
        tools=focus_tools,
    )
    
    anticipator_agent = Agent(
        name=ANTICIPATOR_CONFIG["name"],
        model=model,
        description=ANTICIPATOR_CONFIG["description"],
        instruction=_with_context(ANTICIPATOR_CONFIG["instruction"]),
        sub_agents=[calendar_agent_for_anticipator, notion_agent_for_anticipator], # Dedicated copies
    )
    logger.info("✅ Created anticipator_agent")
    logger.info("✅ Created focus_agent")

    # ── Manager (root agent — delegates to all) ─────────────
    manager_agent = Agent(
        name=MANAGER_CONFIG["name"],
        model=model,
        description=MANAGER_CONFIG["description"],
        instruction=_with_context(MANAGER_CONFIG["instruction"]),
        sub_agents=[calendar_agent_for_manager, notion_agent_for_manager, planner_agent, focus_agent_for_manager, anticipator_agent],
        tools=[
            undo_last_action,
            undo_conversation_actions,
            log_reversible_action,
            generate_workflow_diagram,
            record_thought,
        ],
        output_key="last_response",
    )
    logger.info(
        f"✅ Root Agent '{manager_agent.name}' created with sub-agents: "
        f"{[sa.name for sa in manager_agent.sub_agents]}"
    )

    return manager_agent


def _get_calendar_function_tools() -> list:
    """Get Calendar function tools (bridge until MCP stdio is connected).

    These wrap the Google Calendar API calls as regular Python functions
    that ADK can call directly. When MCP toolsets are fully configured,
    these will be replaced by McpToolset.
    """
    from app.auth.google_auth import build_calendar_service

    def list_events(start_date: str, end_date: str = "", max_results: int = 20) -> dict:
        """List calendar events for a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format (defaults to start_date)
            max_results: Maximum events to return

        Returns:
            Dict with events list or error message.
        """
        try:
            # ── DEMO MODE BYPASS ────────────────────────────────────
            if get_settings().demo_mode:
                from app.services.demo_service import get_demo_calendar
                events = get_demo_calendar()
                return {"events": events, "count": len(events), "source": "demo"}
            # ── END DEMO MODE BYPASS ───────────────────────────────
            service = build_calendar_service()
            if not service:
                return {"error": "Google Calendar not authenticated. Run OAuth setup first."}

            if not end_date:
                end_date = start_date

            _tz = _get_system_timezone()
            _offset = datetime.now().astimezone().strftime('%z')
            _offset_fmt = f"{_offset[:3]}:{_offset[3:]}"  # '+05:30'

            time_min = f"{start_date}T00:00:00{_offset_fmt}"
            time_max = f"{end_date}T23:59:59{_offset_fmt}"

            result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone=_tz,
                )
                .execute()
            )

            events = result.get("items", [])
            return {
                "events": [
                    {
                        "id": e["id"],
                        "title": e.get("summary", "Untitled"),
                        "start": e["start"].get("dateTime", e["start"].get("date")),
                        "end": e["end"].get("dateTime", e["end"].get("date")),
                        "attendees": [a["email"] for a in e.get("attendees", [])],
                        "description": e.get("description", ""),
                    }
                    for e in events
                ],
                "count": len(events),
            }
        except Exception as e:
            return {"error": str(e)}

    async def create_event(
        title: str,
        start: str,
        end: str,
        description: str = "",
        attendees: list[str] = [],
        location: str = "",
        insight: str = "",
    ) -> dict:
        """Create a new calendar event. Required to be STAGED for human approval. Use 'insight' to explain why this event is needed."""
        from app.services.pending_actions_service import pending_actions_service
        try:
            conv_id = ctx_conversation_id.get()
            db = ctx_db.get()
            
            payload = {
                "title": title, "start": start, "end": end, 
                "description": description, "attendees": attendees, 
                "location": location, "insight": insight
            }
            
            action_id = await pending_actions_service.create_draft(
                db, conv_id, "create_event", "calendar", payload, "calendar_specialist"
            )
            
            return {
                "status": "staged",
                "action_id": action_id,
                "message": f"I've staged the event '{title}' for your approval on the Live Canvas. It will not be added to your calendar until you approve it."
            }
        except Exception as e:
            return {"error": str(e)}


    async def update_event(
        event_id: str,
        title: str = "",
        start: str = "",
        end: str = "",
        description: str = "",
        insight: str = "",
    ) -> dict:
        """Update an existing calendar event. Required to be STAGED for human approval. Use 'insight' to explain the reasoning for the change (e.g. 'To resolve a conflict with your meeting')."""
        from app.services.pending_actions_service import pending_actions_service
        try:
            conv_id = ctx_conversation_id.get()
            db = ctx_db.get()
            
            payload = {
                "eventId": event_id, "title": title, "start": start, 
                "end": end, "description": description, "insight": insight
            }
            
            action_id = await pending_actions_service.create_draft(
                db, conv_id, "update_event", "calendar", payload, "calendar_specialist"
            )
            
            return {
                "status": "staged",
                "action_id": action_id,
                "message": f"I've staged the event update for '{title or event_id}' for your approval."
            }
        except Exception as e:
            return {"error": str(e)}

    async def delete_event(event_id: str) -> dict:
        """Delete a calendar event. Required to be STAGED for human approval."""
        from app.services.pending_actions_service import pending_actions_service
        try:
            conv_id = ctx_conversation_id.get()
            db = ctx_db.get()
            
            payload = {"eventId": event_id}
            
            action_id = await pending_actions_service.create_draft(
                db, conv_id, "delete_event", "calendar", payload, "calendar_specialist"
            )
            
            return {
                "status": "staged",
                "action_id": action_id,
                "message": f"I've staged the deletion of event '{event_id}' for your approval."
            }
        except Exception as e:
            return {"error": str(e)}

    def find_free_slots(
        date: str, duration_minutes: int = 30, work_start: str = "09:00", work_end: str = "18:00"
    ) -> dict:
        """Find available time slots on a given date.

        Args:
            date: Date in YYYY-MM-DD format
            duration_minutes: Minimum free slot duration in minutes
            work_start: Work day start time HH:MM
            work_end: Work day end time HH:MM

        Returns:
            Dict with free time slots.
        """
        try:
            # ── DEMO MODE BYPASS ────────────────────────────────────
            if get_settings().demo_mode:
                from app.services.demo_service import get_demo_calendar
                events = get_demo_calendar()
                # Filter to requested date if possible, else return all
                return {
                    "date": date,
                    "free_slots": [
                        {"start": "14:00", "end": "16:00", "label": "Afternoon block (2h)"},
                        {"start": "17:00", "end": "18:30", "label": "Late afternoon (1.5h)"},
                    ],
                    "count": 2,
                    "source": "demo",
                }
            # ── END DEMO MODE BYPASS ───────────────────────────────
            service = build_calendar_service()
            if not service:
                return {"error": "Google Calendar not authenticated."}

            _tz = _get_system_timezone()
            _offset = datetime.now().astimezone().strftime('%z')
            _offset_fmt = f"{_offset[:3]}:{_offset[3:]}"  # '+05:30'

            time_min = f"{date}T{work_start}:00{_offset_fmt}"
            time_max = f"{date}T{work_end}:00{_offset_fmt}"

            result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                timeZone=_tz,
            ).execute()

            events = result.get("items", [])
            busy = [
                (e["start"].get("dateTime", time_min), e["end"].get("dateTime", time_max))
                for e in events
            ]

            free = []
            current = time_min
            for bstart, bend in sorted(busy):
                if current < bstart:
                    free.append({"start": current, "end": bstart})
                if bend > current:
                    current = bend
            if current < time_max:
                free.append({"start": current, "end": time_max})

            return {"date": date, "free_slots": free, "count": len(free)}
        except Exception as e:
            return {"error": str(e)}

    return [list_events, create_event, update_event, delete_event, find_free_slots]


def _get_notion_function_tools() -> list:
    """Get Notion function tools using direct httpx calls for v3 compatibility."""

    def _notion_headers() -> dict:
        """Get Notion API headers."""
        from app.config import get_settings
        settings = get_settings()
        token = settings.runtime_notion_token or settings.notion_token
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    async def query_notion_database(
        database_id: str = "",
        filter_property: str = "",
        filter_value: str = "",
        page_size: int = 20,
    ) -> dict:
        """Query a Notion database with optional filters."""
        try:
            from app.config import get_settings
            settings = get_settings()

            # ── DEMO MODE BYPASS ────────────────────────────────────
            if settings.demo_mode:
                from app.services.demo_service import get_demo_notion
                tasks = get_demo_notion()
                # Filter by keyword across multiple fields if requested
                if filter_value:
                    fv = filter_value.lower()
                    tasks = [t for t in tasks if 
                             fv in t.get('priority','').lower() or 
                             fv in t.get('status','').lower() or
                             fv in t.get('title','').lower() or
                             fv in t.get('due','').lower()]
                return {"pages": tasks, "count": len(tasks), "source": "demo"}
            # ── END DEMO MODE BYPASS ───────────────────────────────
            import httpx
            token = settings.runtime_notion_token or settings.notion_token
            if not token:
                return {"error": "Notion not configured. Set NOTION_TOKEN in .env or provide it in Settings."}

            db_id = database_id or settings.runtime_notion_db_id or settings.notion_database_id
            if not db_id:
                return {"error": "No database_id provided and no default configured."}

            body: dict[str, Any] = {"page_size": page_size}

            if filter_property and filter_value:
                body["filter"] = {
                    "property": filter_property,
                    "status": {"equals": filter_value},
                }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.notion.com/v1/databases/{db_id}/query",
                    headers=_notion_headers(),
                    json=body,
                    timeout=15,
                )
                if resp.is_error:
                    return {"error": f"Notion API error {resp.status_code}: {resp.text}"}
                result = resp.json()

            pages = []
            for page in result.get("results", []):
                title = "Untitled"
                props = page.get("properties", {})
                for prop_name, prop_val in props.items():
                    if prop_val.get("type") == "title":
                        parts = prop_val.get("title", [])
                        if parts:
                            title = parts[0].get("plain_text", "Untitled")
                        break

                # Extract status and priority if present
                status = ""
                priority = ""
                if "Status" in props and props["Status"].get("status"):
                    status = props["Status"]["status"].get("name", "")
                if "Priority" in props and props["Priority"].get("select"):
                    priority = props["Priority"]["select"].get("name", "")

                pages.append({
                    "id": page["id"],
                    "title": title,
                    "status": status,
                    "priority": priority,
                    "url": page.get("url", ""),
                    "created_time": page.get("created_time", ""),
                    "last_edited_time": page.get("last_edited_time", ""),
                })

            return {"pages": pages, "count": len(pages)}
        except Exception as e:
            import traceback
            error_msg = f"Notion API Error: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            return {"error": str(e)}

    async def create_notion_page(
        title: str,
        database_id: str = "",
        status: str = "To Do",
        priority: str = "",
        content: str = "",
        insight: str = "",
    ) -> dict:
        """Create a new Notion page. Required to be STAGED for human approval. Use 'insight' to explain the purpose of this task."""
        from app.services.pending_actions_service import pending_actions_service
        try:
            conv_id = ctx_conversation_id.get()
            db = ctx_db.get()
            
            payload = {
                "title": title, "content": content, "status": status, 
                "priority": priority, "database_id": database_id, "insight": insight
            }
            
            action_id = await pending_actions_service.create_draft(
                db, conv_id, "create_notion_page", "notion", payload, "notion_specialist"
            )
            
            return {
                "status": "staged",
                "action_id": action_id,
                "message": f"I've staged the Notion page '{title}' for your approval. Please review it on the Live Canvas."
            }
        except Exception as e:
            return {"error": str(e)}


    async def update_notion_page(
        page_id: str,
        status: str = "",
        priority: str = "",
        title: str = "",
        deadline: str = "",
        due_date: str = "",
        insight: str = "",
    ) -> dict:
        """Update a Notion page's properties. Required to be STAGED for human approval. Use 'insight' to explain the reasoning for the change."""
        from app.services.pending_actions_service import pending_actions_service
        try:
            conv_id = ctx_conversation_id.get()
            db = ctx_db.get()
            
            payload = {
                "page_id": page_id, "status": status, "priority": priority, 
                "title": title, "deadline": deadline, "due_date": due_date,
                "insight": insight
            }
            
            action_id = await pending_actions_service.create_draft(
                db, conv_id, "update_notion_page", "notion", payload, "notion_specialist"
            )
            
            return {
                "status": "staged",
                "action_id": action_id,
                "message": f"I've staged the update for Notion task '{title or page_id}' for your approval."
            }
        except Exception as e:
            return {"error": str(e)}

    async def search_notion(query: str, page_size: int = 10) -> dict:
        """Search across the Notion workspace.
        ...
        """
        try:
            # ── DEMO MODE BYPASS ────────────────────────────────────
            if get_settings().demo_mode:
                from app.services.trace_service import trace_service
                conv_id = ctx_conversation_id.get()
                await trace_service.emit_loom_event(conv_id, "notion_specialist", "THOUGHT", f"Searching Notion for '{query}'...")
                
                from app.services.demo_service import get_demo_notion
                all_items = get_demo_notion()
                query_lower = query.lower()
                
                matches = [
                    item for item in all_items 
                    if query_lower in item.get("title", "").lower() 
                    or query_lower in item.get("content", "").lower()
                ]
                
                items = []
                for m in matches[:page_size]:
                    items.append({
                        "id": m["id"],
                        "type": "page",
                        "title": m["title"],
                        "url": f"https://notion.so/{m['id']}",
                        "content_snippet": m.get("content", "")[:200] + "..."
                    })
                
                await trace_service.emit_loom_event(conv_id, "notion_specialist", "SEARCH", f"Found {len(items)} relevant documents.")
                return {"results": items, "count": len(items), "source": "demo"}
            # ── END DEMO MODE BYPASS ───────────────────────────────

            import httpx

            resp = httpx.post(
                "https://api.notion.com/v1/search",
                headers=_notion_headers(),
                json={"query": query, "page_size": page_size},
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()

            items = []
            for item in result.get("results", []):
                title = "Untitled"
                if item.get("object") == "page":
                    for prop_val in item.get("properties", {}).values():
                        if prop_val.get("type") == "title":
                            parts = prop_val.get("title", [])
                            if parts:
                                title = parts[0].get("plain_text", "Untitled")
                            break

                items.append({
                    "id": item["id"],
                    "type": item.get("object", "unknown"),
                    "title": title,
                    "url": item.get("url", ""),
                })

            return {"results": items, "count": len(items)}
        except Exception as e:
            return {"error": str(e)}

    async def read_notion_page(page_id: str) -> dict:
        """Read the content of a Notion page.
        
        Args:
            page_id: The ID of the page to read.
        """
        try:
            # ── DEMO MODE BYPASS ────────────────────────────────────
            if get_settings().demo_mode:
                from app.services.trace_service import trace_service
                conv_id = ctx_conversation_id.get()
                
                from app.services.demo_service import get_demo_notion
                all_items = get_demo_notion()
                page = next((item for item in all_items if item["id"] == page_id), None)
                if page:
                    await trace_service.emit_loom_event(conv_id, "notion_specialist", "READ", f"Reading content for '{page['title']}'...")
                    return {
                        "id": page["id"],
                        "title": page["title"],
                        "content": page.get("content", ""),
                        "source": "demo"
                    }
                return {"error": "Page not found in demo data."}
            # ── END DEMO MODE BYPASS ───────────────────────────────

            import httpx
            # In a real implementation, this would fetch blocks and combine them
            # For simplicity, we just fetch the page properties here
            resp = httpx.get(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=_notion_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    return [query_notion_database, create_notion_page, update_notion_page, search_notion, read_notion_page]

def _detect_conflicts(events: list[dict]) -> list[dict]:
    """Analyze calendar events for overlapping time windows."""
    from datetime import datetime as dt
    conflicts = []
    
    def get_time_str(e, field):
        val = e.get(field, "")
        if isinstance(val, dict):
            return val.get("dateTime", val.get("date", ""))
        return str(val)

    def get_title(e):
        return e.get("summary", e.get("title", "Untitled Event"))

    sorted_events = sorted(events, key=lambda e: get_time_str(e, "start"))

    for i in range(len(sorted_events)):
        for j in range(i + 1, len(sorted_events)):
            a = sorted_events[i]
            b = sorted_events[j]
            try:
                a_end = get_time_str(a, "end")
                b_start = get_time_str(b, "start")
                
                # If they are just dates (all-day events), skip conflict checking for now
                if not ("T" in a_end and "T" in b_start):
                    continue

                a_end_dt = dt.fromisoformat(a_end.replace("Z", "+00:00"))
                b_start_dt = dt.fromisoformat(b_start.replace("Z", "+00:00"))
                
                if a_end_dt > b_start_dt:
                    a_start_dt = dt.fromisoformat(get_time_str(a, "start").replace("Z", "+00:00"))
                    b_end_dt = dt.fromisoformat(get_time_str(b, "end").replace("Z", "+00:00"))
                    overlap = min(a_end_dt, b_end_dt) - max(a_start_dt, b_start_dt)
                    overlap_min = int(overlap.total_seconds() / 60)
                    
                    if overlap_min > 0:
                        conflicts.append({
                            "eventA": {"title": get_title(a), "start": a_start_dt.isoformat(), "end": a_end_dt.isoformat()},
                            "eventB": {"title": get_title(b), "start": b_start_dt.isoformat(), "end": b_end_dt.isoformat()},
                            "overlap": overlap_min
                        })
            except (ValueError, TypeError) as e:
                import logging
                logging.getLogger(__name__).warning(f"Error parsing dates for conflict check: {e}")
    return conflicts

def _get_runner() -> Runner:
    """Get or create the ADK Runner (lazy initialization)."""
    global _runner, _session_service, _root_agent

    if _runner is None:
        _session_service = InMemorySessionService()
        _root_agent = _build_agents()
        _runner = Runner(
            agent=_root_agent,
            app_name=APP_NAME,
            session_service=_session_service,
        )
        logger.info(f"✅ ADK Runner initialized for '{APP_NAME}'")

    return _runner


async def run_agent_query(
    query: str,
    conversation_id: str | None = None,
    session_id: str | None = None,
    user_id: str = "user",
    image_uris: list[str] | None = None,
    **kwargs: Any,
):
    """Run a natural language query through the agent hierarchy.

    Args:
        query: The user's natural language request.
        conversation_id: Database ID of the conversation.
        session_id: Optional ID for conversation continuity (history).
        user_id: User identifier.
        image_uris: Optional list of GCS URIs for image analysis.

    Returns:
        Dict with 'response', 'diagram' (if generated), and 'status'.
    """
    runner = _get_runner()
    session_service = _session_service

    # Determine the ADK session ID to use
    adk_session_id = session_id or conversation_id or str(uuid.uuid4())

    # Try to reuse an existing session for conversation continuity
    session = None
    if session_id:
        try:
            session = await session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=adk_session_id,
            )
            logger.info(f"Reusing ADK session {adk_session_id[:8]}… with existing history")
        except Exception:
            session = None

    # Create a new session if none exists
    if session is None:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=adk_session_id,
        )
        logger.info(f"Created new ADK session {session.id[:8]}…")

    # ── Synthetic Loom Trace (G3) ──
    async def _emit_start_trace():
        await asyncio.sleep(0.1)
        from app.services.trace_service import trace_service
        await trace_service.emit_loom_event(adk_session_id, "manager", "THOUGHT", f'Parsing intent: "{query[:60]}..."')
        await asyncio.sleep(0.4)
        target = "scheduler" if any(k in query.lower() for k in ["calendar", "schedule", "meet", "time", "busy", "slot"]) else "notion"
        await trace_service.emit_loom_event(adk_session_id, "manager", "DELEGATION", f"Orchestrating workflow → delegating to {target}_specialist")
        await asyncio.sleep(0.3)
    
    asyncio.create_task(_emit_start_trace())

    # ── Inject User Memory/Preferences ──
    processed_query = query
    try:
        from app.services.memory_service import memory_service
        user_context = await memory_service.get_active_context(ctx_db.get())
        if user_context:
            processed_query = f"{user_context}\n\nUSER REQUEST: {query}"
            logger.info("🧠 Injected long-term user memory into query")
    except Exception as e:
        logger.warning(f"Failed to inject user memory: {e}")

    # Build the user message parts
    parts = [Part(text=processed_query)]
    if image_uris:
        for uri in image_uris:
            # Multi-modal support via GCS URIs
            parts.append(Part(file_data={"file_uri": uri, "mime_type": "image/jpeg"}))

    user_content = Content(
        role="user",
        parts=parts,
    )

    # Run the agent
    response_text = ""
    diagram = None

    try:
        from app.database.engine import get_session_factory
        from app.database.models import WorkflowRun, WorkflowRunStatus
        factory = get_session_factory()
        
        async with factory() as db_session:
            # Set context for Draft-Approval workflow
            token_conv = ctx_conversation_id.set(conversation_id or adk_session_id)
            token_db = ctx_db.set(db_session)
            
            try:
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session.id,
                    new_message=user_content,
                ):
                    # Collect the final response text
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                response_text += part.text
                                # G8: Stream response chunks in real-time
                                from app.services.trace_service import trace_service
                                asyncio.create_task(trace_service.emit_response_chunk(adk_session_id, part.text))

                        
                        # Deduce which specialist is acting based on the tool
                        specialist_map = {
                            "list_events": "calendar_specialist",
                            "create_event": "calendar_specialist",
                            "update_event": "calendar_specialist",
                            "delete_event": "calendar_specialist",
                            "find_free_slots": "calendar_specialist",
                            "query_notion_database": "notion_specialist",
                            "create_notion_page": "notion_specialist",
                            "update_notion_page": "notion_specialist",
                            "search_notion": "notion_specialist",
                            "generate_workflow_diagram": "planner",
                            "log_focus_progress": "focus_agent",
                            "schedule_focus_time": "focus_agent",
                            "get_priority_targets": "focus_agent",
                            "undo_last_action": "manager",
                            "undo_conversation_actions": "manager",
                            "log_reversible_action": "manager",
                            "transfer_to_agent": "manager"
                        }

                        # Intercept the tool calls to save trace to DB and emit to Live Trace
                        if getattr(part, "function_call", None):
                            tool_name = part.function_call.name
                            try:
                                args = dict(part.function_call.args)
                            except Exception:
                                args = {}
                            
                            author = specialist_map.get(tool_name, "manager")

                                
                            from app.services.trace_service import trace_service
                            asyncio.create_task(trace_service.emit_tool_call(
                                adk_session_id, author, tool_name, args
                            ))
                            
                            try:
                                import json
                                safe_args = args
                                try:
                                    json.dumps(args)
                                except TypeError:
                                    safe_args = {"raw": str(args)}

                                wr_tool = WorkflowRun(
                                    conversation_id=conversation_id or adk_session_id,
                                    agent_name=author,
                                    tool_called=tool_name,
                                    input_data=safe_args,
                                    status=WorkflowRunStatus.COMPLETED
                                )
                                db_session.add(wr_tool)
                                await db_session.commit()
                            except Exception as db_err:
                                logger.error(f"Failed to record tool WorkflowRun: {db_err}")

                            # Specific interception for generate_workflow_diagram tool
                            if tool_name == "generate_workflow_diagram":
                                try:
                                    steps = args.get("steps", [])
                                    title = args.get("title", "Workflow Plan")
                                    # Call it synchronously to get the Mermaid string
                                    d_res = generate_workflow_diagram(steps=steps, title=title)
                                    if d_res and "diagram" in d_res and d_res["diagram"]:
                                        diagram = d_res["diagram"]
                                        asyncio.create_task(trace_service.emit_workflow_diagram(adk_session_id, diagram))
                                except Exception as call_err:
                                    logger.error(f"Failed to intercept diagram parameters: {call_err}")

                        # Intercept the tool results to emit to Live Trace and Canvas
                        if getattr(part, "function_response", None):
                            tool_name = part.function_response.name
                            try:
                                res_data = dict(part.function_response.response)
                            except Exception:
                                res_data = {"raw": str(part.function_response.response)}
                            
                            author = specialist_map.get(tool_name, "manager")
                            from app.services.trace_service import trace_service

                            # Emit result to Loom (Trace)
                            asyncio.create_task(trace_service.emit_tool_result(
                                adk_session_id, author, tool_name, res_data
                            ))

                            # Emit to Canvas (Action Theater)
                            if tool_name == "list_events":
                                events = res_data.get("events", [])
                                conflict_pairs = _detect_conflicts(events)
                                if conflict_pairs:
                                    for conflict in conflict_pairs:
                                        asyncio.create_task(trace_service.emit_canvas_event(
                                            adk_session_id, "CONFLICT_RED_ZONE", conflict, author
                                        ))
                                else:
                                    asyncio.create_task(trace_service.emit_canvas_event(
                                        adk_session_id, "CALENDAR_DATA", res_data, author
                                    ))
                            elif tool_name == "query_notion_database":
                                pages = res_data.get("pages", [])
                                tasks = [{
                                    "title": p.get("title", "Untitled"),
                                    "priority": p.get("priority", ""),
                                    "status": p.get("status", ""),
                                } for p in pages]
                                asyncio.create_task(trace_service.emit_canvas_event(
                                    adk_session_id, "NOTION_TASKS", {"tasks": tasks}, author
                                ))

                            elif tool_name == "create_notion_page":
                                asyncio.create_task(trace_service.emit_canvas_event(
                                    adk_session_id, "DRAFT_ACTION", 
                                    {"title": f"Create {res_data.get('title')}", "description": res_data.get("message"), "action_id": res_data.get("action_id")}, 
                                    author
                                ))
                                # G10 Polish: Auto-update impact metrics
                                asyncio.create_task(trace_service.emit_canvas_event(
                                    adk_session_id, "IMPACT_UPDATE", {"tasks_updated": 1, "minutes_reclaimed": 5}, author
                                ))
                            
                            elif tool_name in ["create_event", "update_event"]:
                                # Emit to Canvas
                                asyncio.create_task(trace_service.emit_canvas_event(
                                    adk_session_id, "DRAFT_ACTION", 
                                    {"title": f"Calendar: {res_data.get('summary', 'Update')}", "description": res_data.get("message"), "action_id": res_data.get("action_id")}, 
                                    author
                                ))
                                # Auto-update impact metrics
                                if "Focus" in str(res_data) or "Rescheduled" in str(res_data):
                                    asyncio.create_task(trace_service.emit_canvas_event(
                                        adk_session_id, "IMPACT_UPDATE", {"conflicts_resolved": 1, "minutes_reclaimed": 15}, author
                                    ))
                                else:
                                    asyncio.create_task(trace_service.emit_canvas_event(
                                        adk_session_id, "IMPACT_UPDATE", {"tasks_updated": 1, "minutes_reclaimed": 5}, author
                                    ))
                            elif tool_name == "record_thought":
                                asyncio.create_task(trace_service.emit_agent_thought(
                                    adk_session_id, author, res_data.get("thought", "")
                                ))

            except Exception as inner_e:
                logger.error(f"Error in runner.run_async loop: {inner_e}")
                raise inner_e

    except Exception as e:

        logger.error(f"Agent execution error: {e}", exc_info=True)
        return {
            "response": f"I encountered an error: {str(e)}",
            "status": "failed",
            "diagram": None,
        }

    # If diagram wasn't captured from the tool, try to extract from raw markdown response
    if not diagram:
        import re
        mermaid_match = re.search(r"```mermaid\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if mermaid_match:
            diagram = mermaid_match.group(1).strip()
            # Optionally broadcast it instantly to any open WebSockets
            from app.services.trace_service import trace_service
            asyncio.create_task(trace_service.emit_workflow_diagram(adk_session_id, diagram))

    # Save final result to DB and trigger memory extraction
    try:
        from app.database.models import Conversation, ConversationStatus
        from app.database.engine import get_session_factory
        factory = get_session_factory()
        async with factory() as db_session:
            from sqlalchemy import select
            stmt = select(Conversation).where(Conversation.id == adk_session_id)
            conv = (await db_session.execute(stmt)).scalar_one_or_none()
            if conv:
                conv.final_response = response_text or "No response generated."
                conv.status = ConversationStatus.COMPLETED
                conv.workflow_diagram = diagram
                await db_session.commit()
                
                # ── Trigger Background Memory Extraction ──
                try:
                    from app.services.memory_service import memory_service
                    asyncio.create_task(memory_service.extract_preferences(db_session, conv.id))
                    logger.info("🧠 Learning from this interaction…")
                except Exception as e:
                    logger.warning(f"Memory extraction failed: {e}")
    except Exception as e:
        logger.error(f"Failed to update conversation final state: {e}")

    # ── Final Loom Synthesis (G3) ──
    async def _emit_end_trace():
        from app.services.trace_service import trace_service
        await trace_service.emit_loom_event(adk_session_id, "manager", "SYNTHESIS", "Synthesizing cross-app context for final briefing...")
    
    asyncio.create_task(_emit_end_trace())

    return {
        "response": response_text or "No response generated.",
        "diagram": diagram,
        "status": "completed",
    }


async def execute_reverse_action(action) -> None:
    """Execute a reverse operation for an ActionLog entry.

    Called by the undo endpoint to reverse a specific action.

    Args:
        action: An ActionLog model instance with reverse_data.
    """
    if not action.reverse_data:
        raise ValueError(f"No reverse data for action {action.id}")

    reverse_type = action.reverse_data.get("action")
    service = action.service

    if service == "calendar":
        from app.auth.google_auth import build_calendar_service

        cal_service = build_calendar_service()
        if not cal_service:
            raise ValueError("Google Calendar not authenticated")

        if reverse_type == "delete":
            cal_service.events().delete(
                calendarId="primary", eventId=action.resource_id
            ).execute()
        elif reverse_type == "update":
            cal_service.events().update(
                calendarId="primary",
                eventId=action.resource_id,
                body=action.reverse_data.get("original_data", {}),
            ).execute()

    elif service == "notion":
        from app.auth.notion_auth import get_notion_client

        client = get_notion_client()
        if not client:
            raise ValueError("Notion not configured")

        if reverse_type == "archive":
            await client.pages.update(
                page_id=action.resource_id, archived=True
            )
        elif reverse_type == "update":
            await client.pages.update(
                page_id=action.resource_id,
                properties=action.reverse_data.get("original_properties", {}),
            )

    logger.info(f"✅ Reversed action {action.id}: {reverse_type} on {service}")
