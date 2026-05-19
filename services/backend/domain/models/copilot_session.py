from datetime import datetime
from typing import List, Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING

class CopilotMessage(Document):
    """Stores individual contextual chat messages for the Copilot session."""
    session_id: str = Field(..., description="Link to CopilotSession")
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., description="Text content of the message")
    citations: List[str] = Field(default_factory=list, description="IDs of cited standards or geometry")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "copilot_messages"
        indexes = [
            IndexModel([("session_id", ASCENDING)])
        ]

class CopilotSession(Document):
    """Maintains the persistent engineering conversation memory."""
    drawing_id: str = Field(..., description="The DXF drawing currently being reviewed")
    user_id: str = Field(..., description="Local reviewer ID")
    title: str = Field(default="New Engineering Chat")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "copilot_sessions"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)])
        ]
