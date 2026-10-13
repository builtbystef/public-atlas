export const TIME_ZONE_COOKIE = "tz";

/** Whether `value` is an IANA zone this runtime knows. */
export function isTimeZone(value: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value });
    return true;
  } catch {
    return false;
  }
}
