"""Notion authentication helper."""

from __future__ import annotations

import logging

from notion_client import AsyncClient, Client

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_notion_client() -> AsyncClient | None:
    """Get an authenticated Notion API async client.

    Returns:
        AsyncClient or None if no token is configured.
    """
    settings = get_settings()

    if not settings.notion_token:
        logger.error(
            "NOTION_TOKEN is not configured. "
            "See docs/setup_notion.md for setup instructions."
        )
        return None

    client = AsyncClient(auth=settings.notion_token)
    logger.info("Notion client initialized.")
    return client


def get_notion_client_sync() -> Client | None:
    """Get an authenticated Notion API synchronous client.

    Use this in ADK tool functions that run inside an already-active
    async event loop (where run_until_complete would fail).

    Returns:
        Client or None if no token is configured.
    """
    settings = get_settings()

    if not settings.notion_token:
        logger.error(
            "NOTION_TOKEN is not configured. "
            "See docs/setup_notion.md for setup instructions."
        )
        return None

    return Client(auth=settings.notion_token)

