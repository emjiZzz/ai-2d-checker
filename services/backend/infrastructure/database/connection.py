import asyncio
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

# Monkey patch AsyncIOMotorClient to prevent Beanie compatibility issues with PyMongo 4+ / Motor 3+
if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *args, **kwargs: None
from ...config import settings
from ...logger import logger
from ...domain.models import __all_models__

class DatabaseConnectionManager:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.connected = False
        self._lock = asyncio.Lock()
        self.retry_count = 0  # track failed connection attempts
        self.total_attempts = 0  # track total connection attempts

    async def connect(self, max_retries: int = 5, initial_delay: float = 1.0) -> bool:
        """
        Connect to local MongoDB using Motor + Beanie.
        Includes graceful exponential backoff retry loop.
        """
        async with self._lock:
            if self.connected and self.client:
                return True

            logger.info("Initializing database connection manager...")
            delay = initial_delay
            
            for attempt in range(1, max_retries + 1):
                self.total_attempts = attempt
                try:
                    logger.info(
                        f"Connecting to MongoDB (Attempt {attempt}/{max_retries}) on URI: "
                        f"{settings.MONGO_URI.split('@')[-1]}"  # Safe log masking credentials
                    )
                    
                    # Create asynchronous motor client
                    self.client = AsyncIOMotorClient(
                        settings.MONGO_URI,
                        serverSelectionTimeoutMS=2000,  # 2 second connect timeout
                        uuidRepresentation="standard"
                    )
                    
                    # Ping database to confirm loopback validity
                    await self.client.admin.command("ping")
                    
                    # Diagnostics logging
                    try:
                        build_info = await self.client.admin.command("buildInfo")
                        mongo_version = build_info.get("version", "unknown")
                        logger.info(f"MongoDB Server Diagnostics: Version {mongo_version}")
                    except Exception as diag_e:
                        logger.warning(f"Could not retrieve MongoDB diagnostics buildInfo: {str(diag_e)}")
                    
                    # Initialize Beanie ODM document schema mapping
                    self.db = self.client[settings.MONGO_DB_NAME]
                    await init_beanie(
                        database=self.db,
                        document_models=__all_models__
                    )
                    
                    # Seed initial enterprise roles & accounts
                    try:
                        from ...domain.models.user_account import UserAccountDocument
                        from ...core.auth import hash_password

                        admin_exists = await UserAccountDocument.find_one(UserAccountDocument.username == "admin")
                        if not admin_exists:
                            admin_user = UserAccountDocument(
                                username="admin",
                                hashed_password=hash_password("admin123"),
                                role="admin",
                                permissions=["all"]
                            )
                            await admin_user.save()
                            logger.info("Seeded default administrator account ('admin' / 'admin123') successfully.")
                        
                        engineer_exists = await UserAccountDocument.find_one(UserAccountDocument.username == "engineer")
                        if not engineer_exists:
                            engineer_user = UserAccountDocument(
                                username="engineer",
                                hashed_password=hash_password("engineer123"),
                                role="user",
                                permissions=["audit"]
                            )
                            await engineer_user.save()
                            logger.info("Seeded default engineering user account ('engineer' / 'engineer123') successfully.")
                    except Exception as seed_err:
                        logger.warning(f"Failed to verify or seed default user accounts: {str(seed_err)}")

                    self.connected = True
                    logger.info(
                        f"Successfully connected to MongoDB database '{settings.MONGO_DB_NAME}' "
                        f"and initialized {len(__all_models__)} document models."
                    )
                    return True
                    
                except Exception as e:
                    self.retry_count += 1
                    logger.warning(
                        f"Database connection attempt {attempt} failed: {str(e)}"
                    )
                    self.connected = False
                    if self.client:
                        self.client.close()
                        self.client = None
                    
                    if attempt == max_retries:
                        logger.error(
                            "Maximum database connection attempts reached. Operating in disconnected fallback mode."
                        )
                        return False
                    
                    logger.info(f"Retrying connection in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                    delay *= 2.0  # Exponential backoff multiplier

            return False

    async def disconnect(self) -> None:
        """
        Safe shutdown cleanup of async client database threads.
        """
        async with self._lock:
            if self.client:
                logger.info("Closing asynchronous MongoDB client connections...")
                self.client.close()
                self.client = None
                self.db = None
                self.connected = False
                logger.info("Database client disconnected gracefully.")

    @property
    def is_connected(self) -> bool:
        return self.connected

db_manager = DatabaseConnectionManager()
