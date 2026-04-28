"""Thought recording tools — enables live Chain-of-Thought visualization."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

def record_thought(thought: str) -> str:
    """Record an internal thought or deliberation process. 
    Use this to explain your reasoning or plan before taking action.
    """
    logger.info(f"💭 Thought: {thought}")
    return thought

def record_handoff(target_agent: str, reason: str) -> str:
    """Record a delegation or handoff to another specialized agent.
    Use this whenever you delegate a sub-task to a specialist (e.g., Calendar, Notion).
    """
    msg = f"🤝 Handing off to **{target_agent}** because: {reason}"
    logger.info(msg)
    return msg
