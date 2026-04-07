import asyncio
from dotenv import load_dotenv; load_dotenv()

from app.agents.crew import _get_runner, APP_NAME

async def test():
    runner = _get_runner()
    from google.genai.types import Content, Part
    
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id="user",
        session_id="test-session-123",
    )
    
    user_content = Content(
        role="user",
        parts=[Part(text="Schedule a sync meeting for tomorrow at 2pm.")],
    )
    
    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=user_content,
    ):
        author = getattr(event, "author", "UNKNOWN")
        print(f"Author: {author}")
        if event.content and event.content.parts:
            for p in event.content.parts:
                print(f"  Part: {p}")

if __name__ == "__main__":
    asyncio.run(test())
