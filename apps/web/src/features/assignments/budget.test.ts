import { expect, test } from "vite-plus/test";

import { formatPercent } from "@/lib/formatting/money";

import { budgetRatio } from "./budget";

test("a budget of nothing reads as nothing used", () => {
  expect(budgetRatio(0, 0)).toBe(0);
  expect(budgetRatio(12, 0)).toBe(0);
  expect(formatPercent(budgetRatio(12, 0))).toBe("0%");
});

test("use past the budget fills the bar and no further", () => {
  expect(budgetRatio(40, 50)).toBe(0.8);
  expect(budgetRatio(50, 50)).toBe(1);
  expect(budgetRatio(75, 50)).toBe(1);
  expect(formatPercent(budgetRatio(75, 50))).toBe("100%");
});
