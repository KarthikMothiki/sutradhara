import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.agents.crew import run_agent_query

@pytest.mark.asyncio
async def test_run_agent_query_multimodal():
    """Verify that run_agent_query accepts image_uris and orchestrates agents."""
    with patch("app.agents.crew._session_service") as mock_session_service:
        mock_session_service.create_session = AsyncMock(return_value=MagicMock(id="new_session"))
        
        with patch("app.agents.crew._get_runner") as mock_runner:
            mock_runner_instance = MagicMock()
            mock_runner.return_value = mock_runner_instance
            
            # Mock the async generator for run_async
            async def mock_run_async(*args, **kwargs):
                # Yield a mock event that has content.parts with a text part
                part = MagicMock()
                # Set attributes so hasattr/getattr work as expected
                part.configure_mock(text="I see your image.", function_call=None, function_response=None)
                
                event = MagicMock()
                event.content.parts = [part]
                yield event
            
            mock_runner_instance.run_async = mock_run_async
            
            query = "What's in this image?"
            image_uris = ["gs://bucket/image.jpg"]
            
            # We need to mock trace_service to avoid real network calls
            with patch("app.services.trace_service.trace_service.emit_response_chunk", new_callable=AsyncMock) as mock_emit:
                result = await run_agent_query(
                    query=query,
                    conversation_id="test_conv",
                    image_uris=image_uris
                )
                
                assert "response" in result
                assert "I see your image" in result["response"]
                # Verify streaming chunk was emitted
                mock_emit.assert_called()

@pytest.mark.asyncio
async def test_run_agent_query_session_reuse():
    """Verify that ADK session is reused when session_id is provided."""
    with patch("app.agents.crew._session_service") as mock_session_service:
        # Use AsyncMock for async methods
        mock_session_service.get_session = AsyncMock(return_value=MagicMock(id="existing_session"))
        
        with patch("app.agents.crew._get_runner") as mock_runner:
            mock_runner_instance = MagicMock()
            mock_runner.return_value = mock_runner_instance
            
            async def mock_run_async(*args, **kwargs):
                part = MagicMock()
                part.configure_mock(text="Reusing session.", function_call=None, function_response=None)
                event = MagicMock()
                event.content.parts = [part]
                yield event
            mock_runner_instance.run_async = mock_run_async

            await run_agent_query(
                query="Hello",
                session_id="existing_session"
            )
            
            mock_session_service.get_session.assert_called()
