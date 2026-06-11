# Architecture Overview

The Green Moment Backend V2 is a Python-based microservice designed to predict Taiwan's electrical grid carbon intensity and alert users to optimal "green" usage windows.

## High-Level System Design

The system runs on **Google Cloud Platform (GCP)** and is orchestrated primarily as a serverless containerized application.

1. **Web Framework:** FastAPI provides high-performance, asynchronous HTTP endpoints.
2. **Compute Environment:** Google Cloud Run (Fully managed, scalable container execution).
3. **Trigger Mechanism:** Google Cloud Scheduler acts as a cron job to trigger the internal pipelines at set intervals.
4. **Data Storage:** 
    - **Google Cloud Storage (GCS):** Stores the ML cache and the finalized carbon forecast JSON artifact.
    - **Firestore (NoSQL):** Stores user preferences and alert subscription configurations.
5. **Authentication & Security:**
    - **Client-side:** Firebase App Check (prevents bot abuse) and Firebase Auth JWT (user identity).
    - **Internal-side:** Google OIDC token verification for Scheduler triggers.
6. **Push Notifications:** Firebase Cloud Messaging (FCM) is used to dispatch alerts to mobile devices.

## Core Workflow

The backend operates on two primary tracks: an internal asynchronous processing track, and a synchronous client-facing track.

### 1. Internal Pipeline (The "Intelligence" Track)
Triggered automatically by Cloud Scheduler every 10 minutes.
- **Data Fetching:** Pulls real-time generation data from Taipower (via Bright Data proxy) and weather data from the Central Weather Administration (CWA).
- **Feature Engineering:** Aggregates data by region (North, Central, South, East, Other), computes time-based cyclical features, and performs cross-regional coupling.
- **ML Inference:** Loads pre-trained PyTorch models (`Huber_model`) to predict a 24-hour (144-step) forecast across 13 fuel types.
- **Artifact Generation:** Computes carbon intensity from the forecast mix, identifies the best 2-hour usage window within active hours (07:00 - 22:00), and saves the results as `carbon_intensity.json` to GCS.

### 2. Notification Dispatch Track
Triggered automatically by Cloud Scheduler to check for pending alerts.
- Queries Firestore for users subscribed to the current time slot.
- Fetches the latest `carbon_intensity.json` artifact to retrieve the optimal usage window.
- Formats a localized message (e.g., "未來24H內的減碳時刻為...").
- Dispatches push notifications via FCM to the users' devices.

### 3. Client Interaction Track
Invoked on-demand by the mobile application.
- **Forecast Retrieval:** The `/api/v1/client/carbon-forecast` endpoint passes through the pre-calculated `carbon_intensity.json` directly from GCS to the client, ensuring minimal latency and CPU usage.
- **User Management:** Endpoints to create/update alert preferences in Firestore and permanently delete user accounts (from both Firestore and Firebase Auth).
