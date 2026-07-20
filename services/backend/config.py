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

    # Gemini model tiers. Google churns model names/deprecations fast (gemini-2.0-flash
    # was shut down June 1 2026; gemini-2.5-pro/flash are deprecated, "no earlier than"
    # Oct 16 2026 but not guaranteed to hold) — so every call site in this codebase
    # reads these instead of hardcoding a model string, and these three are the only
    # place a model upgrade/downgrade needs to happen.
    #   PRO      — highest-reasoning tier, used for the full-AI structured comparison
    #              pipeline where accuracy matters more than latency/cost.
    #   FLASH    — fast/interactive tier, used for Copilot chat streaming and title
    #              block OCR.
    #   FALLBACK — last-resort alias if PRO/FLASH are unavailable (rate-limited,
    #              deprecated, or mid-outage). "gemini-flash-latest" auto-points at
    #              whatever Google currently considers their latest stable Flash model,
    #              so it self-heals across future deprecations without a code change.
    GEMINI_MODEL_PRO: str = os.getenv("GEMINI_MODEL_PRO", "gemini-3.1-pro-preview")
    GEMINI_MODEL_FLASH: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")
    GEMINI_MODEL_FALLBACK: str = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-flash-latest")

    @property
    def GEMINI_MODEL_CASCADE(self) -> list[str]:
        """
        Ordered [PRO, FLASH, FALLBACK] cascade for call sites that want the highest
        quality available with automatic fallback on overload/deprecation, deduped
        while preserving order (so setting PRO == FLASH doesn't retry the same model
        twice).
        """
        seen: set[str] = set()
        cascade: list[str] = []
        for model in (self.GEMINI_MODEL_PRO, self.GEMINI_MODEL_FLASH, self.GEMINI_MODEL_FALLBACK):
            if model and model not in seen:
                seen.add(model)
                cascade.append(model)
        return cascade
    
    # ODA File Converter Auto-Discovery
    ODA_CONVERTER_PATH: str = _auto_detect_oda_converter()
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10240"))

settings = Settings()
