import asyncio
from app.database.engine import init_db
from app.agents.crew import run_agent_query
import uuid

async def main():
    await init_db()
    conv_id = str(uuid.uuid4())
    print(f"Starting debug run for conv: {conv_id}")
    try:
        res = await run_agent_query("brief me about my notion tasks", conv_id)
        print("Success:", res)
    except Exception as e:
        print("ERROR:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
