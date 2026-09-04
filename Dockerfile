# Cloud backend image (Render). See `render.yaml` for the service definition.
#
# This is the THIRD topology this backend runs in, alongside the per-workstation sidecar
# (PyInstaller, `tools/draftcheck_server.spec`) and the LAN server at 192.168.200.105.
# The other two are Windows-native; this is the only Linux one, which is why the font work
# below exists.
#
# ## What is deliberately NOT installed
#
# `libgl1-mesa-glx` does not exist on bookworm (split into libgl1 / libglx-mesa0) and is not
# needed regardless: nothing under `services/backend/` imports cv2, and matplotlib is pinned to
# the headless Agg backend at `infrastructure/rendering/dxf_background_renderer.py:9`.
# PyMuPDF ships its own binaries; reportlab needs neither cairo nor pango.

FROM python:3.12-slim

# - fonts-noto-cjk is LOAD-BEARING, not cosmetic. This corpus is Japanese, and without a
#   CJK-capable TTF `configure_cad_fonts()` returns None and every CJK string in a PNG render,
#   an OCR crop and the PDF report draws as tofu. See `dxf_render_setup.JAPANESE_FONT_CANDIDATES`,
#   which had to learn the Linux paths for this to resolve.
# - libgomp1 is the OpenMP runtime the scipy / scikit-learn wheels link against.
# - curl backs the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        fonts-noto-cjk \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # matplotlib refuses to start without a writable config dir, and $HOME is not one here.
    MPLCONFIGDIR=/tmp/mpl \
    # Anchored explicitly rather than left to `app_root()`, so the value is greppable from
    # `render.yaml` and from a `docker inspect`.
    STORAGE_ROOT=/app/storage

WORKDIR /app

# Dependencies first, so a source-only change does not re-resolve ~40 wheels.
COPY services/backend/requirements.txt ./services/backend/requirements.txt
RUN pip install --no-cache-dir -r services/backend/requirements.txt

# ⚠ `services/` and `services/backend/` have NO `__init__.py` — they are PEP 420 namespace
# packages, so `services.backend.*` resolves only with /app on sys.path. WORKDIR + `python -m`
# is what supplies that.
COPY services/backend ./services/backend

RUN mkdir -p /app/storage

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

# Reuses the existing console entry point rather than introducing a second way to start the
# server. It already reads settings.HOST/PORT and hands uvicorn the app OBJECT — no reload, one
# worker — which is what this deployment wants anyway. See its module docstring.
CMD ["python", "-m", "services.backend.server_main"]
