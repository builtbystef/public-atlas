"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { SectionSidebar } from "@/components/shared/layout/section-sidebar";
import { SettingsSection } from "@/components/shared/layout/settings-section";
import { browserApi } from "@/lib/api/client";
import { paths } from "@/lib/routes";

import {
  countryQuery,
  defaultSourcesQuery,
  institutionTypesQuery,
  sourceTypesQuery,
} from "../queries";
import { CountryNameTitle, NamingRulesForm } from "./country-settings-form";
import { CountryTypesTable } from "./country-types-table";
import { LevelsTable } from "./levels-table";

/** The country's header and the list of its pages, around the page being shown. */
export function CountryShell({
  code,
  flag,
  children,
}: {
  code: string;
  flag: ReactNode;
  children: ReactNode;
}) {
  const { data: country } = useSuspenseQuery(countryQuery(browserApi, code));
  const pages = [
    { href: paths.country(code), label: "Naming rules" },
    {
      href: paths.countryLevels(code),
      label: "Levels",
      count: country.administrative_levels.length,
    },
    {
      href: paths.countryInstitutionTypes(code),
      label: "Institution types",
      count: country.institution_types.length,
    },
  ];
  return (
    <>
      <PageHeader
        title={
          <CountryNameTitle
            key={country.settings.country_code}
            settings={country.settings}
            flag={flag}
          />
        }
      />
      <SectionSidebar pages={pages}>{children}</SectionSidebar>
    </>
  );
}

/** The country the page is under, as the shell's layout read it. */
function useCountry() {
  const { code } = useParams<{ code: string }>();
  const { data: country } = useSuspenseQuery(countryQuery(browserApi, code));
  return { code, country };
}

export function CountryNamingRulesPage() {
  const { country } = useCountry();
  return (
    <SettingsSection wide title="Naming rules">
      <div className="max-w-2xl">
        <NamingRulesForm key={country.settings.country_code} settings={country.settings} />
      </div>
    </SettingsSection>
  );
}

export function CountryLevelsPage() {
  const { code, country } = useCountry();
  const { data: institutionTypes } = useSuspenseQuery(institutionTypesQuery(browserApi));
  return (
    <SettingsSection wide title="Administrative levels">
      <LevelsTable
        countryCode={code}
        countryName={country.settings.name}
        levels={country.administrative_levels}
        institutionTypes={institutionTypes}
        countryTypes={country.institution_types.map((row) => row.institution_type)}
      />
    </SettingsSection>
  );
}

export function CountryInstitutionTypesPage() {
  const { code, country } = useCountry();
  const { data: institutionTypes } = useSuspenseQuery(institutionTypesQuery(browserApi));
  const { data: sourceTypes } = useSuspenseQuery(sourceTypesQuery(browserApi));
  const { data: defaultSources } = useSuspenseQuery(defaultSourcesQuery(browserApi));
  return (
    <SettingsSection wide title="Institution types in this country">
      <CountryTypesTable
        countryCode={code}
        countryName={country.settings.name}
        rows={country.institution_types}
        institutionTypes={institutionTypes}
        sourceTypes={sourceTypes}
        defaultSources={defaultSources}
      />
    </SettingsSection>
  );
}
