import { expect, test } from "vite-plus/test";

import { formatCompact, formatCost, formatCount, formatPercent } from "./money";

test("costs are dollars, with four decimals under a dollar", () => {
  expect(formatCost("0")).toBe("$0.00");
  expect(formatCost("0.0123")).toBe("$0.0123");
  expect(formatCost("12.5")).toBe("$12.50");
  expect(formatCost(3)).toBe("$3.00");
  expect(formatCost(null)).toBe("");
  expect(formatCost("n/a")).toBe("n/a");
});

test("counts and ratios", () => {
  expect(formatCount(12345)).toBe("12,345");
  expect(formatPercent(0.815)).toBe("82%");
  expect(formatPercent(null)).toBe("");
});

test("compact counts for budget figures", () => {
  expect(formatCompact(74)).toBe("74");
  expect(formatCompact(12_500)).toBe("12.5K");
  expect(formatCompact(4_576_247)).toBe("4.6M");
  expect(formatCompact(10_000_000)).toBe("10M");
});
