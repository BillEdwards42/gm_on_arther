from datetime import datetime, timezone, timedelta, date
from typing import Optional
from firebase_admin import messaging
from app.core.logging import logger
from app.repository.postgres_repo import PostgresRepo
from app.repository.local_file_repo import LocalFileRepo
from app.schemas.forecast import CarbonLevel, PredictionArtifact, OptimizationWindow

class NotificationService:
    def __init__(self):
        self.repo = PostgresRepo()
        self.bucket = LocalFileRepo()

    def _get_current_time_bucket(self) -> str:
        """
        Returns the current time in HH:MM format (24h), rounded down
        to the nearest 10-minute interval.
        e.g., 08:03 -> "08:00", 08:17 -> "08:10"
        """
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        # Round DOWN to nearest 10-minute interval to match user-set times
        rounded_minute = (now.minute // 10) * 10
        return f"{now.hour:02d}:{rounded_minute:02d}"

    def _construct_message(self, window: Optional[OptimizationWindow]) -> str:
        """
        Creates a punchy, actionable message using the BEST usage window.
        Format: "未來24H內的減碳時刻為XX:XX - YY:YY，建議在該時段使用家電!"
        """
        if window:
            # Determine if it's Tomorrow
            tz = timezone(timedelta(hours=8))
            now_tw = datetime.now(tz)

            prefix = ""
            if window.start_time.date() > now_tw.date():
                prefix = "明日的"

            start_str = window.start_time.strftime("%H:%M")
            end_str = window.end_time.strftime("%H:%M")
            return f"未來24H內的減碳時刻為{prefix}{start_str} - {end_str}，在該時段用電的排碳較低!"
        else:
            # Fallback if no window is available
            return "目前電網供應穩定，是使用電器的好時機！"

    async def dispatch_alerts(self):
        """
        Main entry point. Queries users and sends alerts.

        DUPLICATE NOTIFICATION FIX:
        The PostgresRepo.get_users_by_alert_time() query now filters out users
        whose `last_notified_date` is today. After a successful send, we stamp
        the user with today's date via `mark_user_notified()`.
        This guarantees at most ONE notification per user per day, regardless
        of how many times the scheduler fires.
        """
        current_time = self._get_current_time_bucket()
        logger.info(f"🔔 Notification Service: Checking for users at {current_time}...")

        # 1. Fetch Forecast Artifact for "Best Window" data
        best_window = None
        try:
            json_str = await self.bucket.download_json("carbon_intensity.json")
            artifact = PredictionArtifact.model_validate_json(json_str)
            best_window = artifact.best_usage_window
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch best usage window for notification: {e}")

        # 2. Get Users (already filtered: is_active=True AND not notified today)
        users = await self.repo.get_users_by_alert_time(current_time)

        if not users:
            logger.info("   No users to notify at this timeslot.")
            return

        # 3. Prepare Message (Localized)
        message = self._construct_message(best_window)

        # 4. Dispatch
        success_count = 0
        for user in users:
            fcm_token = user.get('fcm_token')
            uid = user.get('uid')

            if not fcm_token:
                logger.warning(f"   ⚠️ User {uid} has no FCM token. Skipping.")
                continue

            try:
                # Real Send
                fcm_msg = messaging.Message(
                    token=fcm_token,
                    notification=messaging.Notification(
                        body=message
                    ),
                    data={"click_action": "FLUTTER_NOTIFICATION_CLICK"}
                )
                response = messaging.send(fcm_msg)
                logger.info(f"   🚀 [FCM Sent] Message ID: {response}")

                # 5. STAMP the user so they don't get notified again today
                await self.repo.mark_user_notified(uid)
                success_count += 1

            except Exception as e:
                logger.error(f"Failed to send to user {uid}: {e}")

        logger.info(f"✅ Dispatched {success_count}/{len(users)} alerts.")
        return {"status": "success", "sent_count": success_count}
