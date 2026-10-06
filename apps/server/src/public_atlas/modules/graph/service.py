"""The graph's doors for other modules: URLs and domain names in one spelling, the domain and
webpage rows a URL needs, and the aliases a place or institution goes by. Phase 3 adds the rest
(duplicate search, `status_changes.py`)."""

import re
import uuid
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Institution,
    Place,
    Webpage,
)

_DOMAIN_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN = re.compile(rf"^(?:{_DOMAIN_LABEL}\.)+{_DOMAIN_LABEL}$")
MAX_DOMAIN_LENGTH = 253


def is_domain_name(value: str) -> bool:
    return bool(_DOMAIN.match(value.lower())) and len(value) <= MAX_DOMAIN_LENGTH


def normalize_url(url: str) -> str:
    """One spelling per page: lower-cased scheme and host, no fragment, no default port, and a
    trailing slash on a bare host. A bare "www.elmwood.ca" gets the scheme it leaves out."""
    url = url.strip()
    if "://" not in url:
        url = f"http://{url}"
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def candidate_domain_name(host: str) -> str:
    """The domain a first link to `host` creates: the host without a leading `www.`. The
    allowlist admits `www.x` under `x` but not the reverse, so a site that redirects `www.x` to
    `x` (or to `en.x`) would otherwise be refused inside its own assignment."""
    host = host.lower()
    bare = host.removeprefix("www.")
    return bare if is_domain_name(bare) else host


async def domain_by_name(session: AsyncSession, name: str) -> Domain | None:
    return await session.scalar(select(Domain).where(Domain.name == name.lower()))


async def domain_of_host(session: AsyncSession, host: str) -> Domain | None:
    """The domain row that covers `host`, subdomains included: the longest match when several
    do (`toronto.bidsandtenders.ca` is under `bidsandtenders.ca`)."""
    labels = host.lower().split(".")
    candidates = [".".join(labels[i:]) for i in range(len(labels) - 1)]
    if not candidates:
        return None
    rows = list(await session.scalars(select(Domain).where(Domain.name.in_(candidates))))
    if not rows:
        return None
    return max(rows, key=lambda domain: len(domain.name))


async def ensure_domain(
    session: AsyncSession, host: str, *, status: EntityStatus, entered_by: EnteredBy
) -> tuple[Domain, bool]:
    """The domain that covers `host`, or a new official one named for it with the status given.
    Whether it was created."""
    found = await domain_of_host(session, host)
    if found is not None:
        return found, False
    domain = Domain(
        name=candidate_domain_name(host),
        domain_kind=DomainKind.OFFICIAL,
        status=status,
        entered_by=entered_by,
    )
    session.add(domain)
    await session.flush()
    return domain, True


async def webpage_by_url(session: AsyncSession, url: str) -> Webpage | None:
    return await session.scalar(select(Webpage).where(Webpage.url == normalize_url(url)))


async def ensure_webpage(
    session: AsyncSession, url: str, domain: Domain, *, assignment_id: uuid.UUID | None = None
) -> Webpage:
    """The row for `url`, created if new. Two writers may race for one URL (the agent's tool calls
    from one response run at once); the savepoint lets the loser take the winner's row."""
    normalized = normalize_url(url)
    webpage = await webpage_by_url(session, normalized)
    if webpage is None:
        webpage = Webpage(
            url=normalized, domain_id=domain.id, first_seen_assignment_id=assignment_id
        )
        try:
            async with session.begin_nested():
                session.add(webpage)
                await session.flush()
        except IntegrityError:
            webpage = await webpage_by_url(session, normalized)
            if webpage is None:  # pragma: no cover - the other writer's row is committed
                raise
    return webpage


async def aliases_of(
    session: AsyncSession, owners: Iterable[Place | Institution]
) -> dict[uuid.UUID, list[str]]:
    """Every alias text of each owner, by owner id. One query for a batch."""
    owners = list(owners)
    if not owners:
        return {}
    column = Alias.place_id if isinstance(owners[0], Place) else Alias.institution_id
    rows = await session.execute(
        select(column, Alias.text).where(column.in_([owner.id for owner in owners]))
    )
    found: dict[uuid.UUID, list[str]] = {owner.id: [] for owner in owners}
    for owner_id, text in rows:
        found[owner_id].append(text)
    return found


async def add_alias(  # noqa: PLR0913
    session: AsyncSession,
    owner: Place | Institution,
    text: str,
    *,
    language: str,
    entered_by: EnteredBy,
    is_acronym: bool = False,
) -> bool:
    """Whether the alias was added; one the owner has already is left as it is."""
    text = " ".join(text.split())
    owner_column = Alias.place_id if isinstance(owner, Place) else Alias.institution_id
    found = await session.scalar(
        select(Alias.id).where(owner_column == owner.id, Alias.text == text)
    )
    if found is not None:
        return False
    alias = Alias(text=text, language=language, is_acronym=is_acronym, entered_by=entered_by)
    if isinstance(owner, Place):
        alias.place_id = owner.id
    else:
        alias.institution_id = owner.id
    session.add(alias)
    await session.flush()
    return True
