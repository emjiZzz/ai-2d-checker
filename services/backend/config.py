import os
from pathlib import Path
from dotenv import load_dotenv

# Find workspace root .env if running from workspace
root_dir = Path(__file__).resolve().parents[2]
env_path = root_dir / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()  # Fallback to local search

class Settings:
    PROJECT_NAME: str = "AI-2D-Checker Standalone Backend"
    VERSION: str = "1.0.0"
    
    # Binding Configuration - Force localhost-only loopback for secure local-first isolation
    HOST: str = os.getenv("SIDECAR_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("SIDECAR_PORT", "8080"))  # Default to 8080 if not set or dynamic
    
    LOG_LEVEL: str = os.getenv("SIDECAR_LOG_LEVEL", "INFO")
    STORAGE_ROOT: str = os.getenv("STORAGE_ROOT", "./storage")
    
    # Database Configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "ai_2d_checker")
    
    # API Security Token
    API_TOKEN: str | None = os.getenv("API_TOKEN")
    
    # Secrets
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    
    # ODA File Converter
    ODA_CONVERTER_PATH: str = os.getenv("ODA_CONVERTER_PATH", "C:/Program Files/ODA/ODAFileConverter/ODAFileConverter.exe")
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "500"))

settings = Settings()
