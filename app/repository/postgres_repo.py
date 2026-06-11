from datetime import datetime, date
from typing import Optional
from sqlalchemy import select, update, delete
from app.core.database import async_session_factory
from app.core.db_models import User
from app.core.logging import logger


class PostgresRepo:
    """
    Repository for user data backed by PostgreSQL.
    Direct replacement for FirestoreRepo.
    """

    async def create_or_update_user(self, uid: str, data: dict):
        """Creates or updates a user document keyed by uid."""
        async with async_session_factory() as session:
            async with session.begin():
                user = await session.get(User, uid)

                if user:
                    # UPDATE: overwrite only the fields present in data
                    for key, value in data.items():
                        if hasattr(user, key) and key != "uid":
                            setattr(user, key, value)
                    user.updated_at = datetime.utcnow()
                else:
                    # CREATE: insert new row
                    user = User(
                        uid=uid,
                        alert_time=data.get("alert_time", "08:00"),
                        fcm_token=data.get("fcm_token"),
                        is_active=data.get("is_active", True),
                        created_at=data.get("created_at", datetime.utcnow()),
                        updated_at=data.get("updated_at", datetime.utcnow()),
                    )
                    session.add(user)

                logger.info(f"User {uid} saved to PostgreSQL.")

    async def get_user(self, uid: str) -> dict | None:
        """Retrieves a user document."""
        async with async_session_factory() as session:
            user = await session.get(User, uid)
            if user:
                return {
                    "uid": user.uid,
                    "alert_time": user.alert_time,
                    "fcm_token": user.fcm_token,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }
            return None

    async def delete_user(self, uid: str):
        """Deletes a user row."""
        async with async_session_factory() as session:
            async with session.begin():
                stmt = delete(User).where(User.uid == uid)
                await session.execute(stmt)
                logger.info(f"Deleted user {uid} from PostgreSQL.")

    async def get_users_by_alert_time(self, alert_time: str) -> list[dict]:
        """
        Retrieves all active users subscribed to a specific alert time
        who have NOT already been notified today.

        This is the core fix for duplicate notifications:
        We add a WHERE clause checking last_notified_date != today.
        """
        today = date.today()
        async with async_session_factory() as session:
            stmt = (
                select(User)
                .where(User.alert_time == alert_time)
                .where(User.is_active == True)
                .where(
                    (User.last_notified_date == None) | (User.last_notified_date < today)
                )
            )
            result = await session.execute(stmt)
            users = result.scalars().all()

            logger.info(f"Found {len(users)} users for time slot {alert_time} (not yet notified today)")
            return [
                {
                    "uid": u.uid,
                    "alert_time": u.alert_time,
                    "fcm_token": u.fcm_token,
                    "is_active": u.is_active,
                }
                for u in users
            ]

    async def mark_user_notified(self, uid: str):
        """
        Stamps the user with today's date after a successful notification.
        Prevents duplicate alerts for the rest of the day.
        """
        today = date.today()
        async with async_session_factory() as session:
            async with session.begin():
                stmt = (
                    update(User)
                    .where(User.uid == uid)
                    .values(last_notified_date=today)
                )
                await session.execute(stmt)
