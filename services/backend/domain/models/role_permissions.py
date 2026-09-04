from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class RolePermissionsDocument(Document):
    role: str = Field(..., description="Role name: admin or user")
    allowed_routes: list[str] = Field(default_factory=list, description="Endpoints allowed for this role")
    allowed_actions: list[str] = Field(default_factory=list, description="Permitted capabilities/operations")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Permission definition creation time")

    class Settings:
        name = "role_permissions"
        indexes = [
            IndexModel([("role", ASCENDING)], unique=True)
        ]
