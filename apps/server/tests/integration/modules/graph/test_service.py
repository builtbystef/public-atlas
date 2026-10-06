"""Creating and finding places and institutions, and the duplicate search: trigram similarity,
one row per entity, at most five, and never a body of another designator."""

from typing import TYPE_CHECKING

from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import EnteredBy, EntityStatus, Institution, Place

if TYPE_CHECKING:
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, World

AGENT = EnteredBy.AGENT


def test_creating_defaults_the_parent_to_the_governments_and_adds_the_name_as_an_alias(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Institution, Institution, list[str], Place]:
        async with db.session() as session:
            library = await build.candidate_institution(
                session, world.oakville, "Oakville  Library"
            )
            board = await graph.create_institution(
                session,
                name="Library Board",
                institution_type="other",
                place=world.oakville,
                entered_by=AGENT,
                parent=library,
                suggested_type="library board",
                language="en",
            )
            names = [alias.text for alias in await graph.names_of(session, library)]
            place = await graph.create_place(
                session,
                name="Birch",
                country_code="CA",
                administrative_level="municipality",
                parent=world.elm,
                entered_by=AGENT,
            )
            await session.commit()
            return library, board, names, place

    library, board, names, place = db.run(scenario)
    assert library.name == "Oakville Library"
    assert library.status is EntityStatus.CANDIDATE
    assert library.parent_institution_id == world.town.id
    assert board.parent_institution_id == library.id
    assert names == ["Oakville Library"]
    assert (place.status, place.parent_place_id) == (EntityStatus.CANDIDATE, world.elm.id)


def test_finding_by_any_written_form(db: Database, world: World, build: type[Build]):
    async def scenario() -> tuple[list[str], list[str], list[str], list[str], list[str]]:
        async with db.session() as session:
            rules = world.rules
            inverted = await graph.find_places(session, "CA", "Elm, County of", rules=rules)
            at_level = await graph.find_places(
                session, "CA", "Oakville", rules=rules, levels=["municipality"]
            )
            wrong_level = await graph.find_places(
                session, "CA", "Oakville", rules=rules, levels=["region"]
            )
            under = await graph.find_places(
                session, "CA", "Oakville", rules=rules, parent=world.elm
            )
            town = await graph.find_institutions(
                session, world.oakville, "The Corporation of the Town of Oakville", rules=rules
            )
            chain = await graph.place_chain(session, world.oakville)
            return (
                [p.name for p in inverted],
                [p.name for p in at_level],
                [p.name for p in wrong_level],
                [p.name for p in under],
                [f"{i.name} / {' > '.join(p.name for p in chain)}" for i in town],
            )

    assert db.run(scenario) == (
        ["Elm"],
        ["Oakville"],
        [],
        ["Oakville"],
        ["Town of Oakville / Oakville > Elm > Ontario > Canada"],
    )


def test_the_duplicate_search(db: Database, world: World, build: type[Build]):
    async def scenario() -> dict[str, list[tuple[str, str]]]:
        async with db.session() as session:
            rules = world.rules
            opl = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library"
            )
            await graph.add_alias(
                session, opl, "OPL", language="en", entered_by=AGENT, is_acronym=True
            )
            await graph.add_alias(
                session, opl, "Oakville Public Library Board", language="en", entered_by=AGENT
            )
            # A regional body saved under the region is offered from the town's chain.
            regional = await build.candidate_institution(
                session, world.elm, "Elm Oakville Library Service"
            )
            gone = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library Inc"
            )
            await status_changes.reject_institution(session, gone, entered_by=AGENT)
            for number in range(7):
                await build.candidate_institution(session, world.oakville, f"Oak Library {number}")
            township = await build.candidate_institution(
                session, world.oakville, "Township of Oakridge Falls", "municipal_government"
            )
            city = await build.candidate_institution(
                session, world.oakville, "City of Oakridge Falls", "other"
            )
            chain = await graph.place_chain(session, world.oakville)
            await session.commit()

            def names(matches: list[graph.Match[Institution]]) -> list[tuple[str, str]]:
                return [(m.entity.name, m.alias) for m in matches]

            library = await graph.similar_institutions(
                session, chain, "Oakville Public Library", rules=rules
            )
            acronym = await graph.similar_institutions(session, chain, "OPL", rules=rules)
            many = await graph.similar_institutions(session, chain, "Oak Library", rules=rules)
            designator = await graph.similar_institutions(
                session, chain, "City of Oakridge Falls", rules=rules
            )
            plain = await graph.similar_institutions(session, chain, "Oakridge Falls", rules=rules)
            nothing = await graph.similar_institutions(
                session, chain, "Metrolinx Transit", rules=rules
            )
            assert regional.id in {m.entity.id for m in library}
            assert gone.id not in {m.entity.id for m in library}
            assert township.id not in {m.entity.id for m in designator}
            assert city.id in {m.entity.id for m in designator}
            return {
                "library": names(library)[:1],
                "acronym": names(acronym)[:1],
                "many": names(many),
                "plain": names(plain),
                "nothing": names(nothing),
            }

    out = db.run(scenario)
    # One row per entity, with its most alike alias.
    assert out["library"] == [("Oakville Public Library", "Oakville Public Library")]
    assert out["acronym"] == [("Oakville Public Library", "OPL")]
    assert len(out["many"]) == graph.MAX_MATCHES
    assert len({name for name, _ in out["many"]}) == graph.MAX_MATCHES
    # A plain name carries no designator, so both bodies of that name are offered.
    assert {"Township of Oakridge Falls", "City of Oakridge Falls"} <= {
        name for name, _ in out["plain"]
    }
    assert out["nothing"] == []
