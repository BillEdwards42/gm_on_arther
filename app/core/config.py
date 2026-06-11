from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # App Config
    PROJECT_NAME: str = "Green Moment Backend V2"
    LOG_LEVEL: str = "INFO"

    # Database (PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://gm_user:gm_password@db:5432/greenmoment"

    # Local File Storage (mounted Docker volume)
    LOCAL_STORAGE_PATH: str = "/app/data/storage"

    # Firebase (Free Tier - Auth, FCM, App Check)
    # Path to the Firebase Admin SDK service account JSON.
    # This is the ONLY Google credential we still need.
    FIREBASE_CREDENTIALS_PATH: str = "credentials.json"

    # External API Secrets (read from env vars)
    CWA_API_KEY: str = ""

    # Scheduling
    PIPELINE_INTERVAL_MINUTES: int = 10
    NOTIFICATION_INTERVAL_MINUTES: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

@lru_cache
def get_settings():
    return Settings()