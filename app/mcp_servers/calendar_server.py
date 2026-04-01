"""Google Calendar MCP Server — exposes Calendar API tools via Model Context Protocol."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ── MCP Server ──────────────────────────────────────────────────
server = Server("google-calendar-mcp")


def _get_calendar_service():
    """Lazy-load Google Calendar API service."""
    from app.auth.google_auth import build_calendar_service
    return build_calendar_service()


# ── Tools ───────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_events",
            description="List calendar events for a given date range. Returns event titles, times, attendees, and descriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format (inclusive)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default 20)",
                        "default": 20,
                    },
                },
                "required": ["start_date"],
            },
        ),
        Tool(
            name="create_event",
            description="Create a new calendar event with title, start/end times, description, and optional attendees.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start": {
                        "type": "string",
                        "description": "Start datetime in ISO 8601 format (e.g., 2026-03-30T14:00:00+05:30)",
                    },
                    "end": {
                        "type": "string",
                        "description": "End datetime in ISO 8601 format",
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description (optional)",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses (optional)",
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location (optional)",
                    },
                },
                "required": ["title", "start", "end"],
            },
        ),
        Tool(
            name="update_event",
            description="Update an existing calendar event by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to update"},
                    "title": {"type": "string", "description": "New event title (optional)"},
                    "start": {"type": "string", "description": "New start datetime (optional)"},
                    "end": {"type": "string", "description": "New end datetime (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                },
                "required": ["event_id"],
            },
        ),
        Tool(
            name="delete_event",
            description="Delete a calendar event by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to delete"},
                },
                "required": ["event_id"],
            },
        ),
        Tool(
            name="find_free_slots",
            description="Find available time windows on a given date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Minimum free slot duration in minutes (default 30)",
                        "default": 30,
                    },
                    "work_start": {
                        "type": "string",
                        "description": "Work day start time HH:MM (default 09:00)",
                        "default": "09:00",
                    },
                    "work_end": {
                        "type": "string",
                        "description": "Work day end time HH:MM (default 18:00)",
                        "default": "18:00",
                    },
                },
                "required": ["date"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from the MCP client (ADK agent)."""
    try:
        service = _get_calendar_service()
        if not service:
            return [TextContent(
                type="text",
                text="❌ Google Calendar is not authenticated. Please run the OAuth setup first."
            )]

        if name == "list_events":
            return await _list_events(service, arguments)
        elif name == "create_event":
            return await _create_event(service, arguments)
        elif name == "update_event":
            return await _update_event(service, arguments)
        elif name == "delete_event":
            return await _delete_event(service, arguments)
        elif name == "find_free_slots":
            return await _find_free_slots(service, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Calendar MCP tool error ({name}): {e}", exc_info=True)
        return [TextContent(type="text", text=f"❌ Error: {str(e)}")]


# ── Tool Implementations ────────────────────────────────────────

async def _list_events(service, args: dict) -> list[TextContent]:
    start_date = args["start_date"]
    end_date = args.get("end_date", start_date)
    max_results = args.get("max_results", 20)

    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    if not events:
        return [TextContent(type="text", text=f"No events found for {start_date} to {end_date}.")]

    lines = [f"📅 Events from {start_date} to {end_date}:\n"]
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        title = event.get("summary", "Untitled")
        event_id = event["id"]
        attendees = [a["email"] for a in event.get("attendees", [])]

        lines.append(f"• **{title}**")
        lines.append(f"  📆 {start} → {end}")
        lines.append(f"  🆔 ID: {event_id}")
        if attendees:
            lines.append(f"  👥 Attendees: {', '.join(attendees)}")
        if event.get("description"):
            lines.append(f"  📝 {event['description'][:100]}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def _create_event(service, args: dict) -> list[TextContent]:
    event_body: dict[str, Any] = {
        "summary": args["title"],
        "start": {"dateTime": args["start"]},
        "end": {"dateTime": args["end"]},
    }

    if args.get("description"):
        event_body["description"] = args["description"]
    if args.get("location"):
        event_body["location"] = args["location"]
    if args.get("attendees"):
        event_body["attendees"] = [{"email": e} for e in args["attendees"]]

    created = service.events().insert(calendarId="primary", body=event_body).execute()

    return [TextContent(
        type="text",
        text=(
            f"✅ Event created successfully!\n"
            f"• Title: {created.get('summary')}\n"
            f"• ID: {created['id']}\n"
            f"• Link: {created.get('htmlLink', 'N/A')}"
        ),
    )]


async def _update_event(service, args: dict) -> list[TextContent]:
    event_id = args["event_id"]

    # Get existing event
    existing = service.events().get(calendarId="primary", eventId=event_id).execute()

    # Apply updates
    if args.get("title"):
        existing["summary"] = args["title"]
    if args.get("start"):
        existing["start"] = {"dateTime": args["start"]}
    if args.get("end"):
        existing["end"] = {"dateTime": args["end"]}
    if args.get("description"):
        existing["description"] = args["description"]

    updated = (
        service.events()
        .update(calendarId="primary", eventId=event_id, body=existing)
        .execute()
    )

    return [TextContent(
        type="text",
        text=f"✅ Event updated: {updated.get('summary')} (ID: {event_id})",
    )]


async def _delete_event(service, args: dict) -> list[TextContent]:
    event_id = args["event_id"]
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return [TextContent(type="text", text=f"✅ Event deleted (ID: {event_id})")]


async def _find_free_slots(service, args: dict) -> list[TextContent]:
    date = args["date"]
    duration = args.get("duration_minutes", 30)
    work_start = args.get("work_start", "09:00")
    work_end = args.get("work_end", "18:00")

    time_min = f"{date}T{work_start}:00Z"
    time_max = f"{date}T{work_end}:00Z"

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    # Calculate free slots
    busy_slots = []
    for event in events:
        start = event["start"].get("dateTime", f"{date}T{work_start}:00Z")
        end = event["end"].get("dateTime", f"{date}T{work_end}:00Z")
        busy_slots.append((start, end))

    # Find gaps between busy slots
    free_slots = []
    current = f"{date}T{work_start}:00Z"

    for busy_start, busy_end in sorted(busy_slots):
        if current < busy_start:
            free_slots.append((current, busy_start))
        if busy_end > current:
            current = busy_end

    end_of_day = f"{date}T{work_end}:00Z"
    if current < end_of_day:
        free_slots.append((current, end_of_day))

    if not free_slots:
        return [TextContent(type="text", text=f"No free slots of {duration}+ minutes found on {date}.")]

    lines = [f"🕐 Free slots on {date} (min {duration} min):\n"]
    for start, end in free_slots:
        lines.append(f"• {start} → {end}")

    return [TextContent(type="text", text="\n".join(lines))]


# ── Entry point for running as a standalone MCP server ──────────

async def main():
    """Run the Google Calendar MCP server via stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
