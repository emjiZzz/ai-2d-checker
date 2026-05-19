import os
from pathlib import Path
from typing import List, Dict, Any
from ....logger import logger
from ....config import settings

class VectorPersistence:
    """
    Manages the offline local storage pathing for the vector embeddings database (ChromaDB / LanceDB).
    Enforces sandbox traversal protections.
    """
    
    @staticmethod
    def get_secure_db_path() -> Path:
        """
        Resolves the secure local storage directory for vector memory.
        """
        # Ensure we stay within the designated storage sandbox
        base_dir = Path(settings.STORAGE_ROOT).resolve()
        vector_dir = base_dir / "vector" / "memory_db"
        
        vector_dir.mkdir(parents=True, exist_ok=True)
        return vector_dir

    @staticmethod
    def validate_sandbox_path(target_path: str) -> bool:
        """
        Prevents directory traversal attacks when loading specific vector shards.
        """
        base = Path(settings.STORAGE_ROOT).resolve()
        target = Path(target_path).resolve()
        try:
            return target.is_relative_to(base)
        except AttributeError:
            # Fallback for Python < 3.9
            try:
                target.relative_to(base)
                return True
            except ValueError:
                return False
