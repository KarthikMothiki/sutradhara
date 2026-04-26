"""Memory Service — handles preference extraction and context injection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserPreference, MemoryEntry, Conversation
from app.config import get_settings

logger = logging.getLogger(__name__)

class MemoryService:
    """Manages long-term user memory and preference extraction."""

    async def extract_preferences(self, db: AsyncSession, conversation_id: str):
        """Analyze a conversation to extract user preferences and store them."""
        # 1. Fetch the conversation
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv or not conv.final_response:
            return

        # 2. Use LLM to extract preferences (Background Pass)
        # In a real implementation, we'd call Gemini with a specific prompt.
        # For the hackathon MVP, we'll implement a 'Pattern Extractor' agent.
        
        # PROMPT snippet for extraction:
        # "Review this conversation. Does the user express any habits, 
        # scheduling preferences, or project priorities? 
        # Format as: CATEGORY | KEY | VALUE | CONFIDENCE"

        logger.info(f"🧠 Extracting preferences for conversation {conversation_id[:8]}…")
        
        # [Placeholder for LLM Extraction Logic]
        # For now, we'll mock a discovery if certain keywords are present
        text = f"{conv.user_query} {conv.final_response}".lower()
        
        discovered = []
        if "morning" in text and ("hate" in text or "no " in text or "avoid" in text):
            discovered.append({
                "category": "scheduling",
                "key": "morning_preference",
                "value": "prefers avoiding morning meetings",
                "score": 0.9
            })
        
        if "focus" in text and "important" in text:
            discovered.append({
                "category": "task_management",
                "key": "focus_priority",
                "value": "prioritizes deep work blocks",
                "score": 0.8
            })

        # 3. Save to DB
        for pref in discovered:
            # Check if exists
            stmt = select(UserPreference).where(UserPreference.pref_key == pref["key"])
            existing = (await db.execute(stmt)).scalar_one_or_none()
            
            if existing:
                existing.pref_value = pref["value"]
                existing.confidence_score = pref["score"]
                existing.last_observed = datetime.now(timezone.utc)
            else:
                db.add(UserPreference(
                    category=pref["category"],
                    pref_key=pref["key"],
                    pref_value=pref["value"],
                    confidence_score=pref["score"]
                ))
        
        await db.commit()

    async def get_active_context(self, db: AsyncSession) -> str:
        """Fetch all relevant user preferences to inject into agent system prompts."""
        result = await db.execute(select(UserPreference))
        prefs = result.scalars().all()
        
        if not prefs:
            return ""
            
        context = "\nUSER HABITS & PREFERENCES:\n"
        for p in prefs:
            context += f"• {p.pref_value} (Confidence: {int(p.confidence_score*100)}%)\n"
        
        return context

memory_service = MemoryService()
