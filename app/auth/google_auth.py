"""Google OAuth2 authentication helper for Calendar API."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import get_settings

logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_google_calendar_credentials() -> Credentials | None:
    """Get or refresh Google Calendar OAuth2 credentials.

    Flow:
    1. Try to load existing token from token.json
    2. If expired, refresh it
    3. If no token, run the OAuth flow (requires browser interaction)

    Returns:
        Credentials object or None if authentication fails.
    """
    settings = get_settings()
    creds = None

    token_path = Path(settings.google_calendar_token_path)
    credentials_path = Path(settings.google_calendar_credentials_path)

    # Load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load existing token: {e}")

    # Refresh or run new auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Google Calendar token refreshed successfully.")
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}, re-authenticating…")
                creds = None

        if not creds:
            if not credentials_path.exists():
                logger.error(
                    f"Google Calendar credentials file not found at {credentials_path}. "
                    f"See docs/setup_google_calendar.md for setup instructions."
                )
                return None

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Google Calendar authentication completed.")
            except Exception as e:
                logger.error(f"Google Calendar auth flow failed: {e}")
                return None

        # Save the token for future runs
        if creds:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            logger.info(f"Token saved to {token_path}")

    return creds


def build_calendar_service():
    """Build an authenticated Google Calendar API service object.

    Returns:
        googleapiclient.discovery.Resource for Calendar API v3, or None.
    """
    creds = get_google_calendar_credentials()
    if not creds:
        return None

    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=creds)
    return service
