"""FastAPI dependencies that read the resources the lifespan put on `request.state`.

Every route reads one database: the main one, or, when the request carries `X-Database: eval`,
the eval database an eval run built its graph in (spec section 10). The console sends the
header for every request while its switch is on the eval database, so each of its pages shows
either graph."""

from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.config import Settings
from public_atlas.integrations.storage import ObjectStore
from public_atlas.resources import EvalDatabaseUnavailableError, Resources
from public_atlas.shared.exceptions import UnprocessableError

DATABASE_HEADER = "X-Database"

type Database = Literal["main", "eval"]


def get_resources(request: Request) -> Resources:
    resources: Resources = request.state.resources
    return resources


ResourcesDep = Annotated[Resources, Depends(get_resources)]


def get_settings(resources: ResourcesDep) -> Settings:
    return resources.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_database(
    x_database: Annotated[
        str | None,
        Header(description="`main` (the default) or `eval`: which database the request reads."),
    ] = None,
) -> Database:
    """Which database the request is about."""
    match (x_database or "main").strip().lower():
        case "main":
            return "main"
        case "eval":
            return "eval"
        case other:
            raise UnprocessableError(f"{DATABASE_HEADER} must be main or eval, not {other!r}")


DatabaseDep = Annotated[Database, Depends(get_database)]


async def get_session(
    resources: ResourcesDep, database: DatabaseDep
) -> AsyncIterator[AsyncSession]:
    """One session per request on the database the request names; handlers commit explicitly."""
    try:
        session = resources.session() if database == "main" else resources.eval_session()
    except EvalDatabaseUnavailableError as exc:
        raise UnprocessableError(str(exc)) from None
    async with session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_object_store(resources: ResourcesDep) -> ObjectStore:
    return resources.object_store


ObjectStoreDep = Annotated[ObjectStore, Depends(get_object_store)]
