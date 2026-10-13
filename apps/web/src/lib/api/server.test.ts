import { expect, test, vi } from "vite-plus/test";

import { unwrapOrNotFound } from "./server";

// The marker import throws outside a Server Component; the function under test is plain.
vi.mock("server-only", () => ({}));

function result(status: number, body: unknown) {
  return { error: body, response: new Response(null, { status }) };
}

test("a 2xx unwraps to its data", () => {
  expect(
    unwrapOrNotFound({ data: { id: 1 }, response: new Response(null, { status: 200 }) }),
  ).toEqual({ id: 1 });
});

test("a 404 renders the not-found page", () => {
  // Next's notFound() throws the error its error boundary turns into the not-found page.
  expect(() => unwrapOrNotFound(result(404, { detail: "Institution not found" }))).toThrow(
    /^NEXT_HTTP_ERROR_FALLBACK;404$/,
  );
});

test("any other failure is the API's own error", () => {
  expect(() => unwrapOrNotFound(result(403, { detail: "Read only" }))).toThrowError(
    expect.objectContaining({ name: "ApiError", status: 403, message: "Read only" }),
  );
});
