"""Speech-to-Text Service — converts audio commands to text using Google Cloud STT."""

from __future__ import annotations

import logging
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
from app.config import get_settings

logger = logging.getLogger(__name__)

class SpeechService:
    """Manages audio transcription using Google Cloud Speech-to-Text."""

    def __init__(self):
        self._client = None
        self._project_id = get_settings().google_cloud_project
        self._location = get_settings().google_cloud_location

    @property
    def client(self):
        if self._client is None:
            self._client = speech_v2.SpeechClient()
        return self._client

    async def transcribe_audio(self, audio_content: bytes, language_code: str = "en-US") -> str:
        """Transcribes audio bytes to text.
        
        Args:
            audio_content: Binary audio data (usually WebM/Opus from browser).
            language_code: BCP-47 language tag.
            
        Returns:
            The transcribed text string.
        """
        if not self._project_id:
            logger.warning("⚠️ No Google Cloud Project configured for STT. Simulation only.")
            return "Simulated voice command: Check my schedule for today."

        try:
            # Note: For production, we'd need a recognizer or a specific config
            # This is the V2 'Short Utterance' pattern
            parent = f"projects/{self._project_id}/locations/{self._location}"
            
            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[language_code],
                model="long", # Or 'short' depending on use case
            )
            
            request = cloud_speech.RecognizeRequest(
                recognizer=f"{parent}/recognizers/_", # Use default recognizer
                config=config,
                content=audio_content,
            )
            
            response = self.client.recognize(request=request)
            
            # Combine all transcripts from the results
            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript
            
            logger.info(f"🎤 STT Transcript: {transcript}")
            return transcript.strip()
        except Exception as e:
            logger.error(f"❌ STT Transcription failed: {e}")
            raise e

# Singleton
speech_service = SpeechService()
