import { expect, test } from "vite-plus/test";

import { assignmentFilters, parseAssignmentSearch } from "./schemas";

const RUN = "9a1b0c6e-2a3f-4c7d-8e9f-0a1b2c3d4e5f";
const OTHER_RUN = "0199e8b0-0000-7000-8000-000000000002";

test("the list asks for the newest first, whatever the URL says about order", () => {
  expect(assignmentFilters(parseAssignmentSearch({ sort: "created_at", order: "asc" }))).toEqual({
    order: "desc",
    limit: 50,
    offset: 0,
  });
});

test("a page's fixed filters beat the URL's", () => {
  const search = parseAssignmentSearch({
    run_id: RUN,
    status: "running",
    result: "nope",
    type: "find_sources",
    page: "2",
  });
  expect(assignmentFilters(search, { run_id: OTHER_RUN })).toEqual({
    run_id: OTHER_RUN,
    status: "running",
    type: "find_sources",
    order: "desc",
    limit: 50,
    offset: 50,
  });
  // A fixed filter left undefined does not erase the URL's.
  expect(assignmentFilters(search, { subject_id: undefined })).toMatchObject({ run_id: RUN });
});
