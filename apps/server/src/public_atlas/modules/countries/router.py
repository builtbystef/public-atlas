"""The countries API (spec section 11, page 5): the five country tables, read and edited with
validation of every array against the type tables. A `PUT` creates or changes the row its path
names; a body naming another row renames it where the keys cascade."""

from fastapi import APIRouter, status

from public_atlas.dependencies import SessionDep
from public_atlas.modules.countries import service
from public_atlas.modules.countries.schemas import (
    AdministrativeLevelInput,
    CountryInstitutionTypeInput,
    CountryOutput,
    CountrySettingsInput,
    InstitutionTypeInput,
    SourceTypeInput,
)
from public_atlas.shared.exceptions import UnprocessableError

router = APIRouter(tags=["countries"])


@router.get("/countries")
async def list_countries(session: SessionDep) -> list[CountrySettingsInput]:
    return await service.list_countries(session)


@router.get("/countries/{country_code}")
async def read_country(country_code: str, session: SessionDep) -> CountryOutput:
    """The country's settings, its administrative levels and how it uses each type."""
    return await service.read_country(session, country_code)


@router.put("/countries/{country_code}")
async def put_country_settings(
    country_code: str, data: CountrySettingsInput, session: SessionDep
) -> CountrySettingsInput:
    """Create the country or change its name and naming rules."""
    if data.country_code != country_code:
        raise UnprocessableError("the body's country code is not the path's")
    result = await service.put_country_settings(session, data)
    await session.commit()
    return result


@router.put("/countries/{country_code}/administrative-levels/{name}")
async def put_administrative_level(
    country_code: str, name: str, data: AdministrativeLevelInput, session: SessionDep
) -> AdministrativeLevelInput:
    """Create or change a level. Its types must be ones the country uses."""
    result = await service.put_administrative_level(session, country_code, name, data)
    await session.commit()
    return result


@router.delete(
    "/countries/{country_code}/administrative-levels/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_administrative_level(country_code: str, name: str, session: SessionDep) -> None:
    """Refused while a place sits at the level."""
    await service.delete_administrative_level(session, country_code, name)
    await session.commit()


@router.put("/countries/{country_code}/institution-types/{institution_type}")
async def put_country_institution_type(
    country_code: str,
    institution_type: str,
    data: CountryInstitutionTypeInput,
    session: SessionDep,
) -> CountryInstitutionTypeInput:
    """How the country uses a type: the sources expected for it and what its names look like."""
    if data.institution_type != institution_type:
        raise UnprocessableError("the body's institution type is not the path's")
    result = await service.put_country_institution_type(session, country_code, data)
    await session.commit()
    return result


@router.delete(
    "/countries/{country_code}/institution-types/{institution_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_country_institution_type(
    country_code: str, institution_type: str, session: SessionDep
) -> None:
    """Refused while one of the country's levels expects the type."""
    await service.delete_country_institution_type(session, country_code, institution_type)
    await session.commit()


@router.get("/institution-types")
async def list_institution_types(session: SessionDep) -> list[InstitutionTypeInput]:
    """Global: one `hospital` for every country."""
    return await service.list_institution_types(session)


@router.put("/institution-types/{name}")
async def put_institution_type(
    name: str, data: InstitutionTypeInput, session: SessionDep
) -> InstitutionTypeInput:
    """Create or change a type; a body with another name renames it everywhere."""
    result = await service.put_institution_type(session, name, data)
    await session.commit()
    return result


@router.delete("/institution-types/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_institution_type(name: str, session: SessionDep) -> None:
    """Refused while anything refers to the type."""
    await service.delete_institution_type(session, name)
    await session.commit()


@router.get("/source-types")
async def list_source_types(session: SessionDep) -> list[SourceTypeInput]:
    return await service.list_source_types(session)


@router.put("/source-types/{name}")
async def put_source_type(name: str, data: SourceTypeInput, session: SessionDep) -> SourceTypeInput:
    """Create or change a source type; a body with another name renames it everywhere."""
    result = await service.put_source_type(session, name, data)
    await session.commit()
    return result


@router.delete("/source-types/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_type(name: str, session: SessionDep) -> None:
    """Refused while anything refers to the type."""
    await service.delete_source_type(session, name)
    await session.commit()
