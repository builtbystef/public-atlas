"""The ASGI entry point for `fastapi run` and `fastapi dev`, the one place the API reads the
environment. Everything else (tests, the eval runner) calls `create_app` with its own settings."""

from public_atlas.config import Settings
from public_atlas.main import create_app

app = create_app(Settings())
