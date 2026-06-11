from sqlalchemy import String, Boolean, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, date
from typing import Optional

from app.core.database import Base


class User(Base):
    """
    ORM model for user preferences and notification subscriptions.
    Replaces the Firestore 'users_v2' collection.
    """
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(String, primary_key=True)
    alert_time: Mapped[str] = mapped_column(String(5), default="08:00")
    fcm_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- FIX for duplicate notifications ---
    # Tracks the last date this user was successfully notified.
    # The notification service checks this before sending to prevent
    # multiple alerts on the same day due to scheduler retries or clock drift.
    last_notified_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    def __repr__(self):
        return f"<User uid={self.uid} alert_time={self.alert_time} active={self.is_active}>"
