import asyncio
from dotenv import load_dotenv; load_dotenv()

from app.database.engine import get_session_factory
from app.agents.crew import run_agent_query

async def test():
    factory = get_session_factory()
    res = await run_agent_query("What meetings do I have tomorrow?")
    print("FINISHED:", dict(res))
    
if __name__ == "__main__":
    asyncio.run(test())
