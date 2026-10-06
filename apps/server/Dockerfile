# Three images from one file. `server`: the API and the default-queue worker. `agent`: adds
# Chromium for the assignment worker. `parse`: adds Docling and its models for the parse-queue
# worker. The deployment picks the command. Build from the repository root, where the uv
# workspace and lockfile live:
#
#   docker build --file apps/server/Dockerfile --target server --tag public-atlas-server .
#   docker build --file apps/server/Dockerfile --target agent  --tag public-atlas-server-agent .
#   docker build --file apps/server/Dockerfile --target parse  --tag public-atlas-server-parse .

# --- Dependencies -------------------------------------------------------------
# The Python from .python-version, and uv copied in from its own image: the version must
# satisfy `required-version` in the root pyproject.toml.
FROM python:3.14-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, from the lockfile alone, so this layer survives source changes. The
# workspace member's pyproject.toml is needed for the resolution.
COPY pyproject.toml uv.lock ./
COPY apps/server/pyproject.toml apps/server/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package public-atlas-server

# Then the project itself: source, migrations, and the Alembic and FastAPI config in
# apps/server. An editable install, so the venv points at /app/apps/server.
COPY apps/server apps/server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package public-atlas-server

# --- Parser dependencies ------------------------------------------------------
# The `parse-cpu` group (Docling, CPU PyTorch) and its models, so the worker never downloads at
# run time.
FROM build AS build-parse

# OpenCV (behind RapidOCR) needs these even headless.
RUN apt-get update && apt-get install --yes --no-install-recommends \
        libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package public-atlas-server --group parse-cpu

RUN --mount=type=cache,target=/root/.cache/huggingface \
    /app/.venv/bin/docling-tools models download --quiet --output-dir /app/models \
        layout tableformer rapidocr

# --- Runtime ------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS runtime

# Trust X-Forwarded-* from any peer: only the web app's `/api` rewrite reaches the API. Narrow
# this to the web service's network if the API is ever exposed more widely.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FORWARDED_ALLOW_IPS="*"

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# No HEALTHCHECK here: the workers serve no HTTP, so an image-level check would mark them
# unhealthy for good. The deployment gives the `api` process one.

# --- The API and the default-queue worker -------------------------------------
FROM runtime AS server

COPY --from=build --chown=app:app /app /app

# `fastapi run` and `alembic` read pyproject.toml from the working directory.
WORKDIR /app/apps/server
USER app

EXPOSE 8000

# The worker runs `public-atlas-worker --queues default` from the same image.
CMD ["fastapi", "run", "--port", "8000", "--proxy-headers"]

# --- The assignment worker -----------------------------------------------------
# Playwright's Chromium and the system libraries it needs, installed as root into a path every
# user can read. The worker opens pages nobody vetted, so Chromium's own sandbox stays on; it
# needs user namespaces, so give the container `--security-opt seccomp=unconfined` or the
# Playwright seccomp profile if it cannot start.
FROM runtime AS agent

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

COPY --from=build --chown=app:app /app /app

RUN /app/.venv/bin/playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /opt/ms-playwright

WORKDIR /app/apps/server
USER app

# Memory-heavy and mostly waiting on the model: a few sessions per process.
ENV PUBLIC_ATLAS_JOBS_CONCURRENCY=4

CMD ["public-atlas-worker", "--queues", "assignment"]

# --- The parse worker ---------------------------------------------------------
FROM runtime AS parse

# OpenCV's libraries, as in build-parse.
RUN apt-get update && apt-get install --yes --no-install-recommends \
        libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Docling reads its models from here instead of downloading.
ENV DOCLING_ARTIFACTS_PATH=/app/models

COPY --from=build-parse --chown=app:app /app /app

WORKDIR /app/apps/server
USER app

# Docling is CPU-bound: one job per process, scale by processes.
ENV PUBLIC_ATLAS_JOBS_CONCURRENCY=1

CMD ["public-atlas-worker", "--queues", "parse"]
