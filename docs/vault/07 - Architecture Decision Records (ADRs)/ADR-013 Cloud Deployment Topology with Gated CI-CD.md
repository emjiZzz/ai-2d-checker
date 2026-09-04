---
title: ADR-013 Cloud Deployment Topology with Gated CI/CD
type: adr
tags: [adr, architecture, deployment, cloud, render, cicd, security, networking]
status: accepted
date: 2026-08-28
supersedes: ADR-005 Local-Only Processing with Cloud Licensing
amends: none
amended-by: none
related: [ADR-004 Deterministic-Only Scope, ADR-005 Local-Only Processing with Cloud Licensing, ADR-010 Grounded LLM Summarization of Comparison Results]
---

# ADR-013 — Cloud-Hosted Backend Deployment on Render with Gated CI/CD

**Status:** accepted · **Date:** 2026-08-28 · **Supersedes:** [[ADR-005 Local-Only Processing with Cloud Licensing]]

---

## Context

Prior to this decision, the application supported two deployment topologies:
1. **Per-workstation sidecar** on `127.0.0.1:8080`, managed as a local Windows service.
2. **On-premises LAN server** at a fixed internal IP (`192.168.200.105:8080`) serving engineering workstations across a private network.

While [[ADR-005 Local-Only Processing with Cloud Licensing]] proposed strict local-only execution, practical prototype delivery, rapid feature iterations, and multi-engineer testing surfaced substantial operational friction in packaging per-workstation sidecars, distributing updated installers, and synchronizing schema/index changes.

To accelerate prototype feedback and establish automated deployment pipelines, this ADR introduces a **cloud-hosted deployment topology** where the FastAPI backend runs as a containerized web service on Render, auto-deployed via gated GitHub Actions from `main`, while allowing the Tauri desktop client to connect securely over HTTPS.

---

## Decision

1. **Cloud Backend Hosting (Render):**
   - The FastAPI backend is containerized via a production `Dockerfile` (`python:3.12-slim` + `fonts-noto-cjk` + `libgomp1`) and deployed on Render.
   - Database persistence remains anchored to the shared **MongoDB Atlas** cluster. Because Render free-tier instances run on dynamic outbound IP addresses, the MongoDB Atlas Network Access IP Access List must include `0.0.0.0/0` (Allow Access from Anywhere).
   - Dynamic port binding (`PORT`) and cloud binding (`HOST=0.0.0.0`) are supported out of the box.
   - `/health` endpoint returns HTTP 503 if MongoDB connection is unavailable, preventing dead-database builds from being marked healthy.

2. **Security & Authentication Boundary:**
   - **Remote API Token:** Cloud deployments use an explicit `API_TOKEN` configured in environment variables.
   - **Desktop Client Authentication:** The desktop app supports entering and persisting a remote `API_TOKEN` in `localStorage` (`ai_2d_remote_api_token`), cleanly bypassing local machine-bound file decryption when targeting remote backends.
   - **Exact Host Validation:** `verify_host` retains strict exact-match hostname verification. `RENDER_EXTERNAL_HOSTNAME` is dynamically appended to `ALLOWED_HOSTS` to support Render domains without opening DNS-rebinding vulnerabilities.
   - **Content Security Policy:** Tauri's CSP is narrowed specifically to `https://*.onrender.com` (no blanket `https:`, no unused `wss:`).

3. **Gated CI/CD Pipeline:**
   - Changes to `services/backend/**`, `tests/**`, or deployment files trigger `.github/workflows/deploy-backend.yml`.
   - The workflow executes the full backend pytest suite (with a dedicated `mongo:7` service container), validates container buildability, and triggers Render deployment upon merging to `main`.

---

## Consequences

**Positive:**
- **Zero Packaging Friction:** Backend bug fixes and pipeline improvements deploy instantly without requiring engineers to download new `.msi`/`.exe` installers.
- **Centralized Compute & Collaboration:** Multiple engineers access shared rooms, drawings, and audit sessions on a single unified backend.
- **Gated Quality Assurance:** Automated CI testing with live MongoDB containers prevents broken commits from reaching staging/production environments.

**Negative / Accepted Costs:**
- **Cold Start Latency:** On Render free tier, idle instances sleep after 15 minutes; the desktop client accommodates this with extended 45-second connection timeout headroom.
- **Ephemeral Storage on Free Tier:** Local uploads on container disk reset across deploys, while all database entities and markings remain safely preserved in MongoDB Atlas.
- **Internet Dependency:** Workstations require an active internet connection when targeting cloud instances.
