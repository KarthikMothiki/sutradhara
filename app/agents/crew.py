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
from app.agents.tools.rollback_tools import (
    log_reversible_action,
    undo_conversation_actions,
    undo_last_action,
)
from app.agents.tools.visualization import generate_workflow_diagram
from app.config import get_settings

logger = logging.getLogger(__name__)

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

    # ── Inject current date/time context into all agent instructions ──
    # This allows agents to resolve "tomorrow", "next week", etc. without
    # asking the user for clarification.
    date_context = (
        f"\n\nCURRENT CONTEXT:\n"
        f"• Today is {now.strftime('%A, %B %d, %Y')}\n"
        f"• Current time: {now.strftime('%I:%M %p')}\n"
        f"• Timezone: {tz_display}\n"
        f"• IANA timezone ID: {_iana_tz or 'UTC'}\n\n"
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

    # We need separate agent instances for the manager and the planner
    # because ADK does not allow an agent to have more than one parent.
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
    logger.info("✅ Created calendar_specialist (×2)")

    # ── Notion Specialist (with MCP tools) ──────────────────
    notion_tools = _get_notion_function_tools()

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
    logger.info("✅ Created notion_specialist (×2)")

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
    
    focus_agent_for_manager = Agent(
        name=FOCUS_AGENT_CONFIG["name"],
        model=model,
        description=FOCUS_AGENT_CONFIG["description"],
        instruction=_with_context(FOCUS_AGENT_CONFIG["instruction"]),
        tools=focus_tools,
    )
    logger.info("✅ Created focus_agent")

    # ── Manager (root agent — delegates to all) ─────────────
    manager_agent = Agent(
        name=MANAGER_CONFIG["name"],
        model=model,
        description=MANAGER_CONFIG["description"],
        instruction=_with_context(MANAGER_CONFIG["instruction"]),
        sub_agents=[calendar_agent_for_manager, notion_agent_for_manager, planner_agent, focus_agent_for_manager],
        tools=[
            undo_last_action,
            undo_conversation_actions,
            log_reversible_action,
            generate_workflow_diagram,
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

    def create_event(
        title: str,
        start: str,
        end: str,
        description: str = "",
        attendees: list[str] = [],
        location: str = "",
    ) -> dict:
        """Create a new calendar event.

        Args:
            title: Event title
            start: Start datetime in ISO 8601 format
            end: End datetime in ISO 8601 format
            description: Event description
            attendees: List of attendee email addresses
            location: Event location

        Returns:
            Dict with created event details or error.
        """
        try:
            service = build_calendar_service()
            if not service:
                return {"error": "Google Calendar not authenticated."}

            _tz = _get_system_timezone()

            body: dict[str, Any] = {
                "summary": title,
                "start": {"dateTime": start, "timeZone": _tz},
                "end": {"dateTime": end, "timeZone": _tz},
            }
            if description:
                body["description"] = description
            if location:
                body["location"] = location
            if attendees:
                body["attendees"] = [{"email": e} for e in attendees]

            created = service.events().insert(calendarId="primary", body=body).execute()
            return {
                "id": created["id"],
                "title": created.get("summary"),
                "link": created.get("htmlLink"),
                "status": "created",
            }
        except Exception as e:
            return {"error": str(e)}

    def update_event(
        event_id: str,
        title: str = "",
        start: str = "",
        end: str = "",
        description: str = "",
    ) -> dict:
        """Update an existing calendar event.

        Args:
            event_id: The event ID to update
            title: New title (optional)
            start: New start datetime (optional)
            end: New end datetime (optional)
            description: New description (optional)

        Returns:
            Dict with updated event details or error.
        """
        try:
            service = build_calendar_service()
            if not service:
                return {"error": "Google Calendar not authenticated."}

            existing = service.events().get(calendarId="primary", eventId=event_id).execute()
            if title:
                existing["summary"] = title
            if start:
                existing["start"] = {"dateTime": start}
            if end:
                existing["end"] = {"dateTime": end}
            if description:
                existing["description"] = description

            updated = service.events().update(
                calendarId="primary", eventId=event_id, body=existing
            ).execute()
            return {"id": event_id, "title": updated.get("summary"), "status": "updated"}
        except Exception as e:
            return {"error": str(e)}

    def delete_event(event_id: str) -> dict:
        """Delete a calendar event.

        Args:
            event_id: The event ID to delete

        Returns:
            Confirmation or error.
        """
        try:
            service = build_calendar_service()
            if not service:
                return {"error": "Google Calendar not authenticated."}

            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return {"id": event_id, "status": "deleted"}
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
        return {
            "Authorization": f"Bearer {settings.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def query_notion_database(
        database_id: str = "",
        filter_property: str = "",
        filter_value: str = "",
        page_size: int = 20,
    ) -> dict:
        """Query a Notion database with optional filters.

        Args:
            database_id: Notion database ID (uses default if empty)
            filter_property: Property name to filter on (optional)
            filter_value: Value to filter for (optional)
            page_size: Number of results

        Returns:
            Dict with matching pages.
        """
        try:
            import httpx
            from app.config import get_settings

            settings = get_settings()
            if not settings.notion_token:
                return {"error": "Notion not configured. Set NOTION_TOKEN in .env."}

            db_id = database_id or settings.notion_database_id
            if not db_id:
                return {"error": "No database_id provided and no default configured."}

            body: dict[str, Any] = {"page_size": page_size}

            if filter_property and filter_value:
                body["filter"] = {
                    "property": filter_property,
                    "status": {"equals": filter_value},
                }

            resp = httpx.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=_notion_headers(),
                json=body,
                timeout=15,
            )
            resp.raise_for_status()
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
            return {"error": str(e)}

    def create_notion_page(
        title: str,
        database_id: str = "",
        status: str = "To Do",
        priority: str = "",
        content: str = "",
    ) -> dict:
        """Create a new page/task in Notion.

        Args:
            title: Page title / task name
            database_id: Target database ID (uses default if empty)
            status: Task status (default: "To Do")
            priority: Task priority (optional)
            content: Page body content (optional)

        Returns:
            Dict with created page details.
        """
        try:
            import httpx
            from app.config import get_settings

            settings = get_settings()
            if not settings.notion_token:
                return {"error": "Notion not configured."}

            db_id = database_id or settings.notion_database_id

            properties: dict[str, Any] = {
                "Name": {"title": [{"text": {"content": title}}]},
            }
            if status:
                properties["Status"] = {"status": {"name": status}}
            if priority:
                properties["Priority"] = {"select": {"name": priority}}

            page_data: dict[str, Any] = {
                "parent": {"database_id": db_id},
                "properties": properties,
            }

            if content:
                page_data["children"] = [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": content}}]
                        },
                    }
                ]

            resp = httpx.post(
                "https://api.notion.com/v1/pages",
                headers=_notion_headers(),
                json=page_data,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            return {"id": result["id"], "title": title, "url": result.get("url", ""), "status": "created"}
        except Exception as e:
            return {"error": str(e)}

    def update_notion_page(
        page_id: str,
        status: str = "",
        priority: str = "",
        title: str = "",
    ) -> dict:
        """Update a Notion page's properties.

        Args:
            page_id: The page ID to update
            status: New status value (optional)
            priority: New priority value (optional)
            title: New title (optional)

        Returns:
            Confirmation or error.
        """
        try:
            import httpx

            properties: dict[str, Any] = {}
            if status:
                properties["Status"] = {"status": {"name": status}}
            if priority:
                properties["Priority"] = {"select": {"name": priority}}
            if title:
                properties["Name"] = {"title": [{"text": {"content": title}}]}

            if not properties:
                return {"error": "No properties to update. Provide status, priority, or title."}

            resp = httpx.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=_notion_headers(),
                json={"properties": properties},
                timeout=15,
            )
            resp.raise_for_status()
            return {"id": page_id, "status": "updated"}
        except Exception as e:
            return {"error": str(e)}

    def search_notion(query: str, page_size: int = 10) -> dict:
        """Search across the Notion workspace.

        Args:
            query: Search query text
            page_size: Number of results

        Returns:
            Dict with search results.
        """
        try:
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

    return [query_notion_database, create_notion_page, update_notion_page, search_notion]


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
    context: dict[str, Any] | None = None,
    source: str = "api",
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run a natural-language query through the agent crew.

    This is the main entry point used by API routes and the scheduler.

    Args:
        query: The user's natural language query
        conversation_id: Optional conversation ID for tracking
        context: Optional context dict
        source: Origin of the query (api, scheduler:*, etc.)
        session_id: Persistent session ID for conversation continuity.
                    If provided, reuses the ADK session so the agent
                    retains full chat history across queries.

    Returns:
        Dict with 'response', 'diagram' (if generated), and 'status'.
    """
    runner = _get_runner()
    session_service = _session_service

    user_id = "user"
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

    # Build the user message
    user_content = Content(
        role="user",
        parts=[Part(text=query)],
    )

    # Run the agent
    response_text = ""
    diagram = None

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

            # Check for workflow diagram in session state
            if hasattr(event, "actions") and event.actions:
                for action in event.actions:
                    if hasattr(action, "state_delta") and action.state_delta:
                        if "workflow_diagram" in action.state_delta:
                            diagram = action.state_delta["workflow_diagram"]

    except Exception as e:
        logger.error(f"Agent execution error: {e}", exc_info=True)
        return {
            "response": f"I encountered an error: {str(e)}",
            "status": "failed",
            "diagram": None,
        }

    # Check if the session state has a diagram
    if not diagram:
        try:
            current_session = await session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session.id,
            )
            if current_session and hasattr(current_session, 'state'):
                diagram = current_session.state.get("workflow_diagram")
        except Exception:
            pass

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
