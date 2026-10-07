import type {
  ApiClient,
  AssignmentResult,
  AssignmentStatus,
  AssignmentType,
} from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";
import { queryParams, type ListPage, type SortOrder } from "@/lib/lists";

export interface AssignmentListFilters extends ListPage {
  run_id?: string | undefined;
  status?: AssignmentStatus | undefined;
  result?: AssignmentResult | undefined;
  type?: AssignmentType | undefined;
  subject_id?: string | undefined;
  order?: SortOrder | undefined;
}

export const assignmentKeys = {
  all: ["assignments"] as const,
  list: (filters: AssignmentListFilters) => [...assignmentKeys.all, "list", filters] as const,
  detail: (id: string) => [...assignmentKeys.all, "detail", id] as const,
  events: (id: string) => [...assignmentKeys.all, "events", id] as const,
  findings: (id: string) => [...assignmentKeys.all, "findings", id] as const,
};

export function assignmentListQuery(api: ApiClient, filters: AssignmentListFilters) {
  return queryOptions({
    queryKey: assignmentKeys.list(filters),
    queryFn: async () =>
      unwrap(await api.GET("/assignments", { params: { query: queryParams(filters) } })),
  });
}

export function assignmentQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: assignmentKeys.detail(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/assignments/{assignment_id}", {
          params: { path: { assignment_id: id } },
        }),
      ),
  });
}

/** Everything the agent saw, said and did, in order, with a presigned URL per recorded video. */
export function assignmentEventsQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: assignmentKeys.events(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/assignments/{assignment_id}/events", {
          params: { path: { assignment_id: id } },
        }),
      ),
  });
}

export function assignmentFindingsQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: assignmentKeys.findings(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/assignments/{assignment_id}/findings", {
          params: { path: { assignment_id: id } },
        }),
      ),
  });
}
