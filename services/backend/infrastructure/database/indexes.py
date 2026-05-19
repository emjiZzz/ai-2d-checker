from pymongo import ASCENDING
from ...logger import logger
from .connection import db_manager

async def bootstrap_indexes() -> bool:
    """
    Programmatic index bootstrap checking and indexing performance properties.
    """
    if not db_manager.is_connected or db_manager.db is None:
        logger.warning("Database disconnected. Skipping index bootstrapping.")
        return False

    try:
        logger.info("Verifying database indexes...")
        
        # Explicit index declaration for drawing duplicates check
        drawings_col = db_manager.db["drawings"]
        await drawings_col.create_index([("hash", ASCENDING)], unique=True, name="idx_drawing_hash_unique")
        await drawings_col.create_index([("file_path", ASCENDING)], name="idx_drawing_filepath")
        
        # Audits lookups index
        audits_col = db_manager.db["audit_results"]
        await audits_col.create_index([("drawing_id", ASCENDING)], name="idx_audit_drawing_id")
        
        # Standards index
        standards_col = db_manager.db["standards"]
        await standards_col.create_index([("name", ASCENDING)], name="idx_standard_name")
        
        logger.info("All performance and constraints indexes bootstrapped successfully.")
        return True
    except Exception as e:
        logger.error(f"Index bootstrapping encountered an exception: {str(e)}")
        return False
