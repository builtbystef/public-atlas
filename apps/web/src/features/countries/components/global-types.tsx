"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { SettingsSection, SettingsSections } from "@/components/shared/layout/settings-section";
import { browserApi } from "@/lib/api/client";

import {
  deleteInstitutionType,
  deleteSourceType,
  putInstitutionType,
  putSourceType,
} from "../mutations";
import { institutionTypesQuery, sourceTypesQuery } from "../queries";
import { TypeTable } from "./type-table";

/** The two type tables every country draws from. */
export function GlobalTypes() {
  const { data: institutionTypes } = useSuspenseQuery(institutionTypesQuery(browserApi));
  const { data: sourceTypes } = useSuspenseQuery(sourceTypesQuery(browserApi));
  return (
    <SettingsSections>
      <SettingsSection
        wide
        title="Institution types"
        description="The kinds of public body. A country says which it uses and what each is called there."
      >
        <TypeTable
          noun="institution type"
          rows={institutionTypes}
          put={putInstitutionType}
          remove={deleteInstitutionType}
        />
      </SettingsSection>
      <SettingsSection
        wide
        title="Source types"
        description="The kinds of signal page find_sources looks for: tenders, budgets, minutes, and so on."
      >
        <TypeTable
          noun="source type"
          rows={sourceTypes}
          put={putSourceType}
          remove={deleteSourceType}
        />
      </SettingsSection>
    </SettingsSections>
  );
}
