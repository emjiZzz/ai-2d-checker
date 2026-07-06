# AI-2D-Checker

> An AI-powered engineering drawing compliance checker that runs entirely on your local computer — no cloud uploads, no subscriptions.

Upload a DWG/DXF drawing file, and the app will automatically compare it against your company's engineering standards and highlight violations using Google's Gemini AI.

---

## ✅ What This App Does

- Converts AutoCAD DWG/DXF drawings into analyzable vectors
- Overlays standard compliance grids onto drawings
- Uses AI to detect dimension errors, missing annotations, and standard violations
- Stores all results locally in MongoDB — your data never leaves your machine
- Runs as a native Windows desktop application (not just a web browser tab)

---

## 🛠️ Technology Stack

| What                     | Technology Used                     |
| ------------------------ | ----------------------------------- |
| **UI (Frontend)**  | React 19 + TypeScript               |
| **Desktop Window** | Tauri v2 (Rust)                     |
| **Backend Server** | Python FastAPI                      |
| **Database**       | MongoDB Community Server (local)    |
| **AI Engine**      | Google Gemini Flash API             |
| **DWG Processing** | ODA File Converter + ezdxf + OpenCV |

---

## 🚀 Quick Start (First Time Setup)

See the full step-by-step guide in [`README_SETUP.txt`](./README_SETUP.txt).

**Summary of what you need to install:**

1. Node.js v20+ and pnpm
2. Python 3.12+
3. Rust (via rustup) + MSVC linker (via `portable-msvc.py`)
4. MongoDB Community Server
5. ODA File Converter
6. A Gemini API Key (free from https://aistudio.google.com/)

---

## ▶️ Running the App (Daily Use)

You need to start **two** things every time you want to run the app.

### Step 1 — Start the Backend

Open a terminal in the project root and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\services\backend\start.ps1
```

Wait until you see: `Uvicorn running on http://0.0.0.0:8080`

### Step 2 — Start the Desktop Window

Open a **second** terminal in the project root and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1
```

> ⏳ First run takes 5–10 minutes (compiling Rust). After that it's fast.

### Optional — View the API Docs

After starting the backend, open this URL in your browser:

```
http://localhost:8080/docs
```

---

## 📁 Project Structure

```
ai-2d-checker/
├── apps/
│   └── desktop/          ← Main React UI + Tauri desktop shell (Rust)
├── packages/
│   ├── config/           ← Shared code style settings (ESLint, Prettier)
│   ├── types/            ← Shared TypeScript data types
│   ├── ui/               ← Shared React UI components
│   └── utils/            ← Shared helper functions
├── services/
│   └── backend/          ← Python FastAPI backend server
├── storage/              ← ⚠️ Git-ignored. Holds drawings, PDFs, DB data
├── tools/
│   └── scripts/          ← Setup and maintenance scripts
├── start_desktop.ps1     ← ← ← Use this to launch the desktop app!
├── portable-msvc.py      ← Script to download MSVC linker (one-time setup)
├── README.md             ← You are here
└── README_SETUP.txt      ← Full beginner setup guide
```

---

## ⚙️ Useful Commands

```powershell
# Install all packages (run after cloning or after pulling new changes)
pnpm install

# Check code for errors
pnpm run lint

# Auto-format code
pnpm run format

# Run all tests
pnpm run test

# Clean build caches (if something is broken, try this)
pnpm run clean
```

---

## 🤝 Contribution Rules

Please follow these rules to keep the codebase clean:

1. **Commit messages** must follow the format: `type(scope): description`

   - Example: `feat(frontend): add zoom slider to canvas`
   - Example: `fix(backend): resolve MongoDB timeout on startup`
2. **Branch naming**: Create branches as `feat/your-feature-name` or `fix/bug-description`
3. **Pull Requests**: Always merge to `develop` first. Never push directly to `main`.
4. **No cross-package imports**: Packages can only import from `config`, `types`, and `utils` — never from each other.

---

## 📖 More Documentation

| Document                                                    | What it covers                            |
| ----------------------------------------------------------- | ----------------------------------------- |
| [`README_SETUP.txt`](./README_SETUP.txt)                   | Full beginner installation guide          |
| [`docs/architecture.md`](./docs/architecture.md)           | Security design and system architecture   |
| [`docs/env_vars.md`](./docs/env_vars.md)                   | All environment variable settings         |
| [`docs/storage_hierarchy.md`](./docs/storage_hierarchy.md) | How local files and folders are organized |

---

## ❓ Need Help?

Check Section 11 of [`README_SETUP.txt`](./README_SETUP.txt) for a full list of common problems and fixes.
