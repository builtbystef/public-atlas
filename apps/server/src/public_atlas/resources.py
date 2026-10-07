"""What every process works with: the settings, the database, the object store, the job queue,
the search engine, the model and the parser, opened once by `build_resources` and passed as an
argument from there.

The API's lifespan, the worker, the CLI and the tests call `build_resources` with their own
settings. Nothing reads settings or opens a connection at import time.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from procrastinate import App
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from public_atlas.config import Settings
from public_atlas.db.session import create_engine
from public_atlas.integrations.ai import Models, create_models
from public_atlas.integrations.parse import Parser, create_parser
from public_atlas.integrations.search import Searcher, create_searcher
from public_atlas.integrations.storage import ObjectStore, create_object_store
from public_atlas.jobs import create_app

if TYPE_CHECKING:
    from procrastinate import JobContext
    from procrastinate.connector import BaseConnector

# Where a worker's `additional_context` holds the resources.
KEY = "resources"


class EvalDatabaseUnavailableError(LookupError):
    """The eval database is the main database, so there is nothing to switch to."""

    def __init__(self) -> None:
        super().__init__("no eval database is configured apart from the main one")


@dataclass(frozen=True, slots=True)
class Resources:
    settings: Settings
    engine: AsyncEngine
    # Tests swap in a factory whose sessions join one transaction.
    session_factory: Callable[[], AsyncSession]
    # Sessions on the eval database (spec section 10), for the console to read the graph an eval
    # run built; None when the eval database is the main one. Connects on first use.
    eval_session_factory: Callable[[], AsyncSession] | None
    object_store: ObjectStore
    # The job queue: `defer` queues through it and the worker serves it.
    jobs: App
    # None when no search engine is configured: the agent then has no `search` tool.
    searcher: Searcher | None
    # None when no model key is configured: no assignment can run. Tests pass a scripted model.
    models: Models | None
    # Built in every process; only the parse worker loads its models (`warm_up`).
    parser: Parser

    def session(self) -> AsyncSession:
        """A new session. One per request or job run; commit explicitly."""
        return self.session_factory()

    def eval_session(self) -> AsyncSession:
        """A new session on the eval database. Raises when there is none."""
        if self.eval_session_factory is None:
            raise EvalDatabaseUnavailableError
        return self.eval_session_factory()


@asynccontextmanager
async def build_resources(  # noqa: PLR0913 - one argument per double
    settings: Settings,
    *,
    object_store: ObjectStore | None = None,
    jobs_connector: BaseConnector | None = None,
    searcher: Searcher | None = None,
    models: Models | None = None,
    parser: Parser | None = None,
) -> AsyncIterator[Resources]:
    """Open every resource from `settings` and close them on exit. The engine connects lazily;
    the object store and the job queue open their pools here. Tests pass an in-memory
    `object_store`, an in-memory `jobs_connector`, and a `searcher`, `models` and `parser` of
    their own."""
    engine = create_engine(settings)
    jobs = create_app(settings, connector=jobs_connector)
    eval_engine = create_engine(settings.eval_settings()) if settings.has_eval_database else None
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        if eval_engine is not None:
            stack.push_async_callback(eval_engine.dispose)
        if object_store is None:
            object_store = await stack.enter_async_context(create_object_store(settings))
        await stack.enter_async_context(jobs.open_async())
        yield Resources(
            settings=settings,
            engine=engine,
            # Attributes stay readable after commit; async code cannot lazy-reload them.
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            eval_session_factory=(
                async_sessionmaker(eval_engine, expire_on_commit=False)
                if eval_engine is not None
                else None
            ),
            object_store=object_store,
            jobs=jobs,
            searcher=searcher if searcher is not None else create_searcher(settings),
            models=models if models is not None else create_models(settings),
            parser=parser if parser is not None else create_parser(settings),
        )


def worker_context(resources: Resources) -> dict[str, Any]:
    """The `additional_context` to start a worker with."""
    return {KEY: resources}


def resources_of(context: JobContext) -> Resources:
    """The resources the worker running this job was started with."""
    found: Resources = context.additional_context[KEY]
    return found


__all__ = [
    "KEY",
    "EvalDatabaseUnavailableError",
    "Resources",
    "build_resources",
    "resources_of",
    "worker_context",
]
