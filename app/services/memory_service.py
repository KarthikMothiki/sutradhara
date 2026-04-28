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
        """Analyze a conversation to extract user preferences and productivity patterns using Gemini."""
        from app.agents.crew import run_agent_query
        
        # 1. Fetch the conversation
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv or not conv.final_response:
            return

        logger.info(f"🧠 ML Pattern Recognition: Analyzing conversation {conversation_id[:8]}…")
        
        # 2. Use Gemini as a 'Pattern Recognition' analyst
        analysis_query = (
            f"ACT AS A PRODUCTIVITY ANALYST. Review this interaction:\n"
            f"USER QUERY: {conv.user_query}\n"
            f"AGENT RESPONSE: {conv.final_response}\n\n"
            f"EXTRACT patterns regarding:\n"
            f"1. Scheduling habits (e.g., 'prefers mornings', 'avoids Fridays')\n"
            f"2. Priority handling (e.g., 'tends to over-commit', 'prioritizes deep work')\n"
            f"3. Deadline sensitivity (e.g., 'mentions being stressed by tight deadlines')\n\n"
            f"Format strictly as: CATEGORY | KEY | VALUE | CONFIDENCE (0-1.0)"
        )

        try:
            # We use a quiet background query for analysis
            analysis_result = await run_agent_query(
                query=analysis_query,
                source="internal:memory_extraction",
            )
            raw_patterns = analysis_result.get("response", "")
            
            # 3. Parse and save to DB
            for line in raw_patterns.split("\n"):
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 4:
                        cat, key, val, conf = parts[0], parts[1], parts[2], float(parts[3])
                        
                        # Upsert preference
                        stmt = select(UserPreference).where(UserPreference.pref_key == key)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        
                        if existing:
                            existing.pref_value = val
                            existing.confidence_score = (existing.confidence_score + conf) / 2
                            existing.last_observed = datetime.now(timezone.utc)
                        else:
                            db.add(UserPreference(
                                category=cat,
                                pref_key=key,
                                pref_value=val,
                                confidence_score=conf
                            ))
            
            await db.commit()
            logger.info("✅ ML Patterns stored in long-term memory.")
        except Exception as e:
            logger.error(f"❌ ML Extraction failed: {e}")

    async def get_productivity_dna(self, db: AsyncSession) -> str:
        """Fetch a summary of user productivity patterns for agent injection."""
        result = await db.execute(select(UserPreference))
        prefs = result.scalars().all()
        
        if not prefs:
            return "No established productivity patterns yet."
            
        context = "\nUSER PRODUCTIVITY DNA & PATTERNS:\n"
        for p in prefs:
            if p.confidence_score > 0.6: # Only high-confidence patterns
                context += f"• [{p.category.upper()}] {p.pref_value}\n"
        
        return context

memory_service = MemoryService()

memory_service = MemoryService()
