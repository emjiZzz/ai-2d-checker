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

Open a **second** terminal in the project root and choose your mode:

#### Option A: Full Development Mode (All Features)
```powershell
powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1
```
> 💡 Includes Authentication/Login, 3D Workspace, History sessions, Standards, and AI Engine/Copilot.

#### Option B: Prototype Mode (Streamlined 2D CAD Only)
```powershell
powershell -ExecutionPolicy Bypass -File .\start_prototype.ps1
```
*or:*
```powershell
powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1 -Prototype
```
> 🚀 Bypasses Login straight to the 2D CAD Workspace and hides the 3D / History / Standards / Settings tabs.
>
> ⚠ **Prototype mode is for collecting an engineer's own markings — no comparison engine runs in it.**
> Every room is forced to `manual_check`, the left panel is the marking list rather than the
> comparison panel, and there is no START COMPARISON button to reach. This bullet used to promise
> "deterministic visual/physical difference checks", which is the opposite of what the flag does.
> Use **Option A** if you want the comparison engine. See `apps/desktop/src/config/features.ts`.

---

### Step 3 — Building the Desktop Installer (.msi / .exe)

To build the standalone Windows installer pre-packaged in **Prototype Mode**:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_prototype.ps1
```
The output installer will be generated in `apps/desktop/src-tauri/target/release/bundle/msi/`.

> ⚠ **Use the script — do not hand-run `pnpm build:prototype` and then `tauri build`.**
> `tauri.conf.json` sets `beforeBuildCommand: "pnpm build"`, so `tauri build` re-runs Vite in
> production mode and **overwrites** the `dist/` that `build:prototype` just produced. Only an
> ambient `VITE_PROTOTYPE_MODE=true` survives that far, which is what the script exports. Run the
> two commands by hand without it and you get a full installer with a login screen, silently.
> The script now verifies the result with `tools/scripts/assert-build-mode.mjs` and aborts rather
> than hand you an installer in the wrong mode.

---

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
├── start_desktop.ps1     ← Launch Desktop App (Full Dev Mode, or -Prototype)
├── start_prototype.ps1   ← Launch Desktop App (Prototype Mode Shortcut)
├── build_prototype.ps1   ← Build standalone .msi/.exe Prototype Installer
├── start-mongo.ps1       ← Start local MongoDB Community Server
├── portable-msvc.py      ← Script to download MSVC linker (one-time setup)
├── README.md             ← You are here
└── README_SETUP.txt      ← Full beginner setup guide
```

---

## ⚙️ Useful Commands

```powershell
# Install all packages (run after cloning or after pulling new changes)
pnpm install

# Run web dev in Prototype Mode (no Tauri / browser only)
pnpm dev:prototype

# Build the WEB bundle in Prototype Mode (browser only)
pnpm build:prototype

# Check which mode apps/desktop/dist was actually built in
pnpm assert:prototype     # fails unless dist/ is a prototype build
pnpm assert:full

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
