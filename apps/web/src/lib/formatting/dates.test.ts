import { expect, test } from "vite-plus/test";

import {
  formatDate,
  formatDateTime,
  formatRelativeDays,
  isBeforeToday,
  isoToWallClock,
  wallClockToIso,
} from "./dates";

test("wall-clock time in a zone round-trips through an ISO instant", () => {
  expect(wallClockToIso("2026-09-07T14:30", "Europe/Belgrade")).toBe("2026-09-07T12:30:00.000Z");
  expect(wallClockToIso("2026-01-07T14:30", "Europe/Belgrade")).toBe("2026-01-07T13:30:00.000Z");
  expect(wallClockToIso("2026-09-07T14:30", "UTC")).toBe("2026-09-07T14:30:00.000Z");
  expect(isoToWallClock("2026-09-07T12:30:00Z", "Europe/Belgrade")).toBe("2026-09-07T14:30");
  expect(isoToWallClock(null, "UTC")).toBe("");
});

test("rejects values that are not a datetime-local string", () => {
  expect(wallClockToIso("tomorrow", "UTC")).toBeNull();
  expect(wallClockToIso("2026-09-07", "UTC")).toBeNull();
});

test("relative days follow the zone's calendar, not UTC's", () => {
  const now = Date.parse("2026-09-07T23:30:00Z"); // 01:30 on the 8th in Belgrade, still the 7th in UTC
  expect(formatRelativeDays("2026-09-07T21:00:00Z", "UTC", now)).toBe("today");
  expect(formatRelativeDays("2026-09-07T21:00:00Z", "Europe/Belgrade", now)).toBe("yesterday");
  expect(formatRelativeDays("2026-09-10T08:00:00Z", "UTC", now)).toBe("in 3 days");
  expect(isBeforeToday("2026-09-07T21:00:00Z", "Europe/Belgrade", now)).toBe(true);
  expect(isBeforeToday("2026-09-07T21:00:00Z", "UTC", now)).toBe(false);
});

test("wall-clock values with seconds, and invalid instants", () => {
  expect(wallClockToIso("2026-09-07T14:30:15", "UTC")).toBe("2026-09-07T14:30:15.000Z");
  expect(isoToWallClock("not a date", "UTC")).toBe("");
  expect(isoToWallClock(undefined, "UTC")).toBe("");
});

test("daylight-saving edges settle on a real instant", () => {
  // 02:30 does not exist on 2026-03-29 in Belgrade (clocks jump 02:00 -> 03:00).
  const skipped = wallClockToIso("2026-03-29T02:30", "Europe/Belgrade");
  expect(["2026-03-29T00:30:00.000Z", "2026-03-29T01:30:00.000Z"]).toContain(skipped);
  // 02:30 happens twice on 2026-10-25; either reading is that wall-clock time.
  const repeated = wallClockToIso("2026-10-25T02:30", "Europe/Belgrade");
  expect(["2026-10-25T00:30:00.000Z", "2026-10-25T01:30:00.000Z"]).toContain(repeated);
  expect(isoToWallClock(repeated, "Europe/Belgrade")).toBe("2026-10-25T02:30");
  expect(
    isoToWallClock(wallClockToIso("2026-03-29T05:00", "Europe/Belgrade"), "Europe/Belgrade"),
  ).toBe("2026-03-29T05:00");
});

test("dates and times are formatted in the given zone", () => {
  expect(formatDate("2026-09-07T23:30:00Z", "UTC")).toBe("Sep 7, 2026");
  expect(formatDate("2026-09-07T23:30:00Z", "Europe/Belgrade")).toBe("Sep 8, 2026");
  expect(formatDateTime("2026-09-07T23:30:00Z", "Europe/Belgrade")).toBe("Sep 8, 2026, 1:30 AM");
  expect(formatDate(null, "UTC")).toBe("");
  expect(formatDateTime("", "UTC")).toBe("");
});

test("relative days count whole days either way", () => {
  const now = Date.parse("2026-09-07T12:00:00Z");
  expect(formatRelativeDays("2026-09-06T23:59:00Z", "UTC", now)).toBe("yesterday");
  expect(formatRelativeDays("2026-09-08T00:01:00Z", "UTC", now)).toBe("tomorrow");
  expect(formatRelativeDays("2026-08-28T00:01:00Z", "UTC", now)).toBe("10 days ago");
  expect(formatRelativeDays(null, "UTC", now)).toBe("");
  expect(isBeforeToday(null, "UTC", now)).toBe(false);
  expect(isBeforeToday("2026-09-07T00:00:00Z", "UTC", now)).toBe(false);
});
