"""WebSocket endpoint for live agent trace streaming."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.trace_service import trace_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/trace/{conversation_id}")
async def trace_websocket(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for real-time agent trace events.

    Connect to this endpoint to receive live updates as agents process a query.

    Events emitted:
    - agent_start:       An agent has started processing
    - agent_end:         An agent has finished processing
    - tool_call:         An agent is calling an MCP tool
    - tool_result:       An MCP tool has returned a result
    - workflow_diagram:  A Mermaid workflow diagram was generated
    - error:             An error occurred
    """
    await trace_service.connect(websocket, conversation_id)

    try:
        # Keep the connection alive — listen for client messages (e.g., ping)
        while True:
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await trace_service.disconnect(websocket, conversation_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await trace_service.disconnect(websocket, conversation_id)
