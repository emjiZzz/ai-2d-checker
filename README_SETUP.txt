==============================================================================
                  AI-2D-CHECKER — DEVELOPER SETUP GUIDE
==============================================================================
Welcome! This guide walks you through setting up the AI-2D-Checker app on your
computer from scratch. Follow each step in order. Do not skip any steps.

If you get stuck, check Section 11 (Troubleshooting) at the bottom.

TABLE OF CONTENTS
──────────────────────────────────────────────────────────────────────────────
 1. What You Need to Install (Prerequisites)
 2. Install Node.js & pnpm  (for the frontend/UI)
 3. Install Python          (for the backend/AI engine)
 4. Install Rust & MSVC     (for the desktop window)
 5. Install MongoDB          (for the local database)
 6. Install ODA File Converter (for reading DWG drawing files)
 7. Set Up Your Gemini API Key (for AI compliance checking)
 8. Download & Install the Project
 9. Daily Startup — How to Run the App
10. Folder Guide for New Developers
11. Troubleshooting Common Problems
12. Git Commit Message Standards
──────────────────────────────────────────────────────────────────────────────


1. WHAT YOU NEED TO INSTALL (PREREQUISITES)
──────────────────────────────────────────────────────────────────────────────
Before running the app, your computer needs these programs installed.
Install them in the order shown in sections 2–7.

  ✅ Node.js v20+     → runs the UI code
  ✅ pnpm             → installs JS packages (like npm, but faster)
  ✅ Python 3.12+     → runs the backend server
  ✅ Rust + MSVC      → compiles the desktop window
  ✅ MongoDB          → stores audit data locally on your computer
  ✅ ODA Converter    → converts DWG files for processing
  ✅ Gemini API Key   → powers the AI drawing analysis


2. INSTALL NODE.JS & PNPM
──────────────────────────────────────────────────────────────────────────────
Node.js lets your computer run JavaScript code outside the browser.
pnpm is a faster alternative to npm for installing JavaScript packages.

STEP 1: Download Node.js LTS from:
  https://nodejs.org/

STEP 2: Run the installer. Accept all default options.

STEP 3: Open a new PowerShell window and verify it installed correctly:
  node --version        ← should show v20.x.x or higher
  npm --version         ← should show a version number

STEP 4: Install pnpm via npm:
  npm install -g pnpm

STEP 5: Verify pnpm:
  pnpm --version        ← should show a version number


3. INSTALL PYTHON
──────────────────────────────────────────────────────────────────────────────
Python runs the FastAPI backend server that handles the AI logic.

STEP 1: Download Python 3.12 (64-bit Windows installer) from:
  https://www.python.org/downloads/

STEP 2: Run the installer.
  ⚠️ IMPORTANT: Check the box that says "Add Python.exe to PATH"
     (this box is on the very first screen of the installer!)

STEP 3: Click "Install Now".

STEP 4: Verify Python installed correctly:
  python --version      ← should show Python 3.12.x or higher
  pip --version         ← should show a version number


4. INSTALL RUST & MSVC (FOR THE DESKTOP WINDOW)
──────────────────────────────────────────────────────────────────────────────
Tauri uses Rust to wrap the web UI into a native Windows desktop window.
Rust also needs Microsoft's C++ linker (link.exe) to compile on Windows.

── STEP A: Get the MSVC C++ linker (link.exe) ──────────────────────────────
Because the Visual Studio installer is very large (~4GB), we use a portable
script to download only the essential files (~500MB).

  1. Open PowerShell and run:
       python portable-msvc.py --accept-license --target x64 --host x64
     (The portable-msvc.py script is included in this repository at the root)

  2. This will create a folder called "msvc" in your home directory
     (C:\Users\<YourName>\msvc\) containing link.exe and the Windows SDK.

── STEP B: Install Rust ─────────────────────────────────────────────────────
  1. Download Rustup from:
       https://rustup.rs/

  2. Run rustup-init.exe and choose option "1" (default installation).

  3. Verify Rust installed:
       rustc --version   ← should show rustc 1.x.x
       cargo --version   ← should show cargo 1.x.x

  NOTE: If rustc/cargo is not found, add this to your PATH manually:
    %USERPROFILE%\.cargo\bin


5. INSTALL MONGODB (LOCAL DATABASE)
──────────────────────────────────────────────────────────────────────────────
MongoDB stores audit results and metadata on your local computer.

STEP 1: Download MongoDB Community Server from:
  https://www.mongodb.com/try/download/community

STEP 2: Run the installer:
  - Check "Install MongoDB as a Service" (runs automatically on startup)
  - Check "Install MongoDB Compass" (a visual GUI to browse your database)

STEP 3: Verify MongoDB is running by opening MongoDB Compass.
  Click "Connect" using this connection string:
    mongodb://localhost:27017

  If you see "Connected" in the top left — it's working!

STEP 4 (IF ADMIN PERMISSIONS ARE BLOCKED):
  If you cannot install as a Service, use the manual launcher script:
    powershell -ExecutionPolicy Bypass -File .\tools\scripts\start-mongo.ps1


6. INSTALL ODA FILE CONVERTER
──────────────────────────────────────────────────────────────────────────────
DWG is a proprietary AutoCAD format. We use the ODA File Converter to
automatically convert DWG drawings into the open DXF format.

STEP 1: Download the ODA File Converter from:
  https://www.opendesign.com/guestfiles/oda_file_converter

STEP 2: Run the installer using all default options.
  It usually installs to:
    C:\Program Files\ODA\ODAFileConverter_25.12.0\ODAFileConverter.exe

STEP 3: Open the file ".env" in the root of the project folder and set:
  ODA_CONVERTER_PATH=C:\Program Files\ODA\ODAFileConverter_25.12.0\ODAFileConverter.exe


