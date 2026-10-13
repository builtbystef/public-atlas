/**
 * The share of a budget used, from 0 to 1: capped so a bar never overflows, and 0 for a budget of
 * nothing rather than a division by zero.
 */
export function budgetRatio(used: number, budget: number): number {
  return budget > 0 ? Math.min(used / budget, 1) : 0;
}
