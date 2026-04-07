import asyncio
from app.database.engine import get_session_factory
from app.database.models import WorkflowRun
from sqlalchemy import select

async def main():
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(10))
        for wr in result.scalars().all():
            print(f"WR: agent={wr.agent_name}, tool={wr.tool_called}, data={wr.input_data}")

asyncio.run(main())
