/**
 * The API sends money as a decimal string (`"0.0123"`), never a float. Shown
 * in dollars with four decimals under a dollar, since an assignment's cost
 * is cents, and two above.
 */
export function formatCost(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return String(value);
  const small = amount !== 0 && Math.abs(amount) < 1;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: small ? 4 : 2,
  }).format(amount);
}

/** "1,234" and "12.5k" style counts for tokens and requests. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/** "81%" for a 0..1 ratio; "" for none. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `${Math.round(value * 100)}%`;
}
