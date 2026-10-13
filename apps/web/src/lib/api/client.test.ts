// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vite-plus/test";

import { browserApi } from "./client";

afterEach(() => {
  document.cookie = "db=; max-age=0";
});

/** The request the client would send, caught before it leaves. */
async function sent(cookie: string): Promise<Request> {
  document.cookie = cookie;
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({ status: "ok" }));
  // The browser resolves the client's `/api` against the page; a test has no page.
  await browserApi.GET("/health", { baseUrl: "http://console.test/api", fetch });
  return fetch.mock.calls[0]![0] as Request;
}

test("the browser client sends the database the cookie chooses", async () => {
  const request = await sent("db=eval");
  expect(request.url).toBe("http://console.test/api/health");
  expect(request.headers.get("x-database")).toBe("eval");
});

test("without a cookie, or with one naming nothing, the live database is sent", async () => {
  expect((await sent("db=; max-age=0")).headers.get("x-database")).toBe("main");
  expect((await sent("db=staging")).headers.get("x-database")).toBe("main");
});
