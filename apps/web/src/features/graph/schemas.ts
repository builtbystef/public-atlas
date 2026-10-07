import { z } from "zod";

import { entityStatuses } from "@/lib/labels";
import { listSearch, optionalParam, parseSearch, type SearchParams } from "@/lib/lists";

export const institutionSorts = [
  "name",
  "institution_type",
  "status",
  "created_at",
  "place",
] as const;

export type InstitutionSort = (typeof institutionSorts)[number];

const institutionSearchSchema = z.object({
  q: optionalParam(z.string().trim().min(1)),
  country_code: optionalParam(z.string().trim().min(1)),
  place_id: optionalParam(z.uuid()),
  administrative_level: optionalParam(z.string().trim().min(1)),
  institution_type: optionalParam(z.string().trim().min(1)),
  status: optionalParam(z.enum(entityStatuses)),
  ...listSearch(institutionSorts),
});

export type InstitutionSearch = z.output<typeof institutionSearchSchema>;

export function parseInstitutionSearch(params: SearchParams | URLSearchParams): InstitutionSearch {
  return parseSearch(institutionSearchSchema, params);
}
