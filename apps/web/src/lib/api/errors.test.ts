import { expect, test } from "vite-plus/test";

import { ApiError, errorMessage } from "./errors";

function result(status: number, body: unknown, headers: Record<string, string> = {}) {
  const response = new Response(null, { status, headers });
  return { error: body, response };
}

test("a detail string becomes the message", () => {
  const error = ApiError.fromResult(result(401, { detail: "Not authenticated" }));
  expect(error.status).toBe(401);
  expect(errorMessage(error)).toBe("Not authenticated");
});

test("a 500 quotes the request ID from the header", () => {
  const error = ApiError.fromResult(
    result(
      500,
      {
        detail: "Something went wrong. Quote the request ID when reporting it.",
        request_id: "abc123",
      },
      { "x-request-id": "abc123" },
    ),
  );
  expect(error.requestId).toBe("abc123");
  expect(errorMessage(error)).toBe(
    "Something went wrong. Quote the request ID when reporting it. (request abc123)",
  );
});

test("a 4xx keeps the request ID without showing it", () => {
  const error = ApiError.fromResult(
    result(404, { detail: "Institution not found" }, { "x-request-id": "abc123" }),
  );
  expect(error.requestId).toBe("abc123");
  expect(errorMessage(error)).toBe("Institution not found");
});

test("a 422 maps each issue to its body field and lists them all", () => {
  const error = ApiError.fromResult(
    result(422, {
      detail: [
        { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
        { loc: ["body", "email"], msg: "second message is not used", type: "value_error" },
        { loc: ["body", "company", "id"], msg: "Input should be a valid UUID", type: "uuid" },
        { loc: ["query", "limit"], msg: "Input should be less than 501", type: "less_than" },
        { loc: ["body", 0], msg: "Field required", type: "missing" },
      ],
    }),
  );
  expect(error.status).toBe(422);
  expect(error.fields).toEqual({
    email: "value is not a valid email address",
    "company.id": "Input should be a valid UUID",
    "query.limit": "Input should be less than 501",
  });
  expect(errorMessage(error)).toBe(
    "email: value is not a valid email address; email: second message is not used; " +
      "company.id: Input should be a valid UUID; query.limit: Input should be less than 501; " +
      "Field required",
  );
});

test("a body without a detail falls back to the status", () => {
  const error = ApiError.fromResult(result(502, "<html>Bad Gateway</html>"));
  expect(errorMessage(error)).toBe("Request failed with status 502");
  expect(error.fields).toEqual({});
  const empty = ApiError.fromResult(result(422, { detail: [] }));
  expect(errorMessage(empty)).toBe("Validation error");
});

test("errors that are not from the API are worded for the user", () => {
  expect(errorMessage(new TypeError("Failed to fetch"))).toBe("The API could not be reached.");
  expect(errorMessage(new Error("boom"))).toBe("boom");
  expect(errorMessage("plain")).toBe("plain");
  expect(errorMessage(undefined)).toBe("undefined");
});

test("unwrap returns the data of a 2xx and throws the ApiError of anything else", async () => {
  const { unwrap } = await import("./errors");
  expect(unwrap({ data: { id: 1 }, response: new Response(null, { status: 200 }) })).toEqual({
    id: 1,
  });
  expect(() => unwrap(result(404, { detail: "Institution not found" }))).toThrowError(
    expect.objectContaining({ name: "ApiError", status: 404, message: "Institution not found" }),
  );
});
