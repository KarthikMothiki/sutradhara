import pytest
from unittest.mock import MagicMock, patch
from app.services.cloud_storage import CloudStorageService
from app.services.speech_service import SpeechService

@pytest.mark.asyncio
async def test_cloud_storage_upload():
    """Test GCS upload logic with a mocked client."""
    with patch("google.cloud.storage.Client") as mock_client:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_client.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        
        service = CloudStorageService()
        # Set bucket name to trigger real logic path
        service._bucket_name = "test-bucket"
        
        content = b"test content"
        filename = "test.jpg"
        
        uri = await service.upload_file(content, filename, "image/jpeg")
        
        # Verify blob interaction (with uuid prefix)
        assert mock_bucket.blob.called
        args, kwargs = mock_bucket.blob.call_args
        assert filename in args[0]
        assert "uploads/" in args[0]
        
        mock_blob.upload_from_string.assert_called()
        assert uri.startswith("gs://test-bucket/")

@pytest.mark.asyncio
async def test_speech_service_transcribe():
    """Test Speech-to-Text service with a mocked V2 client."""
    # The code uses speech_v2.SpeechClient (sync)
    with patch("google.cloud.speech_v2.SpeechClient") as mock_speech:
        mock_instance = MagicMock()
        mock_speech.return_value = mock_instance
        
        # Mock the recognize response
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(alternatives=[MagicMock(transcript="Hello Sutradhara")])
        ]
        mock_instance.recognize.return_value = mock_response
        
        service = SpeechService()
        service._project_id = "test-project" # Trigger real logic path
        service._location = "us-central1"
        
        transcript = await service.transcribe_audio(b"fake audio data")
        
        assert transcript == "Hello Sutradhara"
        mock_instance.recognize.assert_called()
