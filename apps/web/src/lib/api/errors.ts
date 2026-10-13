/** The shape openapi-fetch returns from every request. */
interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** One issue in FastAPI's 422 body: `{ detail: [{ loc, msg, type }] }`. */
interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** A non-2xx response from the API, with FastAPI's `detail` turned into a message. */
export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly status: number,
    message: string,
    /** Per-field messages from a 422, keyed by the body field name. */
    readonly fields: Readonly<Record<string, string>> = {},
    /** The API's `X-Request-ID`, which finds the request's log lines. */
    readonly requestId: string | null = null,
  ) {
    super(message);
  }

  /** The error for a failed result: a 500 quotes its request ID, a 422 maps issues to fields. */
  static fromResult(result: ApiResult<unknown>): ApiError {
    const { response, error } = result;
    const detail = isRecord(error) ? error["detail"] : undefined;
    const requestId = response.headers.get("x-request-id");
    if (response.status >= 500 && requestId) {
      // The API's own 500 says to quote the ID; show it so the user can.
      const message = typeof detail === "string" ? detail : "Something went wrong.";
      return new ApiError(response.status, `${message} (request ${requestId})`, {}, requestId);
    }
    if (typeof detail === "string") {
      return new ApiError(response.status, detail, {}, requestId);
    }
    if (Array.isArray(detail)) {
      const fields: Record<string, string> = {};
      const messages: string[] = [];
      for (const issue of detail as ValidationIssue[]) {
        const field = issue.loc
          .filter((part): part is string => typeof part === "string" && part !== "body")
          .join(".");
        if (field) fields[field] ??= issue.msg;
        messages.push(field ? `${field}: ${issue.msg}` : issue.msg);
      }
      return new ApiError(
        response.status,
        messages.join("; ") || "Validation error",
        fields,
        requestId,
      );
    }
    return new ApiError(
      response.status,
      response.statusText || `Request failed with status ${response.status}`,
      {},
      requestId,
    );
  }
}

/** The data of a 2xx result; anything else throws its `ApiError`. */
export function unwrap<T>(result: ApiResult<T>): T {
  if (result.response.ok) {
    return result.data as T;
  }
  throw ApiError.fromResult(result);
}

/** What to show the user for anything thrown; a failed fetch reads as the API being unreachable. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "The API could not be reached.";
  if (error instanceof Error) return error.message;
  return String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
