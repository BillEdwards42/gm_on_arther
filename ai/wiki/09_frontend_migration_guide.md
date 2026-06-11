# Frontend Migration Guide

This guide outlines the changes required in the Flutter frontend application to support the new self-hosted backend architecture.

## 1. Update the Base URL
The backend is no longer hosted on Google Cloud Run. It is now routed securely through a Cloudflare Tunnel to our self-hosted server.

**Action Required:**
Update your API base URL in the Flutter app's networking layer (e.g., Dio, http, or Riverpod config).

- **Old URL:** `https://gm-backend-v2-...-de.a.run.app/api/v1`
- **New URL:** `https://greenmoment.edwardsserver.com/api/v1`

## 2. Authentication & Security Remain Unchanged
The most critical part of this migration is that **the security model has not changed for the client.**

You do **NOT** need to change how you handle:
1. **Firebase App Check:** Keep generating and passing the `X-Firebase-App-Check` header on every request. The self-hosted backend still verifies these against the free-tier Firebase Admin SDK.
2. **Firebase Auth (Anonymous Login):** Continue passing the `Authorization: Bearer <ID_TOKEN>` header for the `/preferences` endpoint. The backend still relies on this to securely identify users.
3. **FCM Push Notifications:** Device tokens still work perfectly. The backend will continue to push alerts using the same Firebase project.

## 3. Handling the Cold Start / Warm-up Period
Because the new server relies on a rolling 5-day cache (720 time steps) to produce its first ML prediction, the `/carbon-forecast` endpoint will return a **503 Service Unavailable** error for the first 5 days of the server's life.

**Action Required:**
Ensure the Flutter app gracefully handles a `503` status code from the `/carbon-forecast` endpoint. It should not crash or show a "red error screen".
Instead, display a friendly fallback UI, such as:
> *"The grid forecast is currently warming up and gathering data. Please check back later!"*

## 4. Endpoints Overview

For confirmation, here are the active client endpoints:

- `GET /client/carbon-forecast`
  - Headers: `X-Firebase-App-Check`
  - Returns: The full ML forecast timeline and optimization window.
- `POST /client/preferences`
  - Headers: `X-Firebase-App-Check`, `Authorization: Bearer <ID_TOKEN>`
  - Body: `{"alert_time": "08:00", "is_active": true, "fcm_token": "..."}`
  - Returns: Success status.
- `DELETE /client/account`
  - Headers: `X-Firebase-App-Check`, `Authorization: Bearer <ID_TOKEN>`
  - Action: Permanently deletes the user's data from PostgreSQL and Firebase Auth.
