import { afterEach, expect, test, vi } from "vite-plus/test";

import { assertApiUrl, createApi, getApiUrl } from "./server-client";

afterEach(() => {
  vi.unstubAllEnvs();
});

test("defaults to the local FastAPI dev server", () => {
  vi.stubEnv("API_URL", undefined);
  expect(getApiUrl()).toBe("http://127.0.0.1:8000");
});

test("a production server refuses to start without API_URL", () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_URL", undefined);
  expect(() => assertApiUrl()).toThrow("API_URL is not set");
  vi.stubEnv("API_URL", "https://api.example.test");
  expect(() => assertApiUrl()).not.toThrow();
});

test("development runs without API_URL", () => {
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("API_URL", undefined);
  expect(() => assertApiUrl()).not.toThrow();
});

test("API_URL overrides the base URL for every request", async () => {
  vi.stubEnv("API_URL", "https://api.example.test");
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({ status: "ok" }));

  const { data } = await createApi(fetch).GET("/health");

  expect(data).toEqual({ status: "ok" });
  const request = fetch.mock.calls[0]?.[0] as Request | undefined;
  expect(request?.url).toBe("https://api.example.test/health");
  expect(request?.headers.get("x-database")).toBe("main");
});

test("the chosen database goes in the X-Database header", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({ status: "ok" }));

  await createApi(fetch, "eval").GET("/health/db");

  const request = fetch.mock.calls[0]?.[0] as Request | undefined;
  expect(request?.headers.get("x-database")).toBe("eval");
});
