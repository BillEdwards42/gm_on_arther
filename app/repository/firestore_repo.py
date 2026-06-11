import os
from google.cloud import firestore
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

class FirestoreRepo():
    def __init__(self):
        # 1. Unified Authentication Logic (Same as BucketRepo)
        if os.path.exists(settings.GCP_CREDENTIALS_PATH):
            logger.info("Firestore: Using local service account file.")
            self.db = firestore.Client.from_service_account_json(
                settings.GCP_CREDENTIALS_PATH
            )
        else:
            logger.info("Firestore: Using Cloud Run default identity.")
            self.db = firestore.Client(project=settings.GCP_PROJECT_ID)
            
        self.collection = self.db.collection(settings.FIRESTORE_COLLECTION)

    async def create_or_update_user(self, uid: str, data: dict):
        """Creates or updates a user document keyed by uid."""
        try:
            # Use await if using an async library, but standard google.cloud.firestore is sync.
            # In FastAPI, standard practice for sync DB calls is to run them directly 
            # or wrap in run_in_executor. For simplicity here, we keep it sync logic 
            # wrapped in async def to satisfy the interface.
            doc_ref = self.collection.document(uid)
            doc_ref.set(data, merge = True)
            logger.info(f"User {uid} saved to firestore.")
        except Exception as e:
            logger.error(f"Failed to save user {uid}: {e}")
            return e

    async def get_user(self, uid: str) -> dict | None:
        """Retrieves a user document."""
        try:
            doc_ref = self.collection.document(uid)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get user {uid}: {e}")
            return None

    async def delete_user(self, uid: str):
        """Deletes the user generated from above testing"""
        try:
            self.collection.document(uid).delete()
            logger.info(f"Deleted user {uid} from Firestore.")
        except Exception as e:
            # Log but don't crash, so Auth deletion can utilize this.
            logger.warning(f"Firestore delete warning for {uid}: {e}")
            # We raise so the caller knows something went wrong, 
            # OR we suppress if we want "Best Effort".
            # "Meticulous" means we should probably raise to inform the client.
            raise e

    async def get_users_by_alert_time(self, alert_time: str) -> list[dict]:
        """
        Retrieves all active users subscribed to a specific alert time.
        """
        try:
            # Note: In a real high-scale app, you'd shard this or use a task queue.
            # For this scale, a direct query is perfectly fine.
            # We filter for:
            # 1. alert_time == TARGET (e.g. "08:00")
            # 2. is_active == True (Don't spam people who turned it off)
            
            # Using synchronous stream() in async wrapper
            query = self.collection.where(field_path="alert_time", op_string="==", value=alert_time)\
                                   .where(field_path="is_active", op_string="==", value=True)
            
            users = []
            docs = query.stream()
            
            for doc in docs:
                users.append(doc.to_dict())
                
            logger.info(f"Found {len(users)} users for time slot {alert_time}")
            return users
            
        except Exception as e:
            logger.error(f"Failed to query users for time {alert_time}: {e}")
            return []