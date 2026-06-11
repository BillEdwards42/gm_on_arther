import os
import aiofiles
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


class LocalFileRepo:
    """
    Repository for JSON artifacts stored on the local filesystem.
    Direct replacement for BucketRepo (Google Cloud Storage).

    Files are stored in the directory specified by LOCAL_STORAGE_PATH,
    which is expected to be a mounted Docker volume for persistence.
    """

    def __init__(self):
        self.base_path = settings.LOCAL_STORAGE_PATH
        # Ensure the storage directory exists
        os.makedirs(self.base_path, exist_ok=True)

    def _resolve_path(self, filename: str) -> str:
        return os.path.join(self.base_path, filename)

    async def upload_json(self, destination_filename: str, json_data: str):
        """Writes a JSON string to a local file."""
        path = self._resolve_path(destination_filename)
        try:
            async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
                await f.write(json_data)
            logger.info(f"   ✅ Saved {destination_filename} to local storage.")
        except Exception as e:
            logger.error(f"   ❌ Failed to save {destination_filename}: {e}")
            raise e

    async def download_json(self, source_filename: str) -> str:
        """Reads a JSON string from a local file."""
        path = self._resolve_path(source_filename)
        try:
            async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            return content
        except FileNotFoundError:
            logger.warning(f"   ⚠️ File not found: {source_filename}")
            raise
        except Exception as e:
            logger.error(f"   ❌ Failed to read {source_filename}: {e}")
            raise e

    async def delete_blob(self, filename: str):
        """Deletes a local file."""
        path = self._resolve_path(filename)
        try:
            os.remove(path)
            logger.info(f"   🗑️ Deleted {filename}.")
        except FileNotFoundError:
            logger.warning(f"   ⚠️ File not found for deletion: {filename}")
        except Exception as e:
            logger.error(f"   ❌ Failed to delete {filename}: {e}")
            raise e
