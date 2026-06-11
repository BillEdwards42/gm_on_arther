import pytest
from unittest.mock import MagicMock, patch
from app.repository.bucket_repo import BucketRepo

# Add "os.path.exists" to the patches
@patch("app.repository.bucket_repo.os.path.exists") 
@patch("app.repository.bucket_repo.storage.Client")
@patch("app.repository.bucket_repo.settings")
@pytest.mark.asyncio
async def test_upload_json_flow(mock_settings, mock_storage_client, mock_path_exists):
    # 1. SETUP
    # Force the code to believe the credentials file exists
    mock_path_exists.return_value = True 
    
    mock_settings.GCS_BUCKET_NAME = "test-bucket"
    mock_settings.GCP_CREDENTIALS_PATH = "fake_path.json"

    # Mock the chain for Path A (from_service_account_json)
    mock_client_instance = mock_storage_client.from_service_account_json.return_value
    mock_bucket = mock_client_instance.bucket.return_value
    mock_blob = mock_bucket.blob.return_value

    # 2. EXECUTE
    repo = BucketRepo()
    await repo.upload_json("test_file.json", '{"key": "value"}')

    # 3. VERIFY
    # Now this should pass because we forced the 'if' block
    mock_client_instance.bucket.assert_called_with("test-bucket")
    mock_bucket.blob.assert_called_with("test_file.json")
    mock_blob.upload_from_string.assert_called_with(
        '{"key": "value"}', 
        content_type="application/json"
    )

@patch("app.repository.bucket_repo.os.path.exists")
@patch("app.repository.bucket_repo.storage.Client")
@patch("app.repository.bucket_repo.settings")
@pytest.mark.asyncio
async def test_download_json_flow(mock_settings, mock_storage_client, mock_path_exists):
    # Force Path A again
    mock_path_exists.return_value = True
    
    mock_client_instance = mock_storage_client.from_service_account_json.return_value
    mock_blob = mock_client_instance.bucket.return_value.blob.return_value
    mock_blob.download_as_text.return_value = '{"downloaded": "success"}'

    repo = BucketRepo()
    result = await repo.download_json("target_file.json")

    assert result == '{"downloaded": "success"}'