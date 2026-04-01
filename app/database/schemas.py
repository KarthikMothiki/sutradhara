"""Pydantic schemas for API request / response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request Schemas ─────────────────────────────────────────────

class QueryRequest(BaseModel):
    """POST /api/v1/query — user's natural-language request."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language request")
    session_id: str | None = Field(
        default=None, description="Persistent chat session ID for conversation continuity"
    )
    context: dict[str, Any] | None = Field(
        default=None, description="Optional context (e.g., preferred timezone)"
    )


class FeedbackRequest(BaseModel):
    """POST /api/v1/query/{id}/feedback — user rates a response."""
    rating: int = Field(..., ge=1, le=5, description="1-5 star rating")
    comment: str | None = Field(default=None, max_length=500)


# ── Response Schemas ────────────────────────────────────────────

class QueryResponse(BaseModel):
    """Response for a query submission."""
    id: str
    status: str
    message: str = "Query submitted successfully"


class ConversationResponse(BaseModel):
    """Full response for a single conversation."""
    id: str
    user_query: str
    final_response: str | None = None
    status: str
    workflow_diagram: str | None = None
    source: str = "api"
    created_at: datetime
    updated_at: datetime
    workflow_runs: list[WorkflowRunResponse] = []
    action_logs: list[ActionLogResponse] = []

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    """Response for a single workflow run step."""
    id: str
    agent_name: str
    tool_called: str | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    status: str
    error_message: str | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionLogResponse(BaseModel):
    """Response for a single action log entry."""
    id: str
    action_type: str
    service: str
    resource_id: str
    is_reversed: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    """Response for conversation history listing."""
    conversations: list[ConversationSummary]
    total: int
    page: int = 1
    per_page: int = 20


class ConversationSummary(BaseModel):
    """Lightweight summary for history listing."""
    id: str
    user_query: str
    status: str
    source: str = "api"
    created_at: datetime

    model_config = {"from_attributes": True}


class UndoResponse(BaseModel):
    """Response for an undo operation."""
    success: bool
    undone_actions: int
    details: list[str] = []


# ── WebSocket Schemas ───────────────────────────────────────────

class TraceEvent(BaseModel):
    """Real-time trace event broadcast via WebSocket."""
    conversation_id: str
    event_type: str  # agent_start, agent_end, tool_call, tool_result, error
    agent_name: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = {}
    timestamp: datetime

    model_config = {"from_attributes": True}


class DiagramResponse(BaseModel):
    """Response for workflow diagram request."""
    conversation_id: str
    diagram: str | None = None
    message: str = ""
