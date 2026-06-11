from fastapi import APIRouter, HTTPException
from app.services.intelligence import run_intelligence_pipeline
from app.core.logging import logger

router = APIRouter()

@router.post("/update-pipeline")
async def trigger_pipeline():
    """
    Internal Endpoint: Can be triggered manually for debugging.
    In production, APScheduler calls run_intelligence_pipeline() directly.
    No external auth needed since this is only reachable via localhost
    (Cloudflare Tunnel does not expose /api/v1/internal).
    """
    try:
        logger.info("⏳ Manual Pipeline Trigger Received. Executing synchronously...")

        result = await run_intelligence_pipeline()

        return {"status": "success", "result": result}

    except Exception as e:
        logger.error(f"Failed to trigger pipeline: {e}")
        raise HTTPException(status_code=500, detail="Internal Trigger Failed")

@router.post("/dispatch-notifications")
async def trigger_notifications():
    """
    Internal Endpoint: Can be triggered manually for debugging.
    In production, APScheduler calls dispatch_alerts() directly.
    """
    try:
        from app.services.notifications import NotificationService

        logger.info("🔔 Manual Notification Trigger Received.")
        service = NotificationService()

        result = await service.dispatch_alerts()

        return {"status": "success", "result": result}

    except Exception as e:
        logger.error(f"Failed to trigger notifications: {e}")
        raise HTTPException(status_code=500, detail="Internal Trigger Failed")