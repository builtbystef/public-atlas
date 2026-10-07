import { expect, test } from "vite-plus/test";

import { parseAssignmentSearch } from "./schemas";

test("the assignments list reads its filters from the URL", () => {
  expect(
    parseAssignmentSearch({
      run_id: "9a1b0c6e-2a3f-4c7d-8e9f-0a1b2c3d4e5f",
      status: "running",
      result: "nope",
      type: "find_sources",
    }),
  ).toEqual({
    run_id: "9a1b0c6e-2a3f-4c7d-8e9f-0a1b2c3d4e5f",
    status: "running",
    type: "find_sources",
  });
});
