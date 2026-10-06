import { expect, test, vi } from "vite-plus/test";

import { createApiClient } from "./index";

test("GET /health/ is typed and hits the expected URL", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({ status: "ok" }));
  const api = createApiClient({ baseUrl: "http://api.test", fetch });

  const { data, error } = await api.GET("/health");

  expect(error).toBeUndefined();
  expect(data?.status).toBe("ok");
  const request = fetch.mock.calls[0]?.[0] as Request | undefined;
  expect(request?.url).toBe("http://api.test/health");
});

test("non-2xx responses land in error", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () =>
    Response.json({ detail: "nope" }, { status: 500 }),
  );
  const api = createApiClient({ baseUrl: "http://api.test", fetch });

  const { data, error, response } = await api.GET("/health/db");

  expect(data).toBeUndefined();
  expect(error).toEqual({ detail: "nope" });
  expect(response.status).toBe(500);
});
