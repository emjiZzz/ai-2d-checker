import asyncio

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

# Monkey patch AsyncIOMotorClient to prevent Beanie compatibility issues with PyMongo 4+ / Motor 3+
if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *args, **kwargs: None
from ...config import settings
from ...domain.models import __all_models__
from ...logger import logger


class DatabaseConnectionManager:
    def __init__(self):
        self.client: AsyncIOMotorClient | None = None
        self.db = None
        self.connected = False
        self.active_uri: str | None = None
        self.is_fallback: bool = False
        self._lock = asyncio.Lock()
        self.retry_count = 0  # track failed connection attempts
        self.total_attempts = 0  # track total connection attempts

    async def connect(self, max_retries: int = 2, initial_delay: float = 0.5) -> bool:
        """
        Connect to MongoDB using Motor + Beanie.
        First tries primary MONGO_URI (e.g. Cloud Atlas). If unreachable, seamlessly
        falls back to MONGO_FALLBACK_URI (e.g. Local MongoDB).
        """
        async with self._lock:
            if self.connected and self.client:
                return True

            logger.info("Initializing database connection manager...")
            
            # Formulate candidate connection list: [Primary, Fallback]
            candidate_uris: list[tuple[str, bool]] = [(settings.MONGO_URI, False)]
            fallback_uri = getattr(settings, "MONGO_FALLBACK_URI", "mongodb://127.0.0.1:27017")
            if fallback_uri and fallback_uri.strip() != settings.MONGO_URI.strip():
                candidate_uris.append((fallback_uri, True))

            for uri, is_fallback in candidate_uris:
                mode_label = "Local Fallback" if is_fallback else "Primary"
                masked_uri = uri.split("@")[-1]
                logger.info(f"Attempting {mode_label} MongoDB connection to: {masked_uri}")

                delay = initial_delay
                for attempt in range(1, max_retries + 1):
                    self.total_attempts += 1
                    try:
                        timeout_ms = 4000 if ("mongodb+srv://" in uri or not is_fallback) else 2000
                        self.client = AsyncIOMotorClient(
                            uri,
                            serverSelectionTimeoutMS=timeout_ms,
                            uuidRepresentation="standard"
                        )
                        
                        # Ping database to confirm validity
                        await self.client.admin.command("ping")
                        
                        # Diagnostics logging
                        try:
                            build_info = await self.client.admin.command("buildInfo")
                            mongo_version = build_info.get("version", "unknown")
                            logger.info(f"MongoDB ({mode_label}) Server Diagnostics: Version {mongo_version}")
                        except Exception as diag_e:
                            logger.warning(f"Could not retrieve MongoDB diagnostics buildInfo: {str(diag_e)}")
                        
                        # Initialize Beanie ODM document schema mapping
                        self.db = self.client[settings.MONGO_DB_NAME]
                        await init_beanie(
                            database=self.db,
                            document_models=__all_models__
                        )
                        
                        self.active_uri = uri
                        self.is_fallback = is_fallback
                        self.connected = True
                    
                        # Seed initial enterprise roles & accounts.
                        try:
                            import os

                            from ...core.auth import hash_password
                            from ...domain.models.user_account import UserAccountDocument

                            DEFAULT_ADMIN_PASSWORD = "admin123"
                            DEFAULT_ENGINEER_PASSWORD = "engineer123"

                            seeded_with_defaults = []

                            admin_exists = await UserAccountDocument.find_one(UserAccountDocument.username == "admin")
                            if not admin_exists:
                                admin_password = os.environ.get("SEED_ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD
                                admin_user = UserAccountDocument(
                                    username="admin",
                                    hashed_password=hash_password(admin_password),
                                    role="admin",
                                    permissions=["all"]
                                )
                                await admin_user.save()
                                if admin_password == DEFAULT_ADMIN_PASSWORD:
                                    seeded_with_defaults.append("admin")
                                else:
                                    logger.info("Seeded administrator account from SEED_ADMIN_PASSWORD.")

                            engineer_exists = await UserAccountDocument.find_one(UserAccountDocument.username == "engineer")
                            if not engineer_exists:
                                engineer_password = os.environ.get("SEED_ENGINEER_PASSWORD") or DEFAULT_ENGINEER_PASSWORD
                                engineer_user = UserAccountDocument(
                                    username="engineer",
                                    hashed_password=hash_password(engineer_password),
                                    role="user",
                                    permissions=["audit"]
                                )
                                await engineer_user.save()
                                if engineer_password == DEFAULT_ENGINEER_PASSWORD:
                                    seeded_with_defaults.append("engineer")
                                else:
                                    logger.info("Seeded engineering user account from SEED_ENGINEER_PASSWORD.")

                            if seeded_with_defaults:
                                logger.warning(
                                    "SECURITY: seeded %s with well-known default password(s). "
                                    "Change them immediately, or set SEED_ADMIN_PASSWORD / "
                                    "SEED_ENGINEER_PASSWORD before first start.",
                                    " and ".join(seeded_with_defaults),
                                )
                        except Exception as seed_err:
                            logger.warning(f"Failed to verify or seed default user accounts: {str(seed_err)}")

                        # Seed initial corporate client directories
                        try:
                            from ...domain.models.client import ClientDocument
                            initial_clients = ["KEMCO", "AGCC", "JFE", "NIKKO", "TEX"]
                            for name in initial_clients:
                                client_exists = await ClientDocument.find_one(ClientDocument.name == name)
                                if not client_exists:
                                    await ClientDocument(name=name).save()
                                    logger.info(f"Seeded target client directory: '{name}' successfully.")
                        except Exception as client_seed_err:
                            logger.warning(f"Failed to verify or seed default clients: {str(client_seed_err)}")

                        self.connected = True
                        logger.info(
                            f"Successfully connected to MongoDB ({mode_label}) database '{settings.MONGO_DB_NAME}' "
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
                            logger.warning(
                                f"Exhausted {max_retries} attempts for {mode_label} URI ({masked_uri})."
                            )
                            break
                        
                        logger.info(f"Retrying connection in {delay:.2f} seconds...")
                        await asyncio.sleep(delay)
                        delay *= 2.0  # Exponential backoff multiplier

            logger.error("All candidate database connections failed. Operating in disconnected fallback mode.")
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
