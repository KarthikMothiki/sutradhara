# Project Sūtradhāra — Multi-Agent Productivity Orchestrator

> _Sūtradhāra_ (सूत्रधार) — "the one who holds the strings." An AI orchestrator that directs a crew of agents to manage your Google Calendar and Notion tasks through natural language.

## 🏗️ Architecture

**Google ADK** (Agent Development Kit) with a **Crew-based** multi-agent pattern:

```
Manager (Root Orchestrator)
├── 📅 Calendar Specialist  ─→ Google Calendar MCP
├── 📝 Notion Specialist    ─→ Notion MCP
└── 🧠 Planner              ─→ Multi-step workflows
    ├── Calendar Specialist
    └── Notion Specialist
```

**Key Features:**

- 🔍 **Live Agent Trace UI** — Watch agents think in real-time
- 📊 **Workflow Visualization** — Auto-generated Mermaid diagrams
- ↩️ **Undo/Rollback** — Reverse any action the agents took
- ⏰ **Proactive Features** — Daily briefings, meeting prep, conflict detection
- 🚀 **Cloud Run Ready** — Docker-based deployment

## 🚀 Quick Start

### 1. Clone & Install

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your credentials:
# - GOOGLE_API_KEY (required)
# - NOTION_TOKEN + NOTION_DATABASE_ID (for Notion features)
# - Google Calendar OAuth setup (see docs/setup_google_calendar.md)
```

### 3. Run

```bash
python -m app.main
# or
uvicorn app.main:app --reload --port 8080
```

Open **http://localhost:8080** for the Agent Trace UI.

### 4. Docker

```bash
docker compose up --build
```

## 📖 Setup Guides

- [Google Calendar API Setup](docs/setup_google_calendar.md)
- [Notion Integration Setup](docs/setup_notion.md)

## 🎯 Capabilities

### Tier 1 — Single-Tool Operations

- "What meetings do I have tomorrow?"
- "Create a task called 'Review PR #42' in my Notion board"
- "Add a meeting with Sarah at 3 PM on Friday"

### Tier 2 — Multi-Step Workflows

- "Review my meeting notes and create tasks for each action item"
- "Schedule 2 hours of focus time for my high-priority tasks"
- "Move my 2 PM meeting to tomorrow and update the related Notion page"

### Tier 3 — Proactive/Autonomous

- 🌅 Daily Briefing (every morning)
- 📋 Meeting Prep (15 min before meetings)
- 📊 Weekly Review (Friday evening)
- ⚠️ Conflict Detection (every 30 min)
- 🧠 Smart Rescheduling (every hour)

## 🛠️ Tech Stack

| Layer           | Technology                           |
| --------------- | ------------------------------------ |
| Agent Framework | Google ADK                           |
| LLM             | Gemini 2.5 Pro (with fallback chain) |
| API Server      | FastAPI                              |
| Database        | SQLite + SQLAlchemy                  |
| External APIs   | Google Calendar, Notion              |
| Protocol        | Model Context Protocol (MCP)         |
| Scheduling      | APScheduler                          |
| Frontend        | Vanilla HTML/CSS/JS + Mermaid.js     |
| Deployment      | Docker + Cloud Run                   |

## 📄 License

MIT
