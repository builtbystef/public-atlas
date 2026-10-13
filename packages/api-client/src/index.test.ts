import { expect, expectTypeOf, test, vi } from "vite-plus/test";

import type { paths } from "./generated/schema";
import { createApiClient, type MergeInput } from "./index";

test("the client sends a typed path to the base URL", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({ status: "ok" }));
  const api = createApiClient({ baseUrl: "http://api.test", fetch });

  const { data } = await api.GET("/health");

  expect(data).toEqual({ status: "ok" });
  const request = fetch.mock.calls[0]?.[0] as Request | undefined;
  expect(request?.url).toBe("http://api.test/health");
  // A path the API does not serve is a type error, not a 404 at runtime.
  // @ts-expect-error -- not a path of the schema
  void api.GET("/healthz").catch(() => undefined);
});

test("a merge's body requires the survivor and may leave the note out", () => {
  // The guard against drift between the schema and the console's forms: `into_id` is
  // required and a UUID string, `note` is optional and nullable, and nothing else is in it.
  type MergeBody =
    paths["/review-items/{review_item_id}/merge"]["post"]["requestBody"]["content"]["application/json"];
  expectTypeOf<MergeBody>().toEqualTypeOf<MergeInput>();
  expectTypeOf<keyof MergeInput>().toEqualTypeOf<"into_id" | "note">();
  expectTypeOf<MergeInput["into_id"]>().toEqualTypeOf<string>();
  expectTypeOf<MergeInput["note"]>().toEqualTypeOf<string | null | undefined>();
  expectTypeOf<{ into_id: string }>().toExtend<MergeInput>();
  expectTypeOf<{ note: null }>().not.toExtend<MergeInput>();
  expectTypeOf<{ into_id: null }>().not.toExtend<MergeInput>();
});
