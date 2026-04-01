# Setting Up Notion Integration

## Step 1: Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **+ New integration**
3. Fill in:
   - Name: "Multi-Agent Task System"
   - Associated workspace: Select your workspace
   - Type: **Internal**
4. Click **Submit**
5. Copy the **Internal Integration Secret** (starts with `ntn_`)

## Step 2: Share Your Database with the Integration

1. Open your target Notion database (a task board works great)
2. Click the **•••** menu (top right)
3. Click **Add connections** (or **Connect to**)
4. Search for "Multi-Agent Task System" (your integration name)
5. Click it to grant access

## Step 3: Get Your Database ID

1. Open your database in Notion (as a full page, not inline)
2. Look at the URL. It will look like:
   ```
   https://www.notion.so/your-workspace/DATABASE_ID?v=...
   ```
3. The `DATABASE_ID` is the 32-character hex string before the `?`
4. Example: `a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`

## Step 4: Configure the Application

Add these to your `.env` file:

```env
# Notion Integration Token
NOTION_TOKEN=ntn_your_integration_secret_here

# Your database ID (32-char hex string)
NOTION_DATABASE_ID=your_database_id_here
```

## Step 5: Recommended Database Schema

For best results, your Notion database should have these properties:

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Task/page title (default) |
| Status | Status | Task status (To Do, In Progress, Done) |
| Priority | Select | Priority level (High, Medium, Low) |
| Due Date | Date | Task due date |
| Tags | Multi-select | Labels/categories |

> **Tip:** You can create a new database from the Notion template gallery — the "Simple Task Board" template works well.

## Troubleshooting

- **"Could not find integration"**: Make sure you shared the database with the integration (Step 2)
- **"Unauthorized"**: Check that your `NOTION_TOKEN` is correct and starts with `ntn_`
- **Empty results**: Make sure the database has content and the integration has access
