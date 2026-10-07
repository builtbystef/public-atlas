import { expect, test } from "vite-plus/test";

import { titleFor } from "./page-titles";

test("the shell header names the section of the URL", () => {
  expect(titleFor("/")).toBe("Overview");
  expect(titleFor("/runs")).toBe("Runs");
  expect(titleFor("/runs/new")).toBe("New run");
  expect(titleFor("/runs/abc")).toBe("Run");
  expect(titleFor("/review")).toBe("Review queue");
  expect(titleFor("/review/abc")).toBe("Review item");
  expect(titleFor("/countries/CA")).toBe("Country");
  expect(titleFor("/elsewhere")).toBeNull();
});
