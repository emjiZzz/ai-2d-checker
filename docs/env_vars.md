# AI-2D-Checker Environment Variables Configuration

This document specifies the variables used in the workspace `.env` configuration file, their default behaviors, security bounds, and automated logging redaction strategies.

---

## ⚙️ 1. Environment Reference Table

| Variable Name | Description | Default / Recommended | Security Level |
|---|---|---|---|
| `MONGO_URI` | Connection URI for the local MongoDB Community Server. | `mongodb://localhost:27017` | **Medium** (Masked credentials in logs) |
| `MONGO_DB_NAME` | Active MongoDB database namespace. | `ai_2d_checker` | **Low** |
| `GEMINI_API_KEY` | Developer Google Gemini Flash API Key. | `YOUR_GEMINI_API_KEY_HERE` | **Critical** (Redacted automatically in logs) |
| `GEMINI_MODEL` | Gemini AI auditing engine model version. | `gemini-3-flash` | **Low** |
| `STORAGE_ROOT` | Absolute or relative path to the persistent workspace storage root. | `./storage` | **Low** |
| `MAX_FILE_SIZE_MB` | Upper limit boundary on drawing upload requests. | `500` | **Low** |
| `ODA_CONVERTER_PATH`| Path to the local installation of the ODA File Converter. | `C:/Program Files/ODA/ODAFileConverter...` | **Low** |
| `SIDECAR_PORT` | Port binding for the backend FastAPI sidecar. Use `0` for dynamic allocation. | `8080` (or `0`) | **Low** |
| `SIDECAR_HOST` | FastAPI server binding host interface. | `127.0.0.1` | **High** (Enforces localhost lookup) |
| `SIDECAR_LOG_LEVEL`| Log verbosity level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` | **Low** |

---

## 🔒 2. Secrets Protection & Automatic Log Redaction

To prevent sensitive credentials or private tokens from ever leaking into diagnostics files or console stdout, the backend structured logger contains an automated redact filter.

- **Monitored Variables**: `API_TOKEN` and `GEMINI_API_KEY`.
- **Formatting Rule**: If a logged message contains either of these keys in plaintext, the logger automatically replaces them with a mask sequence: `********`.
- **Diagnostics Masking**: In startup diagnostics print statements, sensitive properties are printed as a masked string using `mask_secret()` (e.g. `AI_3...4Fh9`).
- **Dynamic Derivation**: No raw key-material is ever written to log traces.