7. SET UP YOUR GEMINI API KEY
──────────────────────────────────────────────────────────────────────────────
The AI compliance checking is powered by Google's Gemini Flash model.
You need a free API key to enable it.

STEP 1: Go to Google AI Studio:
  https://aistudio.google.com/

STEP 2: Sign in with your Google account.

STEP 3: Click "Create API Key". Copy the key (starts with "AIza...").

STEP 4: Open the ".env" file in the project root and paste your key:
  GEMINI_API_KEY=AIzaSy...your-key-here...

  ⚠️ NEVER share this key or commit it to Git. The .env file is already
     in .gitignore to protect you.


8. DOWNLOAD & INSTALL THE PROJECT
──────────────────────────────────────────────────────────────────────────────
Once all prerequisites are installed, get the project code set up.

STEP 1: Clone the repository:
  git clone https://github.com/your-org/ai-2d-checker.git
  cd ai-2d-checker

STEP 2: Install all JavaScript/Node packages:
  pnpm install

STEP 3: Install Python backend packages:
  cd services\backend
  pip install -r requirements.txt
  pip install -r ..\..\requirements-dev.txt
  cd ..\..

STEP 4: Copy the example environment file:
  copy .env.example .env
  (Then edit .env to fill in your API key and ODA path from steps 6 & 7)


9. DAILY STARTUP — HOW TO RUN THE APP
──────────────────────────────────────────────────────────────────────────────
Every time you want to work on or test the app, open TWO terminals.

── TERMINAL 1: Start the Backend (FastAPI server) ───────────────────────────
  Navigate to the project root, then run:
    powershell -ExecutionPolicy Bypass -File .\services\backend\start.ps1

  ✅ You should see:
    "Uvicorn running on http://0.0.0.0:8080"

── TERMINAL 2: Start the Desktop App (Tauri) ────────────────────────────────
  In a second terminal at the project root, run:
    powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1

  ✅ The first run will take 5-10 minutes (compiling Rust code).
     Subsequent runs will be much faster (cached).
  ✅ A desktop window will pop open when it's ready.

── OPTIONAL: View API Documentation ─────────────────────────────────────────
  After starting the backend, open in your browser:
    http://localhost:8080/docs


10. FOLDER GUIDE FOR NEW DEVELOPERS
──────────────────────────────────────────────────────────────────────────────
Here is a map of what's inside the project folder:

  /apps/desktop/
    The main React UI code and Tauri configuration.
    This is where the visual interface (buttons, panels, screens) lives.

  /apps/desktop/src-tauri/
    Rust code for the native desktop window shell.
    You usually don't need to edit this unless modifying OS-level features.

  /packages/
    Shared code used by multiple parts of the project.
    ├── config/   → Shared lint/format/TypeScript settings
    ├── types/    → Shared TypeScript data types (e.g. Drawing, AuditResult)
    ├── ui/       → Shared React components (buttons, modals, etc.)
    └── utils/    → Shared helper functions (file validation, calculations)

  /services/backend/
    The Python FastAPI server. Handles all the heavy logic:
    DWG conversion, AI auditing, PDF generation, database operations.

  /storage/
    ⚠️ This folder is NOT committed to Git (it's in .gitignore).
    It holds uploaded drawings, generated PDFs, overlay images, and
    the local MongoDB database files.

  /tools/scripts/
    Helper PowerShell scripts for setup, diagnostics, and packaging.


11. TROUBLESHOOTING COMMON PROBLEMS
──────────────────────────────────────────────────────────────────────────────
Problem: "python is not recognized" when running scripts.
Fix: You forgot to check "Add Python.exe to PATH" during installation.
     Uninstall Python, reinstall it, and check that box this time.
     Alternatively, search "Environment Variables" in Windows settings
     and manually add: C:\Users\<YourName>\AppData\Local\Programs\Python\Python312

Problem: "cargo is not recognized" — Rust not found.
Fix: Close your terminal completely and open a new one.
     If still broken, manually add to PATH: %USERPROFILE%\.cargo\bin

Problem: MongoDB connection fails (Compass shows "Connection refused").
Fix: Option A — Open Windows Services (search "services.msc"), find
     "MongoDB Server", right-click → Start.
Fix: Option B — Run the manual launcher:
     powershell -ExecutionPolicy Bypass -File .\tools\scripts\start-mongo.ps1

Problem: ODA File Converter fails / drawing previews are blank.
Fix: Open .env and double-check the ODA_CONVERTER_PATH value.
     Make sure the path leads to the actual ODAFileConverter.exe file.

Problem: Tauri desktop window never opens (compile takes forever or fails).
Fix: Make sure you ran the portable-msvc.py script first (Section 4).
     Then always use start_desktop.ps1 instead of running pnpm directly.

Problem: Backend shows a FutureWarning about "google.generativeai".
Fix: This is a harmless warning about an old package name.
     The app still works correctly. It will be updated in a future version.


12. GIT COMMIT MESSAGE STANDARDS
──────────────────────────────────────────────────────────────────────────────
All commits must follow this format so the history is easy to read:

  <type>(<scope>): <short description>

Types:
  feat      → You added a new feature
  fix       → You fixed a bug
  docs      → You changed documentation or README files
  refactor  → You rewrote code without changing what it does
  test      → You added or modified tests
  chore     → Maintenance work (updating packages, cleanup, etc.)

Scopes (use the folder/area you changed):
  frontend, backend, desktop, types, ui, utils, scripts, docs

Examples:
  feat(frontend): add zoom controls to drawing canvas
  fix(backend): resolve MongoDB connection timeout on startup
  docs(readme): update Rust installation steps for Windows
  chore(deps): update tauri to v2.11.2

==============================================================================
