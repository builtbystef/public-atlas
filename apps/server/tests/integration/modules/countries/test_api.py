"""The countries API edits the five tables with every array validated against the type tables,
and refuses to delete what is in use."""

from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.modules.countries import service
from public_atlas.modules.countries.seeds import canada, shared
from public_atlas.modules.graph.models import Place

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database


async def seed(db: Database) -> None:
    async with db.session() as session:
        await service.seed(session, canada.SEED)
        await session.commit()


async def ontario_level(db: Database) -> str:
    async with db.session() as session:
        return (
            await session.execute(select(Place.administrative_level).where(Place.name == "Ontario"))
        ).scalar_one()


async def level_types(db: Database, name: str) -> list[str]:
    async with db.session() as session:
        country = await service.read_country(session, "CA")
    return next(
        level for level in country.administrative_levels if level.name == name
    ).expected_institution_types


def test_reading_a_country(client: TestClient, db: Database):
    db.run(seed, db)

    countries = client.get("/countries").json()
    assert [country["country_code"] for country in countries] == ["CA"]
    assert countries[0]["naming_rules"]["connectors"][0] == "of the"

    country = client.get("/countries/CA").json()
    assert country["settings"]["name"] == "Canada"
    assert [level["name"] for level in country["administrative_levels"]] == [
        "country",
        "province_territory",
        "region",
        "municipality",
    ]
    assert len(country["institution_types"]) == len(canada.INSTITUTION_TYPES)
    assert client.get("/countries/XX").status_code == 404

    types = client.get("/institution-types").json()
    assert {row["name"] for row in types} == {row["name"] for row in shared.INSTITUTION_TYPES}
    sources = client.get("/source-types").json()
    assert {row["name"] for row in sources} == {row["name"] for row in shared.SOURCE_TYPES}


def test_country_settings_are_created_and_edited(client: TestClient, db: Database):
    db.run(seed, db)
    body = {"country_code": "US", "name": "United States", "naming_rules": {"connectors": ["of"]}}
    assert client.put("/countries/US", json=body).status_code == 200
    assert client.get("/countries/US").json()["settings"]["name"] == "United States"

    body["name"] = "USA"
    assert client.put("/countries/US", json=body).json()["name"] == "USA"
    # The body's code must be the path's.
    assert client.put("/countries/CA", json=body).status_code == 422
    # Shapes are validated: a naming rule the schema lacks.
    body["naming_rules"] = {"nope": []}
    assert client.put("/countries/US", json=body).status_code == 422


def test_a_level_takes_only_types_the_country_uses(client: TestClient, db: Database):
    db.run(seed, db)
    level = {
        "name": "county",
        "rank": 3,
        "government_institution_type": "regional_government",
        "expected_institution_types": ["library", "zoo"],
    }
    response = client.put("/countries/CA/administrative-levels/county", json=level)
    assert response.status_code == 422
    assert "zoo" in response.json()["detail"]

    level["expected_institution_types"] = ["library"]
    assert client.put("/countries/CA/administrative-levels/county", json=level).status_code == 200
    assert db.run(level_types, db, "county") == ["library"]
    # The path must name an existing level, or the body must name the path.
    level["name"] = "parish"
    assert client.put("/countries/CA/administrative-levels/nope", json=level).status_code == 404
    assert client.delete("/countries/CA/administrative-levels/county").status_code == 204
    assert client.delete("/countries/CA/administrative-levels/county").status_code == 404


