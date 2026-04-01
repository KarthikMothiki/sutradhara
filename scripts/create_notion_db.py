#!/usr/bin/env python3
"""Create a Notion database for Project Sūtradhāra.

Usage:
    NOTION_TOKEN=ntn_xxx python scripts/create_notion_db.py

This script:
1. Searches for an existing parent page called "Sūtradhāra Tasks" (or creates one)
2. Creates a database with the expected schema (Name, Status, Priority, Due Date, Tags)
3. Prints the DATABASE_ID you need for your .env file
"""

import json
import os
import sys

import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def search_for_page(title: str) -> str | None:
    """Search for an existing page by title. Returns page_id or None."""
    resp = requests.post(
        f"{NOTION_API}/search",
        headers=HEADERS,
        json={
            "query": title,
            "filter": {"value": "page", "property": "object"},
        },
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    for page in results:
        page_title = ""
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                for t in prop.get("title", []):
                    page_title += t.get("plain_text", "")
        if title.lower() in page_title.lower():
            return page["id"]
    return None


def find_any_shared_page() -> str | None:
    """Find any page the integration has access to."""
    resp = requests.post(
        f"{NOTION_API}/search",
        headers=HEADERS,
        json={
            "filter": {"value": "page", "property": "object"},
            "page_size": 10,
        },
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    return None


def create_database(parent_page_id: str) -> str:
    """Create a database with the expected schema inside the parent page."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"emoji": "📋"},
        "title": [{"text": {"content": "Task Board"}}],
        "properties": {
            # Title property (required — every DB needs exactly one)
            "Name": {"title": {}},
            # Status property
            "Status": {
                "status": {
                    "options": [
                        {"name": "To Do", "color": "default"},
                        {"name": "In Progress", "color": "blue"},
                        {"name": "Done", "color": "green"},
                    ],
                    "groups": [
                        {
                            "name": "To-do",
                            "option_ids": [],  # Notion auto-assigns
                            "color": "gray",
                        },
                        {
                            "name": "In progress",
                            "option_ids": [],
                            "color": "blue",
                        },
                        {
                            "name": "Complete",
                            "option_ids": [],
                            "color": "green",
                        },
                    ],
                }
            },
            # Priority selector
            "Priority": {
                "select": {
                    "options": [
                        {"name": "High", "color": "red"},
                        {"name": "Medium", "color": "yellow"},
                        {"name": "Low", "color": "green"},
                    ]
                }
            },
            # Due date
            "Due Date": {"date": {}},
            # Tags (multi-select)
            "Tags": {
                "multi_select": {
                    "options": [
                        {"name": "Work", "color": "blue"},
                        {"name": "Personal", "color": "green"},
                        {"name": "Urgent", "color": "red"},
                        {"name": "Research", "color": "purple"},
                        {"name": "Meeting", "color": "orange"},
                    ]
                }
            },
            # Timestamps (auto-managed by Notion)
            "Created At": {"created_time": {}},
            "Last Modified": {"last_edited_time": {}},
        },
    }

    resp = requests.post(
        f"{NOTION_API}/databases",
        headers=HEADERS,
        json=payload,
    )

    if resp.status_code != 200:
        # Status property creation can be finicky — retry without explicit options
        print(f"⚠️  First attempt returned {resp.status_code}, retrying with simpler Status…")
        payload["properties"]["Status"] = {"status": {}}
        resp = requests.post(
            f"{NOTION_API}/databases",
            headers=HEADERS,
            json=payload,
        )

    resp.raise_for_status()
    db = resp.json()
    db_id = db["id"]
    # URL-friendly ID (remove hyphens)
    db_id_clean = db_id.replace("-", "")
    return db_id_clean


def seed_sample_tasks(database_id: str):
    """Add a few sample tasks so the database isn't empty."""
    tasks = [
        {
            "Name": "Review PR #42",
            "Status": "To Do",
            "Priority": "High",
            "Tags": ["Work"],
        },
        {
            "Name": "Prepare weekly presentation",
            "Status": "In Progress",
            "Priority": "Medium",
            "Tags": ["Work", "Meeting"],
        },
        {
            "Name": "Read research paper on RAG",
            "Status": "To Do",
            "Priority": "Low",
            "Tags": ["Research"],
        },
    ]

    for task in tasks:
        props = {
            "Name": {"title": [{"text": {"content": task["Name"]}}]},
            "Priority": {"select": {"name": task["Priority"]}},
            "Tags": {"multi_select": [{"name": t} for t in task["Tags"]]},
            "Status": {"status": {"name": task["Status"]}},
        }
        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=HEADERS,
            json={
                "parent": {"database_id": database_id},
                "properties": props,
            },
        )
        if resp.ok:
            print(f"   📝 Created task: {task['Name']}")
        else:
            print(f"   ⚠️  Could not create '{task['Name']}': {resp.status_code}")


def main():
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN not set. Run with:")
        print('   NOTION_TOKEN="ntn_xxx" python scripts/create_notion_db.py')
        sys.exit(1)

    print("🎭 Project Sūtradhāra — Notion Database Setup\n")

    # 1. Find a page the integration has access to
    print("🔍 Searching for a shared page to use as parent…")
    parent_id = search_for_page("Sūtradhāra Tasks")
    if parent_id:
        print(f"   Found existing Sūtradhāra page: {parent_id}")
    else:
        parent_id = find_any_shared_page()
        if parent_id:
            print(f"   Using existing shared page: {parent_id}")
        else:
            print("\n❌ No pages are shared with your integration yet.")
            print("\n   To fix this:")
            print("   1. Open any page in Notion (or create a new blank one)")
            print('   2. Click ••• (top right) → "Add connections"')
            print('   3. Search for your integration and connect it')
            print("   4. Re-run this script\n")
            sys.exit(1)

    # 2. Create the database
    print("\n📋 Creating task database…")
    db_id = create_database(parent_id)
    print(f"✅ Database created!\n")

    # 3. Seed sample tasks
    print("🌱 Adding sample tasks…")
    seed_sample_tasks(db_id)

    # 4. Print results
    print("\n" + "═" * 55)
    print("  🎉  ALL DONE!")
    print("═" * 55)
    print(f"\n  NOTION_DATABASE_ID = {db_id}\n")
    print("  Add this to your .env file:")
    print(f'  NOTION_DATABASE_ID={db_id}')
    print("\n  ⚠️  Don't forget to also connect the integration to")
    print("  the database in Notion (••• → Add connections).")
    print("═" * 55)


if __name__ == "__main__":
    main()
