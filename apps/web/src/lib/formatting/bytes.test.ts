import { expect, test } from "vite-plus/test";

import { formatBytes } from "./bytes";

test("formats byte counts with the largest fitting unit", () => {
  expect(formatBytes(0)).toBe("0 B");
  expect(formatBytes(12)).toBe("12 B");
  expect(formatBytes(1024)).toBe("1 KB");
  expect(formatBytes(3481)).toBe("3.4 KB");
  expect(formatBytes(25 * 1024 * 1024)).toBe("25 MB");
  expect(formatBytes(1.55 * 1024 ** 3)).toBe("1.6 GB");
});

test("negative counts read as nothing and huge ones stay in gigabytes", () => {
  expect(formatBytes(-5)).toBe("0 B");
  expect(formatBytes(1023)).toBe("1023 B");
  expect(formatBytes(1024 ** 4)).toBe("1024 GB");
  expect(formatBytes(1.04 * 1024)).toBe("1 KB");
});
