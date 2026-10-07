import type {
  AdministrativeLevelInput,
  CountryInstitutionTypeInput,
  CountrySettingsInput,
  InstitutionTypeInput,
  SourceTypeInput,
} from "@public-atlas/api-client";

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

/** Every write is a PUT by name or a DELETE: the tables are small and the names are the keys. */

export async function putCountrySettings(
  code: string,
  body: CountrySettingsInput,
): Promise<CountrySettingsInput> {
  return unwrap(
    await browserApi.PUT("/countries/{country_code}", {
      params: { path: { country_code: code } },
      body,
    }),
  );
}

export async function putAdministrativeLevel(
  code: string,
  body: AdministrativeLevelInput,
): Promise<AdministrativeLevelInput> {
  return unwrap(
    await browserApi.PUT("/countries/{country_code}/administrative-levels/{name}", {
      params: { path: { country_code: code, name: body.name } },
      body,
    }),
  );
}

export async function deleteAdministrativeLevel(code: string, name: string): Promise<void> {
  unwrap(
    await browserApi.DELETE("/countries/{country_code}/administrative-levels/{name}", {
      params: { path: { country_code: code, name } },
    }),
  );
}

export async function putCountryInstitutionType(
  code: string,
  body: CountryInstitutionTypeInput,
): Promise<CountryInstitutionTypeInput> {
  return unwrap(
    await browserApi.PUT("/countries/{country_code}/institution-types/{institution_type}", {
      params: { path: { country_code: code, institution_type: body.institution_type } },
      body,
    }),
  );
}

export async function deleteCountryInstitutionType(code: string, type: string): Promise<void> {
  unwrap(
    await browserApi.DELETE("/countries/{country_code}/institution-types/{institution_type}", {
      params: { path: { country_code: code, institution_type: type } },
    }),
  );
}

export async function putInstitutionType(
  body: InstitutionTypeInput,
): Promise<InstitutionTypeInput> {
  return unwrap(
    await browserApi.PUT("/institution-types/{name}", {
      params: { path: { name: body.name } },
      body,
    }),
  );
}

export async function deleteInstitutionType(name: string): Promise<void> {
  unwrap(await browserApi.DELETE("/institution-types/{name}", { params: { path: { name } } }));
}

export async function putSourceType(body: SourceTypeInput): Promise<SourceTypeInput> {
  return unwrap(
    await browserApi.PUT("/source-types/{name}", { params: { path: { name: body.name } }, body }),
  );
}

export async function deleteSourceType(name: string): Promise<void> {
  unwrap(await browserApi.DELETE("/source-types/{name}", { params: { path: { name } } }));
}
