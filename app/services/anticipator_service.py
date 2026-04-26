"""Anticipator Service — coordinates proactive audits and dashboard alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DashboardAlert, Conversation, ConversationStatus
from app.database.engine import get_session_factory
from app.agents.crew import run_agent_query

logger = logging.getLogger(__name__)

class AnticipatorService:
    """Manages proactive background audits of the user's schedule."""

    async def run_proactive_audit(self):
        """Perform a full system audit and generate dashboard alerts."""
        logger.info("🚀 Starting proactive system audit…")
        
        # We run a specialized query through the agent crew
        query = (
            "Perform a Proactive Audit of my next 48 hours. "
            "Check for meeting conflicts, back-to-back fatigue, and missing project context in Notion. "
            "Return a list of specific alerts with Title, Message, and Severity."
        )
        
        try:
            # We use a special 'system-anticipator' conversation ID
            result = await run_agent_query(
                query=query,
                conversation_id="system-audit-" + datetime.now().strftime("%Y%m%d-%H"),
                source="scheduler:anticipator"
            )
            
            response_text = result.get("response", "")
            
            # Simple parser to extract alerts from agent response
            # In a production app, we'd use structured output (pydantic)
            alerts = self._parse_alerts(response_text)
            
            if alerts:
                factory = get_session_factory()
                async with factory() as db:
                    for alert_data in alerts:
                        db.add(DashboardAlert(
                            title=alert_data["title"],
                            message=alert_data["message"],
                            severity=alert_data["severity"]
                        ))
                    await db.commit()
                logger.info(f"✅ Proactive audit complete. Generated {len(alerts)} alerts.")
            else:
                logger.info("✅ Proactive audit complete. No issues found.")
                
        except Exception as e:
            logger.error(f"Proactive audit failed: {e}")

    def _parse_alerts(self, text: str) -> list[dict]:
        """Simple markdown parser for agent-generated alerts."""
        alerts = []
        import re
        
        # Look for Title: / Message: / Severity: patterns
        sections = re.split(r"(?i)title:", text)
        for section in sections[1:]:
            try:
                title_match = re.search(r"^(.*?)\n", section)
                msg_match = re.search(r"(?i)message:\s*(.*?)\n", section, re.DOTALL)
                sev_match = re.search(r"(?i)severity:\s*(\w+)", section)
                
                if title_match and msg_match:
                    alerts.append({
                        "title": title_match.group(1).strip(),
                        "message": msg_match.group(1).strip().split("\n\n")[0], # Take first block
                        "severity": sev_match.group(1).strip().lower() if sev_match else "info"
                    })
            except Exception:
                continue
        return alerts

anticipator_service = AnticipatorService()
