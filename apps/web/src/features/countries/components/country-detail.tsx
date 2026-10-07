"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/shared/layout/page-header";
import { SettingsSection, SettingsSections } from "@/components/shared/layout/settings-section";
import { browserApi } from "@/lib/api/client";

import { countryQuery, institutionTypesQuery, sourceTypesQuery } from "../queries";
import { CountrySettingsForm } from "./country-settings-form";
import { CountryTypesTable } from "./country-types-table";
import { LevelsTable } from "./levels-table";

export function CountryDetail({ code }: { code: string }) {
  const { data: country } = useSuspenseQuery(countryQuery(browserApi, code));
  const { data: institutionTypes } = useSuspenseQuery(institutionTypesQuery(browserApi));
  const { data: sourceTypes } = useSuspenseQuery(sourceTypesQuery(browserApi));
  return (
    <>
      <PageHeader
        title={country.settings.name}
        description={`${country.settings.country_code} · every edit takes effect on the next assignment.`}
      />
      <SettingsSections>
        <SettingsSection
          title="Settings"
          description="The name, and the naming rules that tell one place from another."
        >
          <CountrySettingsForm key={country.settings.country_code} settings={country.settings} />
        </SettingsSection>
        <SettingsSection
          wide
          title="Administrative levels"
          description="The hierarchy of places, with the government's type and the bodies expected at each level."
        >
          <LevelsTable
            countryCode={code}
            levels={country.administrative_levels}
            institutionTypes={institutionTypes}
          />
        </SettingsSection>
        <SettingsSection
          wide
          title="Institution types in this country"
          description="Which types the country uses, the sources expected on each, and the name pattern a body should match."
        >
          <CountryTypesTable
            countryCode={code}
            rows={country.institution_types}
            institutionTypes={institutionTypes}
            sourceTypes={sourceTypes}
          />
        </SettingsSection>
      </SettingsSections>
    </>
  );
}
