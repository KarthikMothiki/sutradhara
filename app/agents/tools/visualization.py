"""Custom tool for generating Mermaid workflow diagrams from plan descriptions."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_workflow_diagram(
    steps: list[str],
    title: str = "Workflow Plan",
) -> dict:
    """Generate a Mermaid diagram from a list of workflow steps.

    This tool is used by the Planner agent to visualize the execution plan
    before running it, so users can approve/modify the workflow.

    Args:
        steps: List of step descriptions like ["Query Notion for tasks",
               "Find free calendar slots", "Create focus time events"]
        title: Title for the workflow diagram

    Returns:
        A dict with the Mermaid diagram string and a description.
    """
    if not steps:
        return {
            "diagram": "",
            "description": "No steps provided for diagram generation.",
        }

    # Build a Mermaid flowchart
    lines = ["graph TD"]
    lines.append(f'    Start(["🚀 {title}"])')

    for i, step in enumerate(steps):
        node_id = f"Step{i + 1}"
        # Determine icon based on keywords
        if any(word in step.lower() for word in ["calendar", "schedule", "meeting", "event"]):
            icon = "📅"
        elif any(word in step.lower() for word in ["notion", "task", "page", "database"]):
            icon = "📝"
        elif any(word in step.lower() for word in ["plan", "analyze", "check"]):
            icon = "🧠"
        else:
            icon = "⚡"

        lines.append(f'    {node_id}["{icon} Step {i + 1}: {step}"]')

        # Connect to previous step
        if i == 0:
            lines.append(f"    Start --> {node_id}")
        else:
            prev_id = f"Step{i}"
            lines.append(f"    {prev_id} --> {node_id}")

    # Add end node
    last_step = f"Step{len(steps)}"
    lines.append(f'    End(["✅ Complete"])')
    lines.append(f"    {last_step} --> End")

    # Add styling
    lines.append("")
    lines.append("    style Start fill:#6366f1,stroke:#4f46e5,color:#fff")
    lines.append("    style End fill:#10b981,stroke:#059669,color:#fff")
    for i in range(len(steps)):
        lines.append(f"    style Step{i + 1} fill:#1e293b,stroke:#334155,color:#e2e8f0")

    diagram = "\n".join(lines)

    return {
        "diagram": diagram,
        "description": f"Generated workflow diagram with {len(steps)} steps.",
        "step_count": len(steps),
    }
