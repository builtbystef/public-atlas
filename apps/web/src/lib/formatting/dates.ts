/**
 * Conversions between the API's ISO 8601 instants and the wall-clock strings
 * that <input type="datetime-local"> uses ("2026-09-07T14:30"), in a given
 * IANA zone. The zone is passed explicitly instead of taken from the runtime
 * so a Client Component renders the same text on the server and in the browser.
 */

const WALL_CLOCK = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

function partsIn(instant: Date, timeZone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(instant);
  const result: Record<string, number> = {};
  for (const { type, value } of parts) {
    if (type !== "literal") result[type] = Number(value);
  }
  return result;
}

/** What the zone's clock reads at `instant`, as if it were UTC. */
function wallClockAsUtc(instant: Date, timeZone: string): number {
  const p = partsIn(instant, timeZone);
  return Date.UTC(p["year"]!, p["month"]! - 1, p["day"]!, p["hour"]!, p["minute"]!, p["second"]!);
}

/** The ISO instant for a datetime-local value read as wall-clock time in `timeZone`. */
export function wallClockToIso(value: string, timeZone: string): string | null {
  const match = WALL_CLOCK.exec(value);
  if (!match) return null;
  const [, year, month, day, hour, minute, second = "0"] = match;
  const asUtc = Date.UTC(+year!, +month! - 1, +day!, +hour!, +minute!, +second);
  // Subtract the zone's offset at this moment; a second pass settles DST edges.
  let instant = asUtc;
  for (let pass = 0; pass < 2; pass++) {
    const offset = wallClockAsUtc(new Date(instant), timeZone) - instant;
    instant = asUtc - offset;
  }
  return new Date(instant).toISOString();
}

export function isoToWallClock(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "";
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return "";
  const p = partsIn(instant, timeZone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p["year"]}-${pad(p["month"]!)}-${pad(p["day"]!)}T${pad(p["hour"]!)}:${pad(p["minute"]!)}`;
}

export function formatDate(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", { timeZone, dateStyle: "medium" }).format(new Date(iso));
}

export function formatDateTime(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

/** "today", "yesterday", "in 3 days": whole calendar days apart in `timeZone`. */
export function formatRelativeDays(
  iso: string | null | undefined,
  timeZone: string,
  now: number = Date.now(),
): string {
  if (!iso) return "";
  const target = wallClockAsUtc(new Date(iso), timeZone);
  const today = wallClockAsUtc(new Date(now), timeZone);
  const days = Math.round(
    (Date.UTC(1970, 0, 1 + Math.floor(target / 86_400_000)) -
      Date.UTC(1970, 0, 1 + Math.floor(today / 86_400_000))) /
      86_400_000,
  );
  return new Intl.RelativeTimeFormat("en-US", { numeric: "auto" }).format(days, "day");
}

export function isBeforeToday(iso: string | null | undefined, timeZone: string, now = Date.now()) {
  if (!iso) return false;
  const target = wallClockAsUtc(new Date(iso), timeZone);
  const today = wallClockAsUtc(new Date(now), timeZone);
  return Math.floor(target / 86_400_000) < Math.floor(today / 86_400_000);
}
