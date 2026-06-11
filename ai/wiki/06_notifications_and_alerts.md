# Notifications and Alerts

The Notification Service (`app.services.notifications`) bridges the gap between the generated ML forecasts and the end users, ensuring they are alerted when the grid is "greenest".

## The Notification Workflow

1. **Trigger:** Google Cloud Scheduler hits `/api/v1/internal/dispatch-notifications` every 10 minutes. The router passes the workload to FastAPI's `BackgroundTasks`.
2. **User Query:** The service queries Firestore for all users whose `alert_time` matches the current system time (rounded to 10-minute intervals) and who have `is_active` set to True.
3. **Artifact Retrieval:** It fetches the latest `carbon_intensity.json` from GCS to extract the `best_usage_window`.
4. **Message Construction:** Translates the best window into a localized, user-friendly message.
5. **Dispatch:** Uses Firebase Admin SDK (`firebase_admin.messaging`) to send push notifications directly to the users' devices via their FCM (Firebase Cloud Messaging) tokens.

## Message Construction Logic

The `_construct_message` function generates actionable advice.
- **Window Found:** It extracts the start and end times of the best window. It also checks if the window starts on the following day relative to Taiwan Time (UTC+8). If so, it prepends "明日的" (Tomorrow's) to the message.
  - *Example:* "未來24H內的減碳時刻為08:00 - 10:00，在該時段用電的排碳較低!"
- **Fallback:** If no optimal window is calculated, it defaults to a safe message: "目前電網供應穩定，是使用電器的好時機！"

## Firebase Cloud Messaging (FCM)
The actual dispatch uses the `send()` function from the `messaging` module. The payload includes:
- The user's specific FCM `token`.
- The `Notification` body containing the constructed message.
- A data payload `{"click_action": "FLUTTER_NOTIFICATION_CLICK"}` to instruct the Flutter mobile app on how to handle the notification tap.
