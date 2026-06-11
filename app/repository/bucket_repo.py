import os
import asyncio
from google.cloud import storage
from app.core.config import get_settings
# We remove logger imports to avoid confusion. Use print for now.

settings = get_settings()

class BucketRepo():
    def __init__(self):
        # We initialize the client ONCE. 
        # The previous "Fresh Client" fix was a hypothesis that failed.
        # We will fix the "Zombie" issue by using a short timeout on the upload itself.
        if os.path.exists(settings.GCP_CREDENTIALS_PATH):
            self.client = storage.Client.from_service_account_json(
                settings.GCP_CREDENTIALS_PATH
            )
        else:
            self.client = storage.Client(project=settings.GCP_PROJECT_ID)
            
        self.bucket = self.client.bucket(settings.GCS_BUCKET_NAME)

    async def upload_json(self, destination_blob_name: str, json_data: str):
        """
        Uploads with an EXTERNAL timeout to guarantee the app never hangs.
        """
        def _sync_upload():
            # Use the existing client (cheaper, safer for threading)
            blob = self.bucket.blob(destination_blob_name)
            
            # Internal timeout (good practice)
            blob.upload_from_string(
                json_data, 
                content_type="application/json", 
                timeout=15 
            )

        print(f"   ☁️ [Thread] Uploading {destination_blob_name}...")

        try:
            # THE FIX: asyncio.wait_for
            # Increased to 60s to handle Cold Start throttling or slow GCS
            await asyncio.wait_for(
                asyncio.to_thread(_sync_upload), 
                timeout=60.0
            )
            print(f"   ✅ Success: Uploaded {destination_blob_name}")
            
        except asyncio.TimeoutError:
            print(f"   ❌ TIMEOUT: Upload for {destination_blob_name} took >60s. Killing it.")
            # We allow the error to bubble up so the pipeline knows it failed
            raise TimeoutError(f"Upload of {destination_blob_name} timed out.")
            
        except Exception as e:
            print(f"   ❌ Upload FAILED for {destination_blob_name}: {e}")
            raise e

    async def download_json(self, source_blob_name: str) -> str:
        """Downloads a blob as a string"""
        def _sync_download():
            blob = self.bucket.blob(source_blob_name)
            return blob.download_as_text()

        try:
            # Cold starts might be slow, giving it 60s
            return await asyncio.wait_for(
                asyncio.to_thread(_sync_download),
                timeout=60.0 
            )
        except asyncio.TimeoutError:
            print(f"   ❌ TIMEOUT: Download for {source_blob_name} took >60s.")
            raise TimeoutError(f"Download of {source_blob_name} timed out.")
        except Exception as e:
            print(f"   ❌ Download FAILED for {source_blob_name}: {e}")
            raise e

    async def delete_blob(self, blob_name: str):
        def _sync_delete():
            blob = self.bucket.blob(blob_name)
            blob.delete()
            
        await asyncio.wait_for(
            asyncio.to_thread(_sync_delete),
            timeout=20.0
        )
        print(f"   🗑️ Deleted {blob_name}.")