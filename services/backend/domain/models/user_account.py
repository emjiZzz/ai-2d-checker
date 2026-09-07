from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class UserAccountDocument(Document):
    username: str = Field(..., description="Unique username/email for identity")
    hashed_password: str = Field(..., description="Bcrypt hashed password")
    role: str = Field(..., description="Account role: admin or user")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation time")
    last_login: datetime | None = Field(None, description="Last login timestamp")
    active: bool = Field(True, description="Whether the account is active")
    permissions: list[str] = Field(default_factory=list, description="Explicit account permission overrides")

    class Settings:
        name = "user_accounts"
        indexes = [
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("role", ASCENDING)]),
            IndexModel([("active", ASCENDING)])
        ]
