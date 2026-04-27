"""Cloud Storage Service — handles deterministic file uploads to GCS."""

from __future__ import annotations

import logging
import uuid
from google.cloud import storage
from app.config import get_settings

logger = logging.getLogger(__name__)

class CloudStorageService:
    """Manages file uploads to Google Cloud Storage."""

    def __init__(self):
        self._client = None
        self._bucket_name = get_settings().google_cloud_bucket

    @property
    def client(self):
        if self._client is None:
            self._client = storage.Client()
        return self._client

    async def upload_file(self, content: bytes, filename: str, content_type: str) -> str:
        """Uploads file content to GCS and returns the gs:// URI.
        
        Args:
            content: Binary content of the file.
            filename: Original filename or desired name.
            content_type: MIME type of the file.
            
        Returns:
            The GCS URI (gs://bucket/name).
        """
        if not self._bucket_name:
            logger.warning("⚠️ No GCS bucket configured. Falling back to local/ephemeral simulation.")
            return f"simulated://{filename}"

        try:
            bucket = self.client.bucket(self._bucket_name)
            
            # Generate a unique path to avoid collisions
            unique_name = f"uploads/{uuid.uuid4()}-{filename}"
            blob = bucket.blob(unique_name)
            
            # Uploading synchronously for simplicity (can be moved to executor if needed)
            blob.upload_from_string(content, content_type=content_type)
            
            gcs_uri = f"gs://{self._bucket_name}/{unique_name}"
            logger.info(f"✅ File uploaded to {gcs_uri}")
            return gcs_uri
        except Exception as e:
            logger.error(f"❌ Failed to upload to GCS: {e}")
            raise e

# Singleton
cloud_storage_service = CloudStorageService()
