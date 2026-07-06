from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class UserSessionDocument(Document):
    token: str = Field(..., description="Encrypted session token / JWT")
    user_id: str = Field(..., description="String reference to user account ID")
    username: str = Field(..., description="Associated account username")
    role: str = Field(..., description="Associated account role: admin or user")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    active: bool = Field(True, description="Whether this session is active")

    class Settings:
        name = "user_sessions"
        indexes = [
            IndexModel([("token", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)])
        ]
