# Setting Up Google Calendar API Credentials

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** (top bar) → **New Project**
3. Enter a project name (e.g., "multi-agent-tasks") and click **Create**
4. Make sure the new project is selected

## Step 2: Enable Google Calendar API

1. Go to **APIs & Services** → **Library**
2. Search for "Google Calendar API"
3. Click on it and press **Enable**

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** user type → **Create**
3. Fill in:
   - App name: "Multi-Agent Task System"
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes**
   - Add `https://www.googleapis.com/auth/calendar`
6. Click **Save and Continue**
7. On **Test users**, click **Add Users**
   - Add your Google account email
8. Click **Save and Continue** → **Back to Dashboard**

## Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: "multi-agent-tasks"
5. Click **Create**
6. Click **Download JSON**
7. Save the file as `credentials.json` in the project root

## Step 5: Configure the Application

1. Copy the downloaded file to the project root:
   ```bash
   cp ~/Downloads/client_secret_*.json ./credentials.json
   ```

2. Set the path in `.env`:
   ```
   GOOGLE_CALENDAR_CREDENTIALS_PATH=./credentials.json
   GOOGLE_CALENDAR_TOKEN_PATH=./token.json
   ```

## Step 6: First Authentication

The first time the app runs and tries to access the Calendar API, it will:
1. Open a browser window for Google OAuth login
2. Ask you to authorize the app
3. Save the token to `token.json` for future use

> **Note:** For Cloud Run deployment, you'll need to complete the OAuth flow locally first, then include the `token.json` in your deployment or use a service account with domain-wide delegation.
