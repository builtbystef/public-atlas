/**
 * How much of a budget is used, as a share from 0 to 1: a bar never
 * overflows, and a budget of nothing is nothing used rather than a division
 * by zero.
 */
export function budgetRatio(used: number, budget: number): number {
  return budget > 0 ? Math.min(used / budget, 1) : 0;
}
