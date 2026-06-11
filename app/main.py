from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import os

import firebase_admin
from firebase_admin import credentials as fb_credentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import logger
from app.routers import internal, client

load_dotenv()
settings = get_settings()

# --- Rate Limiter (Global) ---
limiter = Limiter(key_func=get_remote_address)

# --- Scheduler ---
scheduler = AsyncIOScheduler()


async def _run_pipeline_job():
    """Wrapper for APScheduler to call the intelligence pipeline."""
    try:
        from app.services.intelligence import run_intelligence_pipeline
        logger.info("⏰ [APScheduler] Triggering Intelligence Pipeline...")
        await run_intelligence_pipeline()
    except Exception as e:
        logger.error(f"❌ [APScheduler] Pipeline job failed: {e}")


async def _run_notification_job():
    """Wrapper for APScheduler to call the notification dispatcher."""
    try:
        from app.services.notifications import NotificationService
        logger.info("⏰ [APScheduler] Triggering Notification Dispatch...")
        service = NotificationService()
        await service.dispatch_alerts()
    except Exception as e:
        logger.error(f"❌ [APScheduler] Notification job failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---

    # 1. Initialize Firebase Admin SDK (for Auth, App Check, FCM)
    if not firebase_admin._apps:
        try:
            cred_path = settings.FIREBASE_CREDENTIALS_PATH
            if os.path.exists(cred_path):
                cred = fb_credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                # Fallback: Application Default Credentials (if running in GCP)
                firebase_admin.initialize_app()
            logger.info("🔥 Firebase Admin Initialized")
        except Exception as e:
            logger.error(f"❌ Firebase Init Failed: {e}")

    # 2. Initialize PostgreSQL Database (create tables if missing)
    logger.info("🗄️ Initializing Database...")
    await init_db()
    logger.info("✅ Database Ready.")

    # 3. Start APScheduler
    scheduler.add_job(
        _run_pipeline_job,
        'interval',
        minutes=settings.PIPELINE_INTERVAL_MINUTES,
        id='intelligence_pipeline',
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )
    scheduler.add_job(
        _run_notification_job,
        'interval',
        minutes=settings.NOTIFICATION_INTERVAL_MINUTES,
        id='notification_dispatch',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"⏰ APScheduler Started (Pipeline: every {settings.PIPELINE_INTERVAL_MINUTES}m, Notifications: every {settings.NOTIFICATION_INTERVAL_MINUTES}m)")

    yield

    # --- SHUTDOWN ---
    scheduler.shutdown(wait=False)
    logger.info("⏰ APScheduler Shut Down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="3.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan
)

# --- Rate Limiter Setup ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register Routers
app.include_router(internal.router, prefix="/api/v1/internal", tags=["Internal"])
app.include_router(client.router, prefix="/api/v1/client", tags=["Client"])

@app.get("/health")
def health_check():
    """Basic health check."""
    return {"status": "ok"}