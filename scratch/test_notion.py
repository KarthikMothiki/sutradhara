import asyncio
import httpx
from app.config import get_settings
from dotenv import load_dotenv

load_dotenv()

async def test_notion():
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    db_id = settings.notion_database_id
    body = {
        "page_size": 20,
        "filter": {
            "property": "Status",
            "status": {"equals": "Pending"}
        }
    }
    
    print(f"Testing Notion connection with DB ID: {db_id}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=headers,
                json=body,
                timeout=15,
            )
            print("Status:", resp.status_code)
            print("Response:", resp.text)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_notion())
