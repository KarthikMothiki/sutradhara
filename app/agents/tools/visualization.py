"""Custom tool for generating Mermaid and D3 workflow diagrams from plan descriptions."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_workflow_diagram(
    steps: list[str],
    title: str = "Workflow Plan",
) -> dict:
    """Generate a Mermaid and JSON diagram from a list of workflow steps.

    This tool is used by the Planner agent to visualize the execution plan
    before running it, so users can approve/modify the workflow.

    Args:
        steps: List of step descriptions like ["Query Notion for tasks",
               "Find free calendar slots", "Create focus time events"]
        title: Title for the workflow diagram

    Returns:
        A dict with the Mermaid diagram string, JSON data, and a description.
    """
    if not steps:
        return {
            "diagram": "",
            "json_data": {"nodes": [], "links": []},
            "description": "No steps provided for diagram generation.",
        }

    # 1. Build Mermaid string (Legacy/Fallback)
    lines = ["graph TD"]
    lines.append(f'    Start(["🚀 {title}"])')

    for i, step in enumerate(steps):
        node_id = f"Step{i + 1}"
        if any(word in step.lower() for word in ["calendar", "schedule", "meeting", "event"]):
            icon = "📅"
        elif any(word in step.lower() for word in ["notion", "task", "page", "database"]):
            icon = "📝"
        elif any(word in step.lower() for word in ["plan", "analyze", "check"]):
            icon = "🧠"
        else:
            icon = "⚡"

        lines.append(f'    {node_id}["{icon} Step {i + 1}: {step}"]')
        prev_id = "Start" if i == 0 else f"Step{i}"
        lines.append(f"    {prev_id} --> {node_id}")

    lines.append(f'    End(["✅ Complete"])')
    lines.append(f"    Step{len(steps)} --> End")
    
    # Styling
    lines.append("    style Start fill:#6366f1,stroke:#4f46e5,color:#fff")
    lines.append("    style End fill:#10b981,stroke:#059669,color:#fff")
    for i in range(len(steps)):
        lines.append(f"    style Step{i + 1} fill:#1e293b,stroke:#334155,color:#e2e8f0")
    
    mermaid_diagram = "\n".join(lines)

    # 2. Build Structured JSON (For D3.js)
    nodes = [{"id": "Start", "label": "🚀 " + title, "type": "start"}]
    links = []

    for i, step in enumerate(steps):
        node_id = f"Step{i + 1}"
        if any(word in step.lower() for word in ["calendar", "schedule", "meeting", "event"]):
            icon, type_ = "📅", "calendar"
        elif any(word in step.lower() for word in ["notion", "task", "page", "database"]):
            icon, type_ = "📝", "notion"
        elif any(word in step.lower() for word in ["plan", "analyze", "check"]):
            icon, type_ = "🧠", "planner"
        else:
            icon, type_ = "⚡", "generic"

        nodes.append({
            "id": node_id,
            "label": f"{icon} {step}",
            "type": type_,
            "step_number": i + 1
        })
        prev_id = "Start" if i == 0 else f"Step{i}"
        links.append({"source": prev_id, "target": node_id})

    nodes.append({"id": "End", "label": "✅ Complete", "type": "end"})
    links.append({"source": f"Step{len(steps)}", "target": "End"})

    return {
        "diagram": mermaid_diagram,
        "json_data": {"nodes": nodes, "links": links},
        "description": f"Generated workflow diagram with {len(steps)} steps.",
        "step_count": len(steps),
    }