def test_renaming_a_level_moves_its_places(client: TestClient, db: Database):
    db.run(seed, db)
    level = next(
        level for level in canada.ADMINISTRATIVE_LEVELS if level["name"] == "province_territory"
    )
    response = client.put(
        "/countries/CA/administrative-levels/province_territory", json={**level, "name": "province"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "province"
    assert db.run(ontario_level, db) == "province"
    # A level with places cannot be deleted.
    assert client.delete("/countries/CA/administrative-levels/province").status_code == 409
    # Nor renamed over another.
    response = client.put(
        "/countries/CA/administrative-levels/province", json={**level, "name": "region"}
    )
    assert response.status_code == 409


def test_renaming_an_institution_type_rewrites_the_checklists(client: TestClient, db: Database):
    db.run(seed, db)
    assert "library" in db.run(level_types, db, "municipality")
    response = client.put(
        "/institution-types/library",
        json={"name": "public_library", "description": "A public library"},
    )
    assert response.status_code == 200
    names = {row["name"] for row in client.get("/institution-types").json()}
    assert "public_library" in names
    assert "library" not in names
    types = db.run(level_types, db, "municipality")
    assert "public_library" in types
    assert "library" not in types
    country = client.get("/countries/CA").json()
    assert "public_library" in {row["institution_type"] for row in country["institution_types"]}
    # Renaming over an existing type is refused.
    response = client.put(
        "/institution-types/public_library", json={"name": "hospital", "description": "x"}
    )
    assert response.status_code == 409


def test_a_type_in_use_cannot_be_deleted(client: TestClient, db: Database):
    db.run(seed, db)
    # Expected at a level.
    assert client.delete("/institution-types/library").status_code == 409
    # Expected by a country's type row.
    assert client.delete("/source-types/procurement").status_code == 409
    assert client.delete("/countries/CA/institution-types/municipal_government").status_code == 409

    # A new type nothing refers to can go.
    assert (
        client.put(
            "/institution-types/zoo", json={"name": "zoo", "description": "A zoo"}
        ).status_code
        == 200
    )
    assert client.delete("/institution-types/zoo").status_code == 204
    assert client.delete("/institution-types/zoo").status_code == 404
    assert (
        client.put(
            "/institution-types/nope", json={"name": "other", "description": "x"}
        ).status_code
        == 404
    )


def test_a_countrys_use_of_a_type_is_validated(client: TestClient, db: Database):
    db.run(seed, db)
    row = {"institution_type": "zoo", "expected_source_types": ["budget"], "name_pattern": None}
    assert client.put("/countries/CA/institution-types/zoo", json=row).status_code == 422
    assert (
        client.put(
            "/institution-types/zoo", json={"name": "zoo", "description": "A zoo"}
        ).status_code
        == 200
    )
    row["expected_source_types"] = ["gossip"]
    response = client.put("/countries/CA/institution-types/zoo", json=row)
    assert response.status_code == 422
    assert "gossip" in response.json()["detail"]
    row["expected_source_types"] = ["budget", "tender"]
    row["name_pattern"] = "("
    assert client.put("/countries/CA/institution-types/zoo", json=row).status_code == 422
    row["name_pattern"] = "^Zoo"
    assert client.put("/countries/CA/institution-types/zoo", json=row).status_code == 200
    # The body must name the path's type.
    assert client.put("/countries/CA/institution-types/hospital", json=row).status_code == 422
    country = client.get("/countries/CA").json()
    zoo = next(r for r in country["institution_types"] if r["institution_type"] == "zoo")
    assert zoo == row
    assert client.delete("/countries/CA/institution-types/zoo").status_code == 204
    assert client.delete("/institution-types/zoo").status_code == 204


def test_renaming_a_source_type_rewrites_the_expected_sources(client: TestClient, db: Database):
    db.run(seed, db)
    response = client.put(
        "/source-types/tender", json={"name": "open_tender", "description": "Open calls"}
    )
    assert response.status_code == 200
    country = client.get("/countries/CA").json()
    hospital = next(r for r in country["institution_types"] if r["institution_type"] == "hospital")
    assert "open_tender" in hospital["expected_source_types"]
    assert "tender" not in hospital["expected_source_types"]
    assert (
        client.put("/source-types/nope", json={"name": "budget", "description": "x"}).status_code
        == 404
    )


def test_default_sources_are_the_shared_seeds(client: TestClient, db: Database):
    db.run(seed, db)
    defaults = client.get("/default-expected-source-types").json()
    assert defaults["hospital"] == shared.DEFAULT_EXPECTED_SOURCE_TYPES["hospital"]
    # A source deleted from the tables is left out of the defaults. The country stops
    # expecting it first, or the delete is refused.
    for row in client.get("/countries/CA").json()["institution_types"]:
        kept = [source for source in row["expected_source_types"] if source != "news"]
        path = f"/countries/CA/institution-types/{row['institution_type']}"
        assert client.put(path, json={**row, "expected_source_types": kept}).status_code == 200
    assert client.delete("/source-types/news").status_code == 204
    defaults = client.get("/default-expected-source-types").json()
    assert all("news" not in sources for sources in defaults.values())


def test_naming_rules_are_previewed_unsaved(client: TestClient):
    rules = canada.SETTINGS["naming_rules"]
    names = ["The Corporation of the Township of Elmwood", "Elmwood, Township of", "Ville de Laval"]
    response = client.post("/naming-rules/preview", json={"naming_rules": rules, "names": names})
    assert response.status_code == 200
    township = next(i for i, group in enumerate(rules["designators"]) if group[0] == "Township")
    first, second, third = response.json()
    assert first["core"] == second["core"] == "elmwood"
    assert first["designator_groups"] == second["designator_groups"] == [township]
    assert "elmwood" in first["forms"]
    # "Ville" is a city and a town.
    assert len(third["designator_groups"]) == 2
    # Rules the form has not saved are read as given.
    response = client.post(
        "/naming-rules/preview",
        json={"naming_rules": {"designators": [["Hamlet"]], "connectors": ["of"]}, "names": names},
    )
    assert [row["designator_groups"] for row in response.json()] == [[], [], []]
    assert (
        client.post("/naming-rules/preview", json={"naming_rules": {}, "names": []}).status_code
        == 422
    )


def test_a_name_pattern_is_tried_on_the_countrys_institutions(client: TestClient, db: Database):
    db.run(seed, db)
    url = "/countries/CA/institution-types/provincial_government/name-pattern-check"

    # Searched case-insensitively, as the rules apply it. The thirteen provincial and
    # territorial governments the seed anchors; Quebec's is named in French.
    check = client.post(url, json={"name_pattern": "^government of"}).json()
    assert (check["error"], check["total"], check["matching"]) == (None, 13, 12)
    assert [miss["name"] for miss in check["misses"]] == ["Gouvernement du Québec"]

    check = client.post(url, json={"name_pattern": "^Ministry of"}).json()
    assert (check["total"], check["matching"]) == (13, 0)
    assert "Government of Ontario" in [miss["name"] for miss in check["misses"]]

    check = client.post(url, json={"name_pattern": "("}).json()
    assert check["error"].startswith("not a regular expression")

    # A type no institution has yet is an empty answer, not an error.
    zoo = client.post(
        "/countries/CA/institution-types/hospital/name-pattern-check", json={"name_pattern": "x"}
    ).json()
    assert (zoo["total"], zoo["error"]) == (0, None)
    assert client.post(url.replace("/CA/", "/XX/"), json={"name_pattern": "x"}).status_code == 404
