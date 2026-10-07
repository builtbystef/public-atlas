import { expect, test } from "vite-plus/test";

import { humanize, labelOf, reviewRuleLabels } from "./labels";

test("type names read as words", () => {
  expect(humanize("school_board")).toBe("School board");
  expect(humanize("agency")).toBe("Agency");
});

test("an unknown value still gets a label", () => {
  expect(labelOf(reviewRuleLabels, "duplicate")).toBe("Possible duplicate");
  expect(labelOf(reviewRuleLabels, "something_new")).toBe("Something new");
});
