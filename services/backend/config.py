import os
from pathlib import Path

from dotenv import load_dotenv

# Find the .env beside the application root. `app_root()` rather than a `__file__` walk because
# a frozen build unpacks into a temp directory -- see runtime_paths for what that silently costs.
from .runtime_paths import app_root

root_dir = app_root()
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
                        return exec_path.resolve().as_posix()
        except Exception:
            pass
            
    # 3. Standard fallback path
    return "C:/Program Files/ODA/ODAFileConverter/ODAFileConverter.exe"

class Settings:
    PROJECT_NAME: str = "AI-2D-Checker Standalone Backend"
    VERSION: str = "1.0.0"
    
    # Binding Configuration - Loopback by default, 0.0.0.0 in container/Render environments
    HOST: str = os.getenv("SIDECAR_HOST") or ("0.0.0.0" if (os.getenv("PORT") or os.getenv("RENDER")) else "127.0.0.1")
    PORT: int = int(os.getenv("PORT") or os.getenv("SIDECAR_PORT", "8080"))  # Default to 8080 if not set or dynamic
    
    LOG_LEVEL: str = os.getenv("SIDECAR_LOG_LEVEL", "INFO")
    STORAGE_ROOT: str = os.getenv("STORAGE_ROOT", "./storage")
    
    # Database Configuration & Failover
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_FALLBACK_URI: str = os.getenv("MONGO_FALLBACK_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "ai_2d_checker")
    ENABLE_DB_AUTO_SYNC: bool = os.getenv("ENABLE_DB_AUTO_SYNC", "true").lower() in ("1", "true", "yes")
    DB_AUTO_SYNC_INTERVAL_SEC: int = int(os.getenv("DB_AUTO_SYNC_INTERVAL_SEC", "60"))
    
    # LAN/Cloud deployment. Both are comma-separated and ADD to the built-in defaults rather than
    # replacing them -- see main.py. Empty means "loopback only", which is the historical
    # behaviour and what a developer checkout wants. RENDER_EXTERNAL_HOSTNAME is auto-appended when present.
    @staticmethod
    def _resolve_allowed_hosts() -> str:
        hosts = [h.strip() for h in (os.getenv("ALLOWED_HOSTS", "")).split(",") if h.strip()]
        render_host = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
        if render_host and render_host not in hosts:
            hosts.append(render_host)
        render_svc = (os.getenv("RENDER_SERVICE_NAME") or "").strip()
        if render_svc and render_svc not in hosts:
            hosts.append(render_svc)
        if (os.getenv("PORT") or os.getenv("RENDER")) and "0.0.0.0" not in hosts:
            hosts.append("0.0.0.0")
        return ",".join(hosts)

    ALLOWED_HOSTS: str = _resolve_allowed_hosts()
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "")

    # API Security Token
    API_TOKEN: str | None = os.getenv("API_TOKEN")
    
    # Secrets
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4")

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
    GEMINI_MODEL_PRO: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-flash")
    GEMINI_MODEL_FLASH: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-flash-latest")
    GEMINI_MODEL_FALLBACK: str = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-flash-latest")

    # ADR-010: grounded LLM summarization of comparison findings. OFF BY DEFAULT, and the default
    # is the safety-relevant half of the decision -- a summary request sends finding text, which is
    # verbatim drawing text, off the customer's machine. ADR-005 argues local-only is a commercial
    # feature here rather than a preference, so a customer who has not opted in must send nothing
    # new. Making a default-off feature default-on later is free; the reverse costs a customer.
    #
    # ADR-010 specifies this opt-in as *per room*. This flag is global -- the default-off property
    # is honoured, the granularity is not yet built. Recorded as a deviation in the ADR rather than
    # left to be discovered.
    ENABLE_LLM_SUMMARY: bool = (
        os.getenv("ENABLE_LLM_SUMMARY", "").strip().lower() in {"1", "true", "yes", "on"}
    )

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
