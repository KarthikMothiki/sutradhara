"""Thought recording tools — enables live Chain-of-Thought visualization."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

def record_thought(thought: str) -> dict[str, Any]:
    """Record an internal thought or deliberation process. 
    Use this to explain your reasoning or plan before taking action.
    
    Args:
        thought: The internal reasoning or deliberation text.
    """
    logger.info(f"💭 Thought: {thought}")
    return {"status": "recorded", "thought": thought}
