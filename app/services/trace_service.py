"""Agent trace broadcasting service for real-time UI updates via WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.database.schemas import TraceEvent

logger = logging.getLogger(__name__)


class TraceService:
    """Manages WebSocket connections and broadcasts agent trace events.

    Usage:
        trace_service = TraceService()

        # In WebSocket endpoint:
        await trace_service.connect(websocket, conversation_id)

        # From agent callbacks:
        await trace_service.emit(TraceEvent(...))
    """

    def __init__(self):
        # conversation_id -> set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, conversation_id: str) -> None:
        """Register a WebSocket for a specific conversation's trace events."""
        await websocket.accept()
        async with self._lock:
            self._connections[conversation_id].add(websocket)
        logger.info(f"Trace client connected for conversation {conversation_id[:8]}…")

    async def disconnect(self, websocket: WebSocket, conversation_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections[conversation_id].discard(websocket)
            if not self._connections[conversation_id]:
                del self._connections[conversation_id]
        logger.info(f"Trace client disconnected from conversation {conversation_id[:8]}…")

    async def emit(self, event: TraceEvent) -> None:
        """Broadcast a trace event to all connected clients for that conversation."""
        conversation_id = event.conversation_id
        async with self._lock:
            connections = self._connections.get(conversation_id, set()).copy()

        if not connections:
            return

        message = event.model_dump_json()
        dead_connections = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._connections[conversation_id].discard(ws)

    async def emit_agent_start(
        self, conversation_id: str, agent_name: str, data: dict[str, Any] | None = None
    ) -> None:
        """Shorthand: emit an agent_start event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="agent_start",
            agent_name=agent_name,
            data=data or {},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_agent_end(
        self, conversation_id: str, agent_name: str, data: dict[str, Any] | None = None
    ) -> None:
        """Shorthand: emit an agent_end event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="agent_end",
            agent_name=agent_name,
            data=data or {},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_tool_call(
        self,
        conversation_id: str,
        agent_name: str,
        tool_name: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Shorthand: emit a tool_call event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="tool_call",
            agent_name=agent_name,
            tool_name=tool_name,
            data=data or {},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_tool_result(
        self,
        conversation_id: str,
        agent_name: str,
        tool_name: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Shorthand: emit a tool_result event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="tool_result",
            agent_name=agent_name,
            tool_name=tool_name,
            data=data or {},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_error(
        self,
        conversation_id: str,
        error: str,
        agent_name: str | None = None,
    ) -> None:
        """Shorthand: emit an error event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="error",
            agent_name=agent_name,
            data={"error": error},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_workflow_diagram(
        self, conversation_id: str, diagram: str
    ) -> None:
        """Shorthand: emit a workflow_diagram event."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="workflow_diagram",
            data={"diagram": diagram},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_canvas_event(
        self,
        conversation_id: str,
        event_type: str,
        data: dict[str, Any],
        agent_name: str | None = None,
    ) -> None:
        """Shorthand: emit a canvas_event for the Action Theater UI."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="canvas_event",
            agent_name=agent_name,
            data={"type": event_type, "payload": data},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_agent_thought(
        self,
        conversation_id: str,
        agent_name: str,
        thought: str,
    ) -> None:
        """Shorthand: emit an agent_thought event for live reasoning visualization."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="agent_thought",
            agent_name=agent_name,
            data={"thought": thought},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_loom_event(
        self,
        conversation_id: str,
        agent_name: str,
        event_type: str,
        text: str,
    ) -> None:
        """General emitter for Loom trace entries (THOUGHT, DELEGATION, SYNTHESIS, etc)."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="loom_event",
            agent_name=agent_name,
            data={"type": event_type, "text": text},
            timestamp=datetime.now(timezone.utc),
        ))

    async def emit_response_chunk(
        self,
        conversation_id: str,
        chunk: str,
    ) -> None:
        """Shorthand: emit a response_chunk event for real-time text streaming."""
        await self.emit(TraceEvent(
            conversation_id=conversation_id,
            event_type="response_chunk",
            data={"text": chunk},
            timestamp=datetime.now(timezone.utc),
        ))



# ── Singleton ───────────────────────────────────────────────────
trace_service = TraceService()
