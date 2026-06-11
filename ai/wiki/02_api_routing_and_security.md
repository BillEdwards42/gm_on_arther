# API Routing and Security

The FastAPI application uses APIRouters to separate internal tasks from client-facing operations.

## Security Layers

Security is handled via the `app.core.security` module which implements multiple dependency checks.

1. **Secret Management:** Google Secret Manager stores sensitive credentials (like CWA keys and Bright Data proxy passwords). These are fetched dynamically or from environment variables during local testing.
2. **Firebase App Check (`verify_app_check`):** Required for all client endpoints. It validates the `X-Firebase-App-Check` header using Firebase Admin, ensuring the request comes from the genuine compiled mobile app.
3. **Firebase User Auth (`verify_firebase_user`):** Validates the Bearer token (JWT) using `auth.verify_id_token`. Used to extract the `uid` for personalized endpoints (like updating preferences).
4. **Internal Scheduler Auth (`verify_internal_scheduler`):** Required for all internal triggers. It verifies the Google OIDC token signature and explicitly checks that the `email` claim matches the designated Cloud Scheduler Service Account (`settings.SCHEDULER_SERVICE_ACCOUNT_EMAIL`).

## Routers

### Internal Router (`/api/v1/internal`)
Used purely by Google Cloud Scheduler to trigger background work.

- `POST /update-pipeline`
  - **Purpose:** Executes the main ETL and ML forecasting pipeline.
  - **Execution:** Runs synchronously (awaiting `run_intelligence_pipeline()`) to ensure Cloud Run keeps the CPU allocated for the duration of the heavy ML task.
  
- `POST /dispatch-notifications`
  - **Purpose:** Checks if users need to be alerted for the current time slot.
  - **Execution:** Utilizes FastAPI `BackgroundTasks` to free the HTTP response immediately while the push notifications are dispatched asynchronously via FCM.

### Client Router (`/api/v1/client`)
Used by the mobile application.

- `GET /carbon-forecast`
  - **Purpose:** Fetches the latest carbon intensity forecast.
  - **Optimization:** To minimize CPU cycles and memory usage, this endpoint acts as a pass-through. It downloads raw JSON bytes from GCS and returns them directly in a `Response` object with `media_type="application/json"`.

- `POST /preferences`
  - **Purpose:** Updates user settings (alert time, active status).
  - **Logic:** Handles "First Run" logic by applying defaults (e.g., 08:00 alert time) if the user document does not exist in Firestore. It uses `exclude_unset=True` to allow partial updates.

- `DELETE /account`
  - **Purpose:** Permanently deletes a user.
  - **Logic:** Removes the user document from Firestore and deletes the user profile from Firebase Auth simultaneously.
