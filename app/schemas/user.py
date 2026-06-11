from pydantic import BaseModel, Field, field_validator, ConfigDict
import re
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    """
    Shared properties.
    """
    alert_time: Optional[str] = Field(None, description = "Target notification time in HH:MM format (24 hour)")
    fcm_token: Optional[str] = Field(None, description = "Firebase Cloud Messaging token for push notifications")
    is_active: Optional[bool] = Field(True)

    @field_validator("alert_time")
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', v):
            raise ValueError("Time must be in HH:MM format")
        return v
    
class UserUpdate(UserBase):
    """
    Payload for updating user preferences. All fields optional.
    """
    pass

class UserInDB(UserBase):
    """
    Represents a user object as stored in the database.
    Enforces that stored data is valid (though Firestore is schemaless, this validates our reads).
    """
    uid: str
    alert_time: str = "08:00" # Default for DB reads if missing
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
