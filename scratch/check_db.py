import asyncio
from app.database.engine import get_session_factory
from app.database.models import Conversation
from sqlalchemy import select

async def check_db():
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Conversation))
        rows = result.scalars().all()
        print(f"Total conversations: {len(rows)}")
        for r in rows:
            print(f"- {r.id}: {r.user_query} (Status: {r.status})")

if __name__ == "__main__":
    asyncio.run(check_db())
