# AI-2D-Checker Environment Variables Configuration

This document specifies the variables used in the workspace `.env` configuration file, their default behaviors, security bounds, and automated logging redaction strategies.

---

## ⚙️ 1. Environment Reference Table

| Variable Name | Description | Default / Recommended | Security Level |
|---|---|---|---|
| `MONGO_URI` | Connection URI for the primary MongoDB cluster / server. | `mongodb://localhost:27017` | **Medium** (Masked credentials in logs) |
| `MONGO_FALLBACK_URI` | Failover MongoDB connection URI. | `mongodb://localhost:27017` | **Medium** (Masked credentials in logs) |
| `MONGO_DB_NAME` | Active MongoDB database namespace. | `ai_2d_checker` | **Low** |
| `ENABLE_DB_AUTO_SYNC` | Enables background replication synchronization with Atlas. | `true` (disable on cloud) | **Low** |
| `DB_AUTO_SYNC_INTERVAL_SEC` | Interval between background database sync cycles. | `60` | **Low** |
| `SEED_ADMIN_PASSWORD` | Initial bootstrap password for seed admin account. | `admin123` | **High** |
| `SEED_ENGINEER_PASSWORD` | Initial bootstrap password for seed engineer account. | `engineer123` | **High** |
| `API_TOKEN` | Static API Bearer Token for authenticating clients. | Auto-generated if empty | **Critical** (Redacted in logs) |
| `GEMINI_API_KEY` | Google Gemini API Key for OCR and AI analysis. | `YOUR_GEMINI_API_KEY_HERE` | **Critical** (Redacted in logs) |
| `GEMINI_MODEL_PRO` | Highest-reasoning Gemini tier for full structured pipeline. | `gemini-2.5-flash` | **Low** |
| `GEMINI_MODEL_FLASH` | Fast/interactive Gemini tier for Copilot streaming & OCR. | `gemini-flash-latest` | **Low** |
| `GEMINI_MODEL_FALLBACK` | Last-resort fallback model. | `gemini-flash-latest` | **Low** |
| `OPENAI_API_KEY` | Developer OpenAI API Key. | `YOUR_OPENAI_API_KEY_HERE` | **Critical** (Redacted in logs) |
| `OPENAI_MODEL` | Target OpenAI model node. | `gpt-5.4` | **Low** |
| `ENABLE_LLM_SUMMARY` | Feature flag for grounded LLM summary of comparison findings. | `false` | **Low** |
| `STORAGE_ROOT` | Path to persistent storage root hierarchy. | `./storage` (or `/app/storage`) | **Low** |
| `MAX_FILE_SIZE_MB` | Upper limit boundary on drawing upload requests. | `500` | **Low** |
| `ODA_CONVERTER_PATH`| Path to local ODA File Converter on Windows. | `C:/Program Files/ODA/...` | **Low** |
| `SIDECAR_PORT` / `PORT` | Port binding for backend FastAPI server. | `8080` (or injected by cloud) | **Low** |
| `SIDECAR_HOST` / `HOST` | FastAPI server binding host interface. | `127.0.0.1` (or `0.0.0.0`) | **Medium** |
| `ALLOWED_HOSTS` | Comma-separated list of exact allowed Host headers. | Empty (loopback only) | **Medium** |
| `CORS_ORIGINS` | Comma-separated extra allowed CORS origins. | Empty (standard Tauri origins) | **Low** |
| `SIDECAR_LOG_LEVEL`| Log verbosity level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` | **Low** |

---

## 🔒 2. Secrets Protection & Automatic Log Redaction

To prevent sensitive credentials or private tokens from ever leaking into diagnostics files or console stdout, the backend structured logger contains an automated redact filter.

- **Monitored Variables**: `API_TOKEN`, `GEMINI_API_KEY`, and `OPENAI_API_KEY`.
- **Formatting Rule**: If a logged message contains either of these keys in plaintext, the logger automatically replaces them with a mask sequence: `********`.
- **Diagnostics Masking**: In startup diagnostics print statements, sensitive properties are printed as a masked string using `mask_secret()` (e.g. `AI_3...4Fh9`).
- **Dynamic Derivation**: No raw key-material is ever written to log traces.
