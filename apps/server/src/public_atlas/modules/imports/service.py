"""The shared list loader (spec section 5.2), written once: it never changes when a list is
added. It opens the module's files (fetched, hash-checked and cached, or collected by hand and
read from the cache), stores each as a snapshot and an `official_lists` row, asks the module
for its entries, and writes what the database lacks: a place by its code, then by its name
under the same parent, with its government, identifier, metrics, aliases, candidate homepage
and an evidence row quoting the list's own line for each fact.

Every run writes in the session and reports what it changed; the caller commits an apply and
rolls a dry run back, so the diff a dry run prints is exactly what an apply would do. A second
apply changes nothing.
"""

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.parse import Parser
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Homepage,
    Identifier,
    Institution,
    InstitutionServedPlace,
    Metric,
    Place,
)
from public_atlas.modules.imports import files, lists
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Entry,
    Figure,
    InstitutionEntry,
    PlaceEntry,
)
from public_atlas.modules.imports.models import OfficialList, Retrieval

logger = logging.getLogger(__name__)

type Action = Literal["add", "change", "remove"]

# How many additions of one table the report lists before counting the rest.
LISTED_ADDITIONS = 20


@dataclass(frozen=True, slots=True)
class Change:
    action: Action
    table: str
    label: str
    detail: str = ""

    def render(self) -> str:
        sign = {"add": "+", "change": "~", "remove": "-"}[self.action]
        detail = f" ({self.detail})" if self.detail else ""
        return f"{sign} {self.table} {self.label}{detail}"


@dataclass
class LoadReport:
    """What a load did, or would do."""

    list_name: str
    applied: bool
    sources: list[str] = field(default_factory=list)
    entries: int = 0
    changes: list[Change] = field(default_factory=list)
    # Entries left as they are, with the reason.
    skipped: list[str] = field(default_factory=list)
    # Keys of the module's `OVERRIDES` that matched no entry: a new export or a bumped hash can
    # strand one.
    idle_overrides: list[str] = field(default_factory=list)

    def count(self, action: Action, table: str | None = None) -> int:
        return sum(
            1
            for change in self.changes
            if change.action == action and (table is None or change.table == table)
        )

    def counts(self) -> Counter[tuple[Action, str]]:
        return Counter((change.action, change.table) for change in self.changes)

    def render(self) -> str:
        mode = "applied" if self.applied else "dry run: nothing written"
        lines = [
            f"{self.list_name}: {self.entries} entries from {len(self.sources)} sources ({mode})"
        ]
        if not self.changes:
            lines.append("  nothing to change")
        for (action, table), count in sorted(self.counts().items()):
            lines.append(f"  {Change(action, table, '').render().strip()}: {count}")
        listed: Counter[str] = Counter()
        for change in self.changes:
            if change.action == "add":
                listed[change.table] += 1
                if listed[change.table] > LISTED_ADDITIONS:
                    continue
            lines.append(f"    {change.render()}")
        for table, count in listed.items():
            if count > LISTED_ADDITIONS:
                lines.append(f"    + {table}: {count - LISTED_ADDITIONS} more")
        if self.skipped:
            lines.append(f"  skipped: {len(self.skipped)}")
            lines.extend(f"    {line}" for line in self.skipped)
        if self.idle_overrides:
            lines.append(f"  overrides that matched nothing: {len(self.idle_overrides)}")
            lines.extend(f"    {line}" for line in self.idle_overrides)
        return "\n".join(lines)


class Skip(Exception):  # noqa: N818 - a signal, not an error
    """An entry the loader leaves as it is, with the reason."""


def module_name(module: ModuleType) -> str:
    """The list's name: its path under `lists/` with slashes (`canada/ontario/places`), so two
    provinces' `places` modules do not collide. `official_lists.name` starts with it."""
    return lists.list_name(module.__name__)


