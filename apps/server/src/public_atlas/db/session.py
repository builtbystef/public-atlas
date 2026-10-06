from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from public_atlas.shared import telemetry

if TYPE_CHECKING:
    from public_atlas.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """`pool_pre_ping` drops a connection the server closed (a restart, a failover) instead of
    handing it to a request; the statement timeout is set per connection, so a runaway query
    cannot hold a pooled connection for good. Connects lazily."""
    timeout_ms = int(settings.database_statement_timeout.total_seconds() * 1000)
    engine = create_async_engine(
        str(settings.database_url),
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        connect_args={"options": f"-c statement_timeout={timeout_ms}"},
    )
    if telemetry.enabled(settings):
        telemetry.instrument_engine(engine)
    return engine
