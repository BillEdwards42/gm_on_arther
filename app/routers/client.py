from fastapi import APIRouter, Depends, HTTPException, Response
from datetime import datetime
from firebase_admin import auth
from app.core.security import verify_app_check
from app.core.security import verify_firebase_user
from app.core.logging import logger
from app.schemas.user import UserUpdate
from app.repository.local_file_repo import LocalFileRepo
from app.repository.postgres_repo import PostgresRepo

router = APIRouter()

@router.get("/carbon-forecast", dependencies=[Depends(verify_app_check)])
async def get_forecast():
    """
    Client Endpoint: Fetches the pre-calculated artifact.
    Optimization: Returns raw JSON bytes directly from local storage (Pass-through).
    This avoids parsing (CPU) and re-serializing the data.
    """
    try:
        repo = LocalFileRepo()
        # Returns the raw JSON string from local storage
        json_str = await repo.download_json("carbon_intensity.json")

        # Return raw content with correct media type.
        # Fast, cheap, and efficient.
        return Response(content=json_str, media_type="application/json")

    except Exception as e:
        logger.error(f"Client Fetch Failed: {e}")
        # Return 503 (Service Unavailable) rather than 500
        raise HTTPException(status_code=503, detail="Forecast unavailable")

@router.post("/preferences", dependencies=[Depends(verify_app_check)])
async def update_preferences(
    user_data: UserUpdate,
    uid: str = Depends(verify_firebase_user)
):
    """
    Client Endpoint: Updates user preferences (Alert time, Active status).
    Protected by Firebase User Auth (JWT).
    Handles 'First Run' registration by applying defaults if user doesn't exist.
    """
    try:
        logger.info(f"🔹 Received /preferences request for UID: {uid}")
        repo = PostgresRepo()

        # 1. Fetch existing user to determine if this is a Create or Update
        current_user = await repo.get_user(uid)
        logger.info(f"   🔍 User Exists? {bool(current_user)}")

        # 2. Prepare payload
        # exclude_unset=True allows sending PARTIAL updates (e.g. just toggling is_active)
        payload = user_data.model_dump(exclude_unset=True)
        now = datetime.now()

        final_data = {}

        if not current_user:
            # --- CREATE NEW USER (BOOTSTRAP) ---
            logger.info(f"   ✨ Bootstrapping NEW user in PostgreSQL: {uid}")
            # Apply Defaults
            final_data = {
                "uid": uid,
                "alert_time": "08:00",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                **payload # Override defaults if client specifically sent something
            }

            # Ensure critical fields exist (Double check)
            if "alert_time" not in final_data: final_data["alert_time"] = "08:00"

        else:
            # --- UPDATE EXISTING USER ---
            final_data = {
                **current_user, # Keep existing data
                **payload,      # Overwrite with new data
                "updated_at": now
            }

        # 3. Save to PostgreSQL
        await repo.create_or_update_user(uid, final_data)

        return {"status": "success", "message": "User settings saved", "active_alert_time": final_data.get("alert_time")}

    except Exception as e:
        logger.error(f"Failed to update preferences for {uid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save preferences")

@router.delete("/account", dependencies=[Depends(verify_app_check)])
async def delete_account(
    uid: str = Depends(verify_firebase_user)
):
    """
    Client Endpoint: PERMANENTLY deletes the user account.
    1. Deletes PostgreSQL Data.
    2. Deletes Firebase Auth User.
    """
    try:
        repo = PostgresRepo()

        # 1. Delete PostgreSQL Data
        await repo.delete_user(uid)

        # 2. Delete Firebase Auth User
        auth.delete_user(uid)

        logger.info(f"🗑️ Account deleted for {uid}")
        return {"status": "success", "message": "Account deleted"}

    except Exception as e:
        logger.error(f"Failed to delete account {uid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account")