async def load_list(  # noqa: PLR0913 - the resources a load needs
    session: AsyncSession,
    store: ObjectStore,
    module: ModuleType,
    *,
    cache_dir: Path,
    apply: bool,
    parser: Parser | None = None,
) -> LoadReport:
    """Load one list module. Flushed, not committed: the caller commits when `apply` and rolls
    back otherwise. The object store is written only when `apply`. `parser` reads a PDF list."""
    name = module_name(module)
    report = LoadReport(list_name=name, applied=apply)
    rules = await countries.load_rules(session, module.COUNTRY)
    opened: dict[str, files.OpenedFile] = {}
    for file in module.SOURCES:
        opened[file.name] = await asyncio.to_thread(files.open_file, file, cache_dir, parser=parser)
        report.sources.append(file.name)
    entries: list[Entry] = list(module.entries(opened, rules))
    report.entries = len(entries)
    report.idle_overrides = idle_overrides(getattr(module, "OVERRIDES", {}), entries)
    for line in report.idle_overrides:
        logger.warning("%s: override %s matched nothing", name, line)
    loader = Loader(
        session=session,
        store=store,
        rules=rules,
        list_name=name,
        files=opened,
        apply=apply,
        report=report,
    )
    await loader.store_sources(module.SOURCES)
    for entry in loader.ordered(entries):
        try:
            await loader.load(entry)
        except Skip as skip:
            report.skipped.append(f"{entry.name}: {skip}")
    await loader.report_removed(entries)
    await session.flush()
    return report


def idle_overrides(overrides: Mapping[str, object], entries: Sequence[Entry]) -> list[str]:
    """The override keys no entry answers to: an override is keyed by a code, a name or an
    alias of the entry it corrects, so a key none of the entries carries corrected nothing."""
    keyed: set[str] = set()
    for entry in entries:
        keyed.add(entry.name)
        keyed.update(alias.text for alias in entry.aliases)
        if isinstance(entry, PlaceEntry):
            keyed.add(entry.code.value)
    return [key for key in overrides if key not in keyed]


def manifest(cache_dir: Path, modules: Mapping[str, ModuleType] = lists.LISTS) -> str:
    """The from-scratch checklist, read from the list modules so it cannot drift from them: the
    fetched URLs with their hashes, then the manual files with the steps that obtain each and
    where in the cache it goes."""
    fetched: list[str] = []
    manual: list[str] = []
    for name, module in modules.items():
        for file in module.SOURCES:
            if file.retrieval is Retrieval.FETCHED:
                fetched.append(f"{name}/{file.name}: {file.title}")
                fetched.append(f"  {file.url}")
                fetched.append(f"  sha256 {file.sha256}")
            else:
                manual.append(f"{name}/{file.name}: {file.title}")
                manual.append(f"  {file.url}")
                manual.append(f"  put it at {file.cache_path(cache_dir)}")
                if file.min_rows:
                    manual.append(f"  at least {file.min_rows} rows")
                manual.extend(f"  {line}" for line in file.instructions.strip().splitlines())
    lines = [f"Fetched files ({len(fetched) // 3})", *fetched]
    if not fetched:
        lines.append("  none")
    lines.append("")
    lines.append(f"Manual files ({sum(1 for line in manual if not line.startswith(' '))})")
    lines.extend(manual or ["  none"])
    return "\n".join(lines)


@dataclass
class Known:
    """A place with the forms of its names, for matching by name."""

    row: Place
    forms: set[str]


