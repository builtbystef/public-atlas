"""A small graph for the status change, review, run and runner tests to work in, built through
the same doors the loader and the rules use: Canada seeded; the region Elm with its government,
a trusted domain and a verified homepage; the town Oakville under it with a government that has
no homepage yet; and a step-mode run. `Build` adds to it the same way; it is reached through a
fixture because the tests are collected in importlib mode, with no `tests` package to import.
A scripted model stands in for every model choice when a test runs the agent."""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.integrations.ai import FixedModels
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    Run,
    RunMode,
)
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Domain,
    DomainKind,
    EnteredBy,
    Homepage,
    Institution,
    Place,
    Webpage,
)

if TYPE_CHECKING:
    from tests.integration.conftest import Database, InlineConnector

    from public_atlas.integrations.storage import ObjectStore
    from public_atlas.resources import Resources

BY = EnteredBy.SCRIPT


@dataclass
class World:
    rules: countries.CountryRules
    ontario: Place
    elm: Place
    county: Institution
    elm_domain: Domain
    elm_homepage: Homepage
    oakville: Place
    town: Institution
    run: Run


class Build:
    """The ways a test adds to the world, through the doors the rules use."""

    @staticmethod
    async def verified_place(session: AsyncSession, name: str, level: str, parent: Place) -> Place:
        place = await graph.create_place(
            session,
            name=name,
            country_code="CA",
            administrative_level=level,
            parent=parent,
            entered_by=BY,
        )
        await status_changes.verify_place(session, place, entered_by=BY)
        return place

    @staticmethod
    async def verified_government(session: AsyncSession, place: Place, name: str) -> Institution:
        level = place.administrative_level
        government = await graph.create_institution(
            session,
            name=name,
            institution_type=f"{'regional' if level == 'region' else 'municipal'}_government",
            place=place,
            entered_by=BY,
        )
        await status_changes.verify_institution(session, government, entered_by=BY)
        place.government_institution_id = government.id
        await session.flush()
        return government

    @staticmethod
    async def candidate_institution(
        session: AsyncSession,
        place: Place,
        name: str,
        institution_type: str = "library",
        *,
        suggested_type: str | None = None,
    ) -> Institution:
        return await graph.create_institution(
            session,
            name=name,
            institution_type=institution_type,
            place=place,
            entered_by=EnteredBy.AGENT,
            suggested_type=suggested_type,
        )

    @staticmethod
    async def claim(
        session: AsyncSession,
        institution: Institution,
        url: str,
        *,
        found_on: Webpage | None = None,
    ) -> Homepage:
        """A candidate homepage claim on `url`, with a candidate domain when the host is new."""
        domain, _ = await graph.ensure_domain(
            session, graph.host_of(url), entered_by=EnteredBy.AGENT
        )
        webpage = await graph.ensure_webpage(session, url, domain=domain)
        return await graph.create_homepage(
            session, institution, webpage, entered_by=EnteredBy.AGENT, found_on=found_on
        )

    @staticmethod
    async def capture(
        session: AsyncSession,
        store: ObjectStore,
        url: str,
        html: str,
        text: str,
        *,
        assignment_id: uuid.UUID | None = None,
    ) -> tuple[Webpage, Snapshot]:
        """A stored copy of a page, as the capture hook would make one."""
        webpage = await graph.ensure_webpage(session, url, assignment_id=assignment_id)
        snapshot, _ = await evidence.store_snapshot(
            session,
            store,
            webpage,
            html.encode(),
            text=text,
            media_type=evidence.HTML,
            filename="page.html",
            assignment_id=assignment_id,
        )
        return webpage, snapshot

    @staticmethod
    async def open_assignment(
        session: AsyncSession,
        run: Run,
        assignment_type: AssignmentType,
        subject_id: uuid.UUID,
        *,
        status: AssignmentStatus = AssignmentStatus.QUEUED,
    ) -> Assignment:
        assignment = Assignment(
            run_id=run.id,
            type=assignment_type,
            subject_id=subject_id,
            status=status,
            budget_requests=10,
            budget_tokens=1000,
        )
        session.add(assignment)
        await session.flush()
        return assignment


async def build_world(db: Database) -> World:
    async with db.session() as session:
        await countries.seed(session, canada.SEED)
        rules = await countries.load_rules(session, "CA")
        ontario = (await session.scalars(select(Place).where(Place.name == "Ontario"))).one()
        elm = await Build.verified_place(session, "Elm", "region", ontario)
        county = await Build.verified_government(session, elm, "County of Elm")
        elm_domain = await graph.create_domain(
            session, "elmcounty.ca", kind=DomainKind.OFFICIAL, entered_by=BY
        )
        await status_changes.verify_domain(session, elm_domain, entered_by=BY)
        page = await graph.ensure_webpage(session, "https://www.elmcounty.ca/", domain=elm_domain)
        elm_homepage = await graph.create_homepage(session, county, page, entered_by=BY)
        await status_changes.verify_homepage(session, elm_homepage, entered_by=BY)
        oakville = await Build.verified_place(session, "Oakville", "municipality", elm)
        town = await Build.verified_government(session, oakville, "Town of Oakville")
        run = Run(name="test", country_code="CA", mode=RunMode.STEP)
        session.add(run)
        await session.commit()
        return World(
            rules=rules,
            ontario=ontario,
            elm=elm,
            county=county,
            elm_domain=elm_domain,
            elm_homepage=elm_homepage,
            oakville=oakville,
            town=town,
            run=run,
        )


@pytest.fixture
def world(db: Database) -> World:
    return db.run(build_world, db)


@pytest.fixture
def build() -> type[Build]:
    return Build


# --- A scripted model ---

type Script = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


def last_prompt(messages: list[ModelMessage]) -> str:
    """The newest user prompt: the briefing, or the handoff request appended to the history."""
    return next(
        str(getattr(part, "content", ""))
        for message in reversed(messages)
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )


def calls_made(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(part, ToolCallPart)
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
    )


_UNACCOUNTED = re.compile(r"named in types_not_found: ([^.]+)\.")


def finishing(summary: str = "Nothing more to find.") -> Script:
    """A model that finishes at once, and, when the finish is refused for a type left
    unaccounted for, finishes again naming the types as not found, as an agent would."""

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        args: dict[str, object] = {"summary": summary}
        last = messages[-1].parts[0] if messages and messages[-1].parts else None
        if isinstance(last, RetryPromptPart):
            found = _UNACCOUNTED.search(str(last.content))
            if found:
                args["types_not_found"] = [name.strip() for name in found.group(1).split(",")]
        return ModelResponse(parts=[ToolCallPart("finish", args)])

    return script


@pytest.fixture
def scripted(queue: InlineConnector) -> Callable[[Script], Resources]:
    """Install `script` as the model every session runs on, for the inline jobs too, and return
    the resources to run an assignment with directly."""

    def install(script: Script) -> Resources:
        assert queue.resources is not None
        queue.resources = replace(
            queue.resources,
            models=FixedModels(FunctionModel(script, model_name="scripted")),
        )
        return queue.resources

    return install


@pytest.fixture
def prompt_of() -> Callable[[list[ModelMessage]], str]:
    return last_prompt


@pytest.fixture
def count_calls() -> Callable[[list[ModelMessage]], int]:
    return calls_made


@pytest.fixture
def finish_script() -> Callable[..., Script]:
    return finishing
