#!/usr/bin/env python3
"""Add timestamp properties to an existing Notion database.

Usage:
    python scripts/add_timestamp_properties.py

Reads NOTION_TOKEN and NOTION_DATABASE_ID from .env (or environment).
Adds "Created At" (created_time) and "Last Modified" (last_edited_time)
properties to the existing database schema.
"""

import os
import sys

import requests

# Load from .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def update_database_schema(database_id: str) -> None:
    """Add Created At and Last Modified properties to the database."""
    payload = {
        "properties": {
            "Created At": {"created_time": {}},
            "Last Modified": {"last_edited_time": {}},
        }
    }

    resp = requests.patch(
        f"{NOTION_API}/databases/{database_id}",
        headers=HEADERS,
        json=payload,
    )

    if resp.ok:
        print("✅ Successfully added timestamp properties to the database!")
        print("   • Created At (created_time) — auto-set when a page is created")
        print("   • Last Modified (last_edited_time) — auto-updated on every edit")
    else:
        print(f"❌ Failed to update database: {resp.status_code}")
        print(f"   {resp.json()}")
        sys.exit(1)


def verify_properties(database_id: str) -> None:
    """Verify the database now has the timestamp properties."""
    resp = requests.get(
        f"{NOTION_API}/databases/{database_id}",
        headers=HEADERS,
    )
    resp.raise_for_status()
    props = resp.json().get("properties", {})

    print("\n📋 Current database properties:")
    for name, prop in sorted(props.items()):
        ptype = prop.get("type", "unknown")
        emoji = {
            "title": "📝",
            "status": "🔄",
            "select": "🏷️",
            "multi_select": "🏷️",
            "date": "📅",
            "created_time": "🕐",
            "last_edited_time": "🕑",
        }.get(ptype, "•")
        print(f"   {emoji} {name} ({ptype})")


def main():
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN not set.")
        sys.exit(1)
    if not NOTION_DATABASE_ID:
        print("❌ NOTION_DATABASE_ID not set.")
        sys.exit(1)

    print("🎭 Project Sūtradhāra — Adding Timestamp Properties\n")
    print(f"   Database: {NOTION_DATABASE_ID}\n")

    update_database_schema(NOTION_DATABASE_ID)
    verify_properties(NOTION_DATABASE_ID)


if __name__ == "__main__":
    main()
