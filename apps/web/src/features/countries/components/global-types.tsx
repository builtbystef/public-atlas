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
      <SettingsSection wide title="Institution types">
        <TypeTable
          noun="institution type"
          rows={institutionTypes}
          put={putInstitutionType}
          remove={deleteInstitutionType}
        />
      </SettingsSection>
      <SettingsSection wide title="Source types">
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
