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

def _auto_detect_oda_converter() -> str:
    # 1. Respect explicit environment override if provided
    env_path = os.getenv("ODA_CONVERTER_PATH")
    if env_path:
        return env_path
        
    # 2. Automatically scan the standard Windows install folder for any version
    default_dir = Path("C:/Program Files/ODA")
    if default_dir.exists():
        try:
            for sub_dir in default_dir.iterdir():
                if sub_dir.is_dir() and "ODAFileConverter" in sub_dir.name:
                    exec_path = sub_dir / "ODAFileConverter.exe"
                    if exec_path.exists():
                        return str(exec_path.resolve().as_posix())
        except Exception:
            pass
            
    # 3. Standard fallback path
    return "C:/Program Files/ODA/ODAFileConverter/ODAFileConverter.exe"

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
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    
    # ODA File Converter Auto-Discovery
    ODA_CONVERTER_PATH: str = _auto_detect_oda_converter()
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10240"))

settings = Settings()