@dataclass
class Loader:
    session: AsyncSession
    store: ObjectStore
    rules: CountryRules
    list_name: str
    files: Mapping[str, files.OpenedFile]
    apply: bool
    report: LoadReport
    # By source name, once stored.
    lists: dict[str, tuple[OfficialList, Snapshot]] = field(default_factory=dict)
    # The country's places by level, with their aliases' forms, read once per level and kept
    # current with what this run adds.
    known: dict[str, list[Known]] = field(default_factory=dict)

    # --- Sources ---

    async def store_sources(self, sources: Iterable[files.ListFile]) -> None:
        """Each file as a snapshot on a webpage of its own domain, and its `official_lists` row
        with the hash of the file as given, fetched or by hand. A list's domain is trusted from
        the start (spec section 6.1)."""
        for file in sources:
            opened = self.files[file.name]
            domain, created = await graph.ensure_domain(
                self.session, graph.host_of(file.url), entered_by=EnteredBy.SCRIPT
            )
            if not graph.is_trusted(domain):
                await status_changes.verify_domain(
                    self.session, domain, entered_by=EnteredBy.SCRIPT
                )
            if created:
                self.changed("add", "domain", domain.name, "trusted: an official list's")
            webpage = await graph.ensure_webpage(self.session, file.url, domain=domain)
            snapshot, created = await evidence.store_snapshot(
                self.session,
                self.store,
                webpage,
                opened.data,
                text=opened.text,
                media_type=file.media_type,
                filename=file.filename,
                write_store=self.apply,
            )
            if created:
                self.changed("add", "snapshot", file.filename, f"{len(opened.lines)} lines")
            list_name = f"{self.list_name}/{file.name}"
            row = await self.session.scalar(
                select(OfficialList).where(
                    OfficialList.name == list_name, OfficialList.sha256 == opened.sha256
                )
            )
            if row is None:
                row = OfficialList(
                    name=list_name,
                    title=file.title,
                    url=file.url,
                    sha256=opened.sha256,
                    retrieval=file.retrieval,
                    retrieved_at=utcnow(),
                    snapshot_id=snapshot.id,
                )
                self.session.add(row)
                await self.session.flush()
                self.changed("add", "official_list", list_name, file.retrieval.value)
            self.lists[file.name] = (row, snapshot)

    def cited(self, citation: Citation) -> tuple[OfficialList, Snapshot, str]:
        """The list, its snapshot and the quoted line."""
        if citation.source not in self.lists:
            raise Skip(f"cites a source the module does not list: {citation.source!r}")
        official_list, snapshot = self.lists[citation.source]
        try:
            quote = self.files[citation.source].line(citation.line)
        except IndexError:
            raise Skip(
                f"cites line {citation.line} of {citation.source}, which has fewer"
            ) from None
        return official_list, snapshot, quote

    # --- Entries ---

    def ordered(self, entries: Sequence[Entry]) -> list[Entry]:
        """Places top-down, so a parent is loaded before its children; institutions after the
        places they sit under."""
        places = [entry for entry in entries if isinstance(entry, PlaceEntry)]
        institutions = [entry for entry in entries if isinstance(entry, InstitutionEntry)]
        places.sort(
            key=lambda entry: (self.rules.levels.get(entry.level, None) is None, entry.name)
        )
        places.sort(
            key=lambda entry: (
                self.rules.rank_of(entry.level) if entry.level in self.rules.levels else 0
            )
        )
        return [*places, *institutions]

    async def load(self, entry: Entry) -> None:
        if isinstance(entry, PlaceEntry):
            await self._load_place(entry)
        else:
            await self._load_institution(entry)

    def changed(self, action: Action, table: str, label: str, detail: str = "") -> None:
        self.report.changes.append(Change(action, table, label, detail))

    # --- Places ---

    async def _load_place(self, entry: PlaceEntry) -> None:
        if entry.level not in self.rules.levels:
            raise Skip(f"{self.rules.name} has no administrative level {entry.level!r}")
        parent = None
        if entry.parent is not None:
            parent = await self._find_place(entry.parent, self.rules.levels_above(entry.level))
            if parent is None:
                raise Skip(f"parent {entry.parent!r} is not loaded above level {entry.level!r}")
        elif self.rules.rank_of(entry.level) != self.rules.levels_by_rank[0].rank:
            raise Skip("no parent, and not at the top level")
        place = await self._match_place(entry, parent)
        label = f"{entry.name} ({entry.level})"
        await self._aliases(place, entry.name, entry.language, entry.aliases)
        official_list, snapshot, quote = self.cited(entry.citations["place"])
        await self._identifier(place, entry.code, official_list, label)
        for figure in entry.figures:
            await self._metric(place, figure, label)
        await self._cite(place.id, snapshot, quote, entry.citations["place"], label)
        if entry.government is not None:
            await self._government(place, entry, label)

    async def _match_place(self, entry: PlaceEntry, parent: Place | None) -> Place:
        """The entry's place: the one holding its code, else the one at its level under the
        same parent that goes by its name, else a new one. A matched place moves under the
        parent the list names."""
        label = f"{entry.name} ({entry.level})"
        place = await self._by_code(entry.code)
        if place is not None and place.administrative_level != entry.level:
            raise Skip(
                f"code {entry.code.value} is held by {place.name!r} at level "
                f"{place.administrative_level!r}"
            )
        if place is None:
            forms = self._entry_forms(entry.name, entry.aliases)
            found = [
                known.row
                for known in await self._known(entry.level)
                if known.forms & forms
                and (parent is None or known.row.parent_place_id == parent.id)
            ]
            if len(found) > 1:
                raise Skip(f"{len(found)} places go by that name at level {entry.level!r}")
            place = found[0] if found else None
        if place is None:
            place = await graph.create_place(
                self.session,
                name=entry.name,
                country_code=self.rules.country_code,
                administrative_level=entry.level,
                parent=parent,
                entered_by=EnteredBy.SCRIPT,
                language=entry.language,
            )
            await status_changes.verify_place(self.session, place, entered_by=EnteredBy.SCRIPT)
            (await self._known(entry.level)).append(Known(place, set()))
            self.changed(
                "add", "place", label, f"under {parent.name}" if parent is not None else ""
            )
        elif parent is not None and place.parent_place_id != parent.id:
            place.parent_place_id = parent.id
            self.changed("change", "place", label, f"moved under {parent.name}")
        return place

    async def _by_code(self, code: Code) -> Place | None:
        held = await self.session.scalar(
            select(Identifier).where(
                Identifier.scheme == code.scheme,
                Identifier.value == code.value,
                Identifier.place_id.is_not(None),
            )
        )
        if held is None or held.place_id is None:
            return None
        return await self.session.get(Place, held.place_id)

    async def _find_place(self, name: str, levels: list[str]) -> Place | None:
        """The one place at any of `levels` that goes by `name`."""
        forms = self.rules.naming.forms(name)
        found: list[Place] = []
        for level in levels:
            found.extend(known.row for known in await self._known(level) if known.forms & forms)
        if len(found) > 1:
            raise Skip(f"{len(found)} places go by {name!r} at levels {levels}")
        return found[0] if found else None

    async def _known(self, level: str) -> list[Known]:
        """The country's places at `level` with the forms of their names, read once."""
        if level not in self.known:
            places = list(
                await self.session.scalars(
                    select(Place).where(
                        Place.country_code == self.rules.country_code,
                        Place.administrative_level == level,
                        Place.status != EntityStatus.REJECTED,
                    )
                )
            )
            aliases = await graph.aliases_of(self.session, places)
            self.known[level] = [
                Known(place, self._forms([place.name, *aliases[place.id]])) for place in places
            ]
        return self.known[level]

    def _forms(self, names: Iterable[str]) -> set[str]:
        forms: set[str] = set()
        for name in names:
            forms |= self.rules.naming.forms(name)
        return forms

    def _entry_forms(self, name: str, aliases: Iterable[AliasEntry]) -> set[str]:
        return self._forms([name, *(alias.text for alias in aliases)])

    async def _aliases(
        self,
        owner: Place | Institution,
        name: str,
        language: str,
        aliases: Iterable[AliasEntry],
    ) -> None:
        wanted = [AliasEntry(text=name, language=language), *aliases]
        added = 0
        for alias in wanted:
            if await graph.add_alias(
                self.session,
                owner,
                alias.text,
                language=alias.language,
                entered_by=EnteredBy.SCRIPT,
                is_acronym=alias.is_acronym,
            ):
                added += 1
        if added:
            table = "place" if isinstance(owner, Place) else "institution"
            self.changed("add", f"{table} alias", owner.name, f"{added}")
        if isinstance(owner, Place):
            for known in self.known.get(owner.administrative_level, []):
                if known.row is owner:
                    known.forms |= self._forms(alias.text for alias in wanted)

    async def _identifier(
        self, place: Place, code: Code, official_list: OfficialList, label: str
    ) -> None:
        """The place's code: added, or changed when the place held another in the scheme. A code
        another place holds is left to it and reported."""
        held = await self.session.scalar(
            select(Identifier).where(
                Identifier.scheme == code.scheme, Identifier.value == code.value
            )
        )
        if held is not None:
            if held.place_id != place.id:
                raise Skip(f"code {code.value} is held by another entity")
            return
        mine = await self.session.scalar(
            select(Identifier).where(
                Identifier.place_id == place.id, Identifier.scheme == code.scheme
            )
        )
        if mine is None:
            self.session.add(
                Identifier(
                    place_id=place.id,
                    scheme=code.scheme,
                    value=code.value,
                    official_list_id=official_list.id,
                )
            )
            self.changed("add", "identifier", label, f"{code.scheme} {code.value}")
        else:
            self.changed("change", "identifier", label, f"{mine.value} -> {code.value}")
            mine.value = code.value
            mine.official_list_id = official_list.id
        await self.session.flush()

    async def _metric(self, place: Place, figure: Figure, label: str) -> None:
        official_list, _, _ = self.cited(figure.citation)
        metric = await self.session.scalar(
            select(Metric).where(
                Metric.place_id == place.id, Metric.name == figure.name, Metric.year == figure.year
            )
        )
        if metric is None:
            self.session.add(
                Metric(
                    place_id=place.id,
                    name=figure.name,
                    year=figure.year,
                    value=figure.value,
                    official_list_id=official_list.id,
                )
            )
            self.changed("add", "metric", label, f"{figure.name} {figure.year}: {figure.value}")
        elif metric.value != figure.value:
            self.changed(
                "change",
                "metric",
                label,
                f"{figure.name} {figure.year}: {metric.value} -> {figure.value}",
            )
            metric.value = figure.value
            metric.official_list_id = official_list.id
        await self.session.flush()

    async def _cite(  # noqa: PLR0913 - the quote and where it sits
        self,
        entity_id: uuid.UUID,
        snapshot: Snapshot,
        quote: str,
        citation: Citation,
        label: str,
        *,
        kind: EvidenceKind = EvidenceKind.APPEARS_ON,
        link_url: str | None = None,
    ) -> None:
        if await evidence.add_evidence(
            self.session,
            entity_id=entity_id,
            snapshot=snapshot,
            kind=kind,
            quote=quote,
            locator=citation.line,
            link_url=link_url,
            entered_by=EnteredBy.SCRIPT,
        ):
            self.changed("add", "evidence", label, f"{citation.source} line {citation.line}")

    async def _government(self, place: Place, entry: PlaceEntry, label: str) -> None:
        """The place's government: created verified when the place has none; named, cited and
        given its candidate homepage either way."""
        assert entry.government is not None  # noqa: S101 - the caller checked
        if place.government_institution_id is None:
            government = await graph.create_institution(
                self.session,
                name=entry.government,
                institution_type=self.rules.government_type(entry.level),
                place=place,
                entered_by=EnteredBy.SCRIPT,
                language=entry.language,
            )
            await status_changes.verify_institution(
                self.session, government, entered_by=EnteredBy.SCRIPT
            )
            place.government_institution_id = government.id
            await self.session.flush()
            self.changed("add", "institution", entry.government, f"government of {label}")
        else:
            government = await self.session.get_one(Institution, place.government_institution_id)
        await self._aliases(government, entry.government, entry.language, ())
        citation = entry.government_citation
        _, snapshot, quote = self.cited(citation)
        await self._cite(government.id, snapshot, quote, citation, entry.government)
        if entry.homepage is not None:
            await self._homepage(government, entry.homepage, entry.citations["homepage"])

    async def _homepage(self, institution: Institution, url: str, citation: Citation) -> None:
        """The list's link as a candidate homepage of the institution, on a candidate domain when
        the domain is new, with the list's line as the evidence that links to it. The loader
        has no run to spawn into: the `find_homepage` this asks for (spec section 7.3) is
        created when a run covering the place seeds itself (`assignments.service.seed_run`)."""
        normalized = graph.normalize_url(url)
        webpage = await graph.webpage_by_url(self.session, normalized)
        if webpage is None:
            domain, created = await graph.ensure_domain(
                self.session, graph.host_of(normalized), entered_by=EnteredBy.SCRIPT
            )
            if created:
                self.changed("add", "domain", domain.name, "candidate")
            webpage = await graph.ensure_webpage(self.session, normalized, domain=domain)
        homepage = await self.session.scalar(
            select(Homepage).where(
                Homepage.institution_id == institution.id, Homepage.webpage_id == webpage.id
            )
        )
        if homepage is None:
            if institution.homepage_id is not None:
                self.report.skipped.append(
                    f"{institution.name}: has a verified homepage already; {normalized} not claimed"
                )
                return
            homepage = await graph.create_homepage(
                self.session, institution, webpage, entered_by=EnteredBy.SCRIPT
            )
            self.changed("add", "homepage", institution.name, f"{normalized} (candidate)")
        _, snapshot, quote = self.cited(citation)
        await self._cite(
            homepage.id,
            snapshot,
            quote,
            citation,
            institution.name,
            kind=EvidenceKind.LINKS_TO,
            link_url=normalized,
        )

    # --- Institutions ---

    async def _load_institution(self, entry: InstitutionEntry) -> None:
        if entry.institution_type not in self.rules.institution_types:
            raise Skip(f"no institution type {entry.institution_type!r}")
        place = await self._find_place(entry.place, list(self.rules.levels))
        if place is None:
            raise Skip(f"place {entry.place!r} is not loaded")
        label = f"{entry.name} ({entry.institution_type})"
        institution, created = await self._match_institution(entry, place, label)
        await self._aliases(institution, entry.name, entry.language, entry.aliases)
        if created or institution.parent_institution_id is None:
            institution.parent_institution_id = await self._parent_institution(entry, place)
        for served in entry.served_places:
            await self._served_place(institution, served, label)
        _, snapshot, quote = self.cited(entry.citations["institution"])
        await self._cite(institution.id, snapshot, quote, entry.citations["institution"], label)
        if entry.homepage is not None:
            await self._homepage(institution, entry.homepage, entry.citations["homepage"])

    async def _match_institution(
        self, entry: InstitutionEntry, place: Place, label: str
    ) -> tuple[Institution, bool]:
        """The institution of the entry's type at the place that goes by its name, else a new
        verified one. Whether it was created."""
        found = await self._institutions_named(
            place, self._entry_forms(entry.name, entry.aliases), entry.institution_type
        )
        if len(found) > 1:
            raise Skip(f"{len(found)} institutions go by that name at {place.name}")
        if found:
            return found[0], False
        institution = await graph.create_institution(
            self.session,
            name=entry.name,
            institution_type=entry.institution_type,
            place=place,
            entered_by=EnteredBy.SCRIPT,
            language=entry.language,
        )
        await status_changes.verify_institution(
            self.session, institution, entered_by=EnteredBy.SCRIPT
        )
        self.changed("add", "institution", label, f"at {place.name}")
        return institution, True

    async def _institutions_named(
        self, place: Place, forms: AbstractSet[str], institution_type: str | None
    ) -> list[Institution]:
        query = select(Institution).where(
            Institution.place_id == place.id, Institution.status != EntityStatus.REJECTED
        )
        if institution_type is not None:
            query = query.where(Institution.institution_type == institution_type)
        rows = list(await self.session.scalars(query))
        aliases = await graph.aliases_of(self.session, rows)
        return [row for row in rows if self._forms([row.name, *aliases[row.id]]) & forms]

    async def _parent_institution(self, entry: InstitutionEntry, place: Place) -> uuid.UUID | None:
        """The body the entry says it sits under, or the place's government."""
        if entry.parent_institution is None:
            return place.government_institution_id
        found = await self._institutions_named(
            place, self.rules.naming.forms(entry.parent_institution), None
        )
        if len(found) != 1:
            raise Skip(
                f"parent institution {entry.parent_institution!r} is not one body at {place.name}"
            )
        return found[0].id

    async def _served_place(self, institution: Institution, name: str, label: str) -> None:
        served = await self._find_place(name, list(self.rules.levels))
        if served is None:
            raise Skip(f"served place {name!r} is not loaded")
        exists = await self.session.get(InstitutionServedPlace, (institution.id, served.id))
        if exists is None:
            self.session.add(
                InstitutionServedPlace(institution_id=institution.id, place_id=served.id)
            )
            await self.session.flush()
            self.changed("add", "served place", label, served.name)

    # --- What the list no longer holds ---

    async def report_removed(self, entries: Sequence[Entry]) -> None:
        """Places this list loaded before that it no longer lists. Reported, never deleted: a
        place that left a list may have merged into another, which a reviewer decides."""
        listed = {
            (entry.code.scheme, entry.code.value)
            for entry in entries
            if isinstance(entry, PlaceEntry)
        }
        rows = await self.session.execute(
            select(Identifier, Place)
            .join(Place, Place.id == Identifier.place_id)
            .join(OfficialList, OfficialList.id == Identifier.official_list_id)
            .where(OfficialList.name.like(f"{self.list_name}/%"))
        )
        for identifier, place in rows:
            if (identifier.scheme, identifier.value) not in listed:
                self.changed(
                    "remove",
                    "place",
                    f"{place.name} ({place.administrative_level})",
                    f"{identifier.scheme} {identifier.value} is no longer listed; kept",
                )
