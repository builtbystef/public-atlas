"""The API. `create_app` builds it from a `Settings`; the lifespan opens the resources once and
puts them on `request.state` (dependencies.py reads them from there)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from public_atlas.config import Settings
from public_atlas.modules.router import router as api_router
from public_atlas.resources import build_resources
from public_atlas.shared import logs, telemetry
from public_atlas.shared.exceptions import AppError, handle_app_error
from public_atlas.shared.middleware import RequestIdMiddleware
from public_atlas.shared.routing import generate_unique_id

if TYPE_CHECKING:
    from procrastinate.connector import BaseConnector

    from public_atlas.integrations.storage import ObjectStore

TITLE = "Public Atlas API"


def create_app(
    settings: Settings,
    *,
    object_store: ObjectStore | None = None,
    jobs_connector: BaseConnector | None = None,
) -> FastAPI:
    """The doubles go to `build_resources`; tests pass an in-memory store and queue."""
    logs.configure(settings.log_level, settings.log_format)
    if (handler := telemetry.configure(settings, service_name="public-atlas-server")) is not None:
        logging.getLogger().addHandler(handler)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[dict[str, object]]:
        """The yielded dict becomes `request.state`."""
        async with build_resources(
            settings, object_store=object_store, jobs_connector=jobs_connector
        ) as resources:
            yield {"resources": resources}

    app = FastAPI(
        title=TITLE,
        generate_unique_id_function=generate_unique_id,
        lifespan=lifespan,
        # Routes have no trailing slash (the web app's `/api` rewrite drops one), and a redirect
        # would point the browser at the API's internal address.
        redirect_slashes=False,
    )
    if telemetry.enabled(settings):
        telemetry.instrument_app(app)
    # Added after instrumentation, so it runs inside the Logfire span and the request ID reaches
    # its logs. No CORS and no body limit: browsers reach the API through the web app's
    # same-origin `/api` rewrite.
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, handle_app_error)
    app.include_router(api_router)
    return app
