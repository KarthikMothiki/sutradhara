"""Notion MCP Server — exposes Notion API tools via Model Context Protocol."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ── MCP Server ──────────────────────────────────────────────────
server = Server("notion-mcp")


def _get_notion_client():
    """Lazy-load Notion async client."""
    from app.auth.notion_auth import get_notion_client
    return get_notion_client()


# ── Tools ───────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_database",
            description="Search and filter a Notion database. Returns matching pages with their properties.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "Notion database ID (uses default if not specified)",
                    },
                    "filter": {
                        "type": "object",
                        "description": "Notion filter object (optional). Example: {\"property\": \"Status\", \"status\": {\"equals\": \"In Progress\"}}",
                    },
                    "sorts": {
                        "type": "array",
                        "description": "Notion sorts array (optional)",
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Number of results (default 20, max 100)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="create_page",
            description="Create a new page or task in a Notion database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "Target database ID (uses default if not specified)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Page title / task name",
                    },
                    "properties": {
                        "type": "object",
                        "description": "Additional properties as key-value pairs. Example: {\"Status\": \"To Do\", \"Priority\": \"High\"}",
                    },
                    "content": {
                        "type": "string",
                        "description": "Page body content as markdown (optional)",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="update_page",
            description="Update properties of an existing Notion page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The Notion page ID to update",
                    },
                    "properties": {
                        "type": "object",
                        "description": "Properties to update as key-value pairs",
                    },
                },
                "required": ["page_id", "properties"],
            },
        ),
        Tool(
            name="get_page_content",
            description="Read the full content (blocks) of a Notion page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The Notion page ID to read",
                    },
                },
                "required": ["page_id"],
            },
        ),
        Tool(
            name="search",
            description="Full-text search across the entire Notion workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text",
                    },
                    "filter_type": {
                        "type": "string",
                        "description": "Filter by object type: 'page' or 'database' (optional)",
                        "enum": ["page", "database"],
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Number of results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from the MCP client (ADK agent)."""
    try:
        client = _get_notion_client()
        if not client:
            return [TextContent(
                type="text",
                text="❌ Notion is not configured. Please set NOTION_TOKEN in .env."
            )]

        if name == "query_database":
            return await _query_database(client, arguments)
        elif name == "create_page":
            return await _create_page(client, arguments)
        elif name == "update_page":
            return await _update_page(client, arguments)
        elif name == "get_page_content":
            return await _get_page_content(client, arguments)
        elif name == "search":
            return await _search(client, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Notion MCP tool error ({name}): {e}", exc_info=True)
        return [TextContent(type="text", text=f"❌ Error: {str(e)}")]


# ── Tool Implementations ────────────────────────────────────────

async def _query_database(client, args: dict) -> list[TextContent]:
    from app.config import get_settings
    settings = get_settings()

    database_id = args.get("database_id", settings.notion_database_id)
    if not database_id:
        return [TextContent(type="text", text="❌ No database_id provided and no default configured.")]

    query_params: dict[str, Any] = {"database_id": database_id}
    if args.get("filter"):
        query_params["filter"] = args["filter"]
    if args.get("sorts"):
        query_params["sorts"] = args["sorts"]
    query_params["page_size"] = args.get("page_size", 20)

    result = await client.databases.query(**query_params)
    pages = result.get("results", [])

    if not pages:
        return [TextContent(type="text", text="No results found in the database.")]

    lines = [f"📝 Found {len(pages)} results:\n"]
    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})

        # Extract title
        title = "Untitled"
        for prop_name, prop_val in props.items():
            if prop_val.get("type") == "title":
                title_parts = prop_val.get("title", [])
                if title_parts:
                    title = title_parts[0].get("plain_text", "Untitled")
                break

        # Extract key properties
        prop_summary = []
        for prop_name, prop_val in props.items():
            ptype = prop_val.get("type", "")
            if ptype == "status":
                status = prop_val.get("status", {})
                if status:
                    prop_summary.append(f"{prop_name}: {status.get('name', '?')}")
            elif ptype == "select":
                sel = prop_val.get("select", {})
                if sel:
                    prop_summary.append(f"{prop_name}: {sel.get('name', '?')}")
            elif ptype == "date":
                date = prop_val.get("date", {})
                if date:
                    prop_summary.append(f"{prop_name}: {date.get('start', '?')}")
            elif ptype == "created_time":
                ct = prop_val.get("created_time", "")
                if ct:
                    prop_summary.append(f"{prop_name}: {ct}")
            elif ptype == "last_edited_time":
                lt = prop_val.get("last_edited_time", "")
                if lt:
                    prop_summary.append(f"{prop_name}: {lt}")

        lines.append(f"• **{title}**")
        lines.append(f"  🆔 ID: {page_id}")
        if prop_summary:
            lines.append(f"  📋 {' | '.join(prop_summary)}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def _create_page(client, args: dict) -> list[TextContent]:
    from app.config import get_settings
    settings = get_settings()

    database_id = args.get("database_id", settings.notion_database_id)
    title = args["title"]

    # Build properties
    properties: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": title}}]},
    }

    # Add extra properties if provided
    if args.get("properties"):
        for key, value in args["properties"].items():
            if isinstance(value, str):
                # Assume it's a status or select property
                properties[key] = {"status": {"name": value}}

    page_data: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }

    # Add content blocks if provided
    if args.get("content"):
        page_data["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": args["content"]}}]
                },
            }
        ]

    result = await client.pages.create(**page_data)

    return [TextContent(
        type="text",
        text=(
            f"✅ Page created successfully!\n"
            f"• Title: {title}\n"
            f"• ID: {result['id']}\n"
            f"• URL: {result.get('url', 'N/A')}"
        ),
    )]


