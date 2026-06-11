from app.core.config import get_settings
from app.core.logging import logger
import os

# Auth Imports (Firebase - Free Tier)
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, app_check

settings = get_settings()
security_scheme = HTTPBearer()

# --- 1. SECRET MANAGEMENT ---
# Simplified: All secrets are now read directly from environment variables.
# No more Google Secret Manager dependency.
def get_secret(secret_id: str) -> str:
    """Reads a secret from environment variables."""
    value = os.getenv(secret_id, "")
    if not value:
        logger.critical(f"FATAL: Environment variable '{secret_id}' is not set.")
        raise ValueError(f"Missing required environment variable: {secret_id}")
    return value


# --- 2. FIREBASE APP CHECK (Play Integrity) ---
# This is FREE and remains the primary defense against bots.
def verify_app_check(request: Request):
    """
    Validates X-Firebase-App-Check header.
    Ensures the request originates from the genuine compiled mobile app.
    """
    app_check_token = request.headers.get("X-Firebase-App-Check")

    if not app_check_token:
        logger.warning("⛔ Request missing App Check Token (X-Firebase-App-Check header)")
        raise HTTPException(status_code=401, detail="Unauthorized: Missing App Attestation")

    try:
        # Verify the token with Firebase Admin SDK
        # This checks the signature, expiration, and ensures it's from a valid provider (Play Integrity)
        app_check.verify_token(app_check_token)
        return True

    except Exception as e:
        logger.error(f"⛔ Invalid App Check Token: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid App Attestation")


# --- 3. FIREBASE USER AUTH (Anonymous Login JWT) ---
# This is FREE and provides the unique user UID needed for preferences/notifications.
def verify_firebase_user(credentials: HTTPAuthorizationCredentials = Security(security_scheme)) -> str:
    """
    Verifies the Firebase Auth ID Token (JWT).
    Returns the User UID if valid.
    Used for 'Write' operations where we need to know WHO is acting.
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Missing Auth Token")

    try:
        # verify_id_token() handles downloading keys, checking signature,
        # checking expiration, and decoding the payload.
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        return uid

    except Exception as e:
        logger.warning(f"⛔ Invalid Firebase ID Token: {e}")
        raise HTTPException(status_code=401, detail="Invalid User Authentication")