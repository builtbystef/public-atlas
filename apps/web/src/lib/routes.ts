/**
 * Every page of the console, so a link is a function call rather than a
 * string put together where it is used. Next's typed routes check that each
 * of these matches a page under app/.
 */
export const paths = {
  /** The front page: the saved lists. `/` redirects here (next.config.ts). */
  lists: "/lists",
  list: (id: string) => `/lists/${id}` as const,
  runs: "/runs",
  runNew: "/runs/new",
  run: (id: string) => `/runs/${id}` as const,
  assignments: "/assignments",
  assignment: (id: string) => `/assignments/${id}` as const,
  institutions: "/institutions",
  institution: (id: string) => `/institutions/${id}` as const,
  /** The institutions list with a query string of filters, as `toSearchString` builds one. */
  institutionsWhere: (search: string) => `/institutions?${search}` as const,
  places: "/places",
  place: (id: string) => `/places/${id}` as const,
  review: "/review",
  reviewItem: (id: string) => `/review/${id}` as const,
  countries: "/countries",
  country: (code: string) => `/countries/${code}` as const,
  evals: "/evals",
  evalRun: (id: string) => `/evals/${id}` as const,
  settings: "/settings",
} as const;

export type Paths = typeof paths;