async def _update_page(client, args: dict) -> list[TextContent]:
    page_id = args["page_id"]
    updates = args["properties"]

    # Build property updates
    properties: dict[str, Any] = {}
    for key, value in updates.items():
        if isinstance(value, str):
            properties[key] = {"status": {"name": value}}
        elif isinstance(value, dict):
            properties[key] = value

    result = await client.pages.update(page_id=page_id, properties=properties)

    return [TextContent(
        type="text",
        text=f"✅ Page updated (ID: {page_id})",
    )]


async def _get_page_content(client, args: dict) -> list[TextContent]:
    page_id = args["page_id"]

    # Get page properties
    page = await client.pages.retrieve(page_id=page_id)

    # Get page blocks (content)
    blocks = await client.blocks.children.list(block_id=page_id)

    lines = [f"📄 Page content (ID: {page_id}):\n"]

    # Extract title
    for prop_name, prop_val in page.get("properties", {}).items():
        if prop_val.get("type") == "title":
            title_parts = prop_val.get("title", [])
            if title_parts:
                lines.append(f"# {title_parts[0].get('plain_text', 'Untitled')}\n")
            break

    # Extract block content
    for block in blocks.get("results", []):
        block_type = block.get("type", "")
        if block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text = " ".join(rt.get("plain_text", "") for rt in rich_text)
            if text:
                lines.append(text)
        elif block_type == "heading_1":
            rich_text = block.get("heading_1", {}).get("rich_text", [])
            text = " ".join(rt.get("plain_text", "") for rt in rich_text)
            lines.append(f"\n# {text}")
        elif block_type == "heading_2":
            rich_text = block.get("heading_2", {}).get("rich_text", [])
            text = " ".join(rt.get("plain_text", "") for rt in rich_text)
            lines.append(f"\n## {text}")
        elif block_type == "bulleted_list_item":
            rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
            text = " ".join(rt.get("plain_text", "") for rt in rich_text)
            lines.append(f"• {text}")
        elif block_type == "to_do":
            rich_text = block.get("to_do", {}).get("rich_text", [])
            checked = block.get("to_do", {}).get("checked", False)
            text = " ".join(rt.get("plain_text", "") for rt in rich_text)
            marker = "☑" if checked else "☐"
            lines.append(f"{marker} {text}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _search(client, args: dict) -> list[TextContent]:
    query = args["query"]
    page_size = args.get("page_size", 10)

    search_params: dict[str, Any] = {"query": query, "page_size": page_size}
    if args.get("filter_type"):
        search_params["filter"] = {"value": args["filter_type"], "property": "object"}

    result = await client.search(**search_params)
    items = result.get("results", [])

    if not items:
        return [TextContent(type="text", text=f"No results found for '{query}'.")]

    lines = [f"🔍 Search results for '{query}':\n"]
    for item in items:
        obj_type = item.get("object", "unknown")
        item_id = item["id"]

        # Extract title
        title = "Untitled"
        if obj_type == "page":
            for prop_val in item.get("properties", {}).values():
                if prop_val.get("type") == "title":
                    title_parts = prop_val.get("title", [])
                    if title_parts:
                        title = title_parts[0].get("plain_text", "Untitled")
                    break
        elif obj_type == "database":
            title_parts = item.get("title", [])
            if title_parts:
                title = title_parts[0].get("plain_text", "Untitled")

        lines.append(f"• [{obj_type.upper()}] **{title}**")
        lines.append(f"  🆔 ID: {item_id}")
        if item.get("url"):
            lines.append(f"  🔗 {item['url']}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


# ── Entry point for running as a standalone MCP server ──────────

async def main():
    """Run the Notion MCP server via stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
