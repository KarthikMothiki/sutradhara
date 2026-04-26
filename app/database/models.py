"""SQLAlchemy ORM models for the task management system."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


# ── Enums ───────────────────────────────────────────────────────

class ConversationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FocusBlockStatus(str, enum.Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    RESCHEDULED = "rescheduled"


# ── Helper ──────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ── Models ──────────────────────────────────────────────────────

class Conversation(Base):
    """Tracks user interactions / queries."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus), default=ConversationStatus.PENDING
    )
    workflow_diagram: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Mermaid diagram of the workflow plan"
    )
    source: Mapped[str] = mapped_column(
        String(50), default="api", comment="Origin: api, scheduler, etc."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    action_logs: Mapped[list[ActionLog]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id[:8]}… status={self.status.value}>"


class WorkflowRun(Base):
    """Tracks each agent/tool execution step within a conversation."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_called: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        Enum(WorkflowRunStatus), default=WorkflowRunStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(
        back_populates="workflow_runs"
    )

    def __repr__(self) -> str:
        return f"<WorkflowRun {self.id[:8]}… agent={self.agent_name}>"


class ActionLog(Base):
    """Tracks reversible actions for undo/rollback support."""

    __tablename__ = "action_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="e.g., create_event, update_page, delete_event"
    )
    service: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="calendar or notion"
    )
    resource_id: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="External ID of the created/modified resource"
    )
    forward_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Data used to perform the action"
    )
    reverse_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Data needed to undo the action"
    )
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(
        back_populates="action_logs"
    )

    def __repr__(self) -> str:
        reversed_tag = " [REVERSED]" if self.is_reversed else ""
        return f"<ActionLog {self.id[:8]}… {self.action_type}{reversed_tag}>"


class UserPriorities(Base):
    """Tracks user goals, priorities and targets."""
    __tablename__ = "user_priorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    weekly_hours_target: Mapped[float] = mapped_column(nullable=False, default=0.0)
    total_hours_remaining: Mapped[float] = mapped_column(nullable=False, default=0.0)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    focus_blocks: Mapped[list[FocusBlocks]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )
    progress_logs: Mapped[list[ProgressLog]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserPriorities id={self.id} goal='{self.goal_name}' rank={self.priority_rank}>"


class FocusBlocks(Base):
    """Maps proposed and confirmed focus blocks back to goals."""
    __tablename__ = "focus_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_priorities.id"), nullable=False)
    calendar_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[FocusBlockStatus] = mapped_column(Enum(FocusBlockStatus), default=FocusBlockStatus.PROPOSED)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    goal: Mapped[UserPriorities] = relationship(back_populates="focus_blocks")
    progress_logs: Mapped[list[ProgressLog]] = relationship(
        back_populates="focus_block", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FocusBlocks id={self.id} status={self.status.value}>"


class ProgressLog(Base):
    """Records completed focus sessions."""
    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    focus_block_id: Mapped[int] = mapped_column(Integer, ForeignKey("focus_blocks.id"), nullable=False)
    goal_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_priorities.id"), nullable=False)
    hours_completed: Mapped[float] = mapped_column(nullable=False, default=0.0)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pace_adjustment: Mapped[float] = mapped_column(nullable=False, default=1.0)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    focus_block: Mapped[FocusBlocks] = relationship(back_populates="progress_logs")
    goal: Mapped[UserPriorities] = relationship(back_populates="progress_logs")

    def __repr__(self) -> str:
        return f"<ProgressLog id={self.id} hours={self.hours_completed}>"


class PendingAction(Base):
    """Tracks actions that require user approval before execution."""

    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="e.g., CREATE_EVENT, UPDATE_TASK"
    )
    service: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="e.g., calendar, notion"
    )
    proposed_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="pending | approved | rejected | executed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship()

    def __repr__(self) -> str:
        return f"<PendingAction {self.id[:8]} status={self.status}>"


class UserPreference(Base):
    """Stores long-term user habits and preferences (e.g., 'User prefers afternoon focus')."""
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="scheduling, task_management, communication")
    pref_key: Mapped[str] = mapped_column(String(100), nullable=False)
    pref_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(default=1.0)
    last_observed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<UserPreference key='{self.pref_key}' value='{self.pref_value[:20]}'>"


class MemoryEntry(Base):
    """Distilled insights and context from previous conversations."""
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=True)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, comment="List of projects/people this insight relates to")
    importance: Mapped[int] = mapped_column(Integer, default=1, comment="1-5 scale of how critical this memory is")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<MemoryEntry id={self.id[:8]} text='{self.insight_text[:30]}…'>"


class KnowledgeGraphEntry(Base):
    """Maps relationships between people, projects, and companies found in data."""
    __tablename__ = "knowledge_graph"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False, comment="Entity name (e.g. 'Project Loom')")
    object: Mapped[str] = mapped_column(String(200), nullable=False, comment="Related entity (e.g. 'Sarah')")
    relationship: Mapped[str] = mapped_column(String(100), nullable=False, comment="Type of link (e.g. 'lead_by', 'member_of')")
    source_service: Mapped[str] = mapped_column(String(50), nullable=True, comment="notion or calendar")
    last_verified: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<KnowledgeGraph {self.subject} --[{self.relationship}]--> {self.object}>"


class DashboardAlert(Base):
    """Proactive notifications generated by the Anticipator agent."""
    __tablename__ = "dashboard_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", comment="info, warning, success")
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<DashboardAlert title='{self.title}' status={'dismissed' if self.is_dismissed else 'active'}>"

