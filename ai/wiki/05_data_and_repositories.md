# Data and Repositories

The system utilizes the repository pattern to abstract database operations, making the service layer agnostic to the underlying infrastructure.

## Google Cloud Storage (BucketRepo)
The `BucketRepo` (`app.repository.bucket_repo`) manages communication with GCS.

### Primary Functions:
1. **ML Cache (`ml_cache_v2.json`):** A large serialized JSON object containing the rolling 5-day history for all 5 regions. It is downloaded at the start of the pipeline, updated, and re-uploaded.
2. **Forecast Artifact (`carbon_intensity.json`):** The final calculated product of the pipeline. It contains the current grid status, carbon level, best usage window, and the 24-hour timeline.

### Key Technical Details:
- **Timeouts:** Due to potential hangs during cold starts or network instability, all GCS operations are wrapped in `asyncio.to_thread` and enforced with an `asyncio.wait_for` timeout (60 seconds for uploads/downloads).
- **Authentication:** Dynamically uses a local Service Account file (if available during testing) or defaults to the Cloud Run identity.

## Firestore (FirestoreRepo)
The `FirestoreRepo` (`app.repository.firestore_repo`) manages user data.

### Schema:
Documents are keyed by the Firebase Auth `uid`.
Fields include:
- `uid`: String
- `alert_time`: String (e.g., "08:00")
- `is_active`: Boolean (whether the user wants notifications)
- `created_at` / `updated_at`: Timestamps

### Operations:
- **Upsert:** `create_or_update_user` merges new data with existing data.
- **Querying:** `get_users_by_alert_time` retrieves all users matching a specific time slot where `is_active == True`. This is used by the notification dispatcher.
- **Deletion:** `delete_user` permanently removes the user's document.

## Data Schemas
Pydantic (`app.schemas`) is heavily utilized for "Rich Domain Modeling".
Instead of just validating inputs, models like `WeatherResponse` contain business logic (e.g., `calculate_regional_averages`) to ensure that data transformation logic stays close to the data definition.
