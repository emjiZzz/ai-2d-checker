# AI-2D-Checker Local Storage Hierarchy Specification

AI-2D-Checker is a local-first application that handles CAD engineering files, AI compliance audits, and caches locally on the machine. This document specifies the layout, write permission validations, and cleanup procedures.

---

## 📁 1. Storage Folder Hierarchy

The storage root directory defaults to `./storage` (git-ignored) at the repository root and contains the following subdirectories:

```text
storage/
├── secure/                   # 🔑 Sensitive runtime files
│   └── .api-token            # AES-256-GCM encrypted Dynamic API Token
├── uploads/                  # 📤 Target folder for raw uploaded CAD drawings
├── cache/                    # ⚡ Drawing segment caches and tile previews
├── temp/                     # ⏳ Transient converter files (dxfs, overlays)
├── quarantine/               # ☣️ Sandbox quarantine (malicious or failed path traversals)
├── reports/                  # 📊 PDF reports exported by the auditor
└── logs/                     # 📝 Rotated application execution log files
    ├── backend/
    │   └── backend.log       # Rotated JSON FastAPI sidecar logs (rotated at 5MB, max 5 backups)
    └── app/
        └── app.log           # Rust app execution traces and critical panic hook dumps
```

---

## 🛡️ 2. Write Permissions Validation

During system startup:
1. The **Path Resolver** attempts to create the storage root and all child folders.
2. It validates write capabilities by creating a temporary file `.write_test` inside *every* required folder.
3. The resolver immediately deletes the `.write_test` file.
4. If any directory fails to write or throws a Permission Error, the backend startup routine halts immediately with a `RuntimeError` and logs a `CRITICAL` state.

---

## 🧹 3. Storage Pruning & Cleanup Policies

To ensure storage space remains clean and does not accumulate heavy caches or transient converter remnants, a manual/scheduled cleanup routine is available:

- **Temporary Pruning**: Scans `storage/temp/` and deletes any transient files older than a customizable threshold (defaults to 24 hours).
- **Cache Flushing**: Completely flushes the `storage/cache/` directory to purge obsolete pre-rendered previews.
- **Diagnostics**: The `/api/v1/system/storage` endpoint compiles detailed counts, absolute paths, and folder sizes, showing disk metrics using standard operating system queries.
