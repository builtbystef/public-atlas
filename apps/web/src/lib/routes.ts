/**
 * Every page of the console, so a link is a function call rather than a
 * string put together where it is used. Next's typed routes check that each
 * of these matches a page under app/.
 */
export const paths = {
  home: "/",
  runs: "/runs",
  runNew: "/runs/new",
  run: (id: string) => `/runs/${id}` as const,
  assignments: "/assignments",
  assignment: (id: string) => `/assignments/${id}` as const,
  institutions: "/institutions",
  institution: (id: string) => `/institutions/${id}` as const,
  /** The institutions list filtered to one place. */
  institutionsIn: (placeId: string) => `/institutions?place_id=${placeId}` as const,
  review: "/review",
  reviewItem: (id: string) => `/review/${id}` as const,
  countries: "/countries",
  country: (code: string) => `/countries/${code}` as const,
  evals: "/evals",
  evalRun: (id: string) => `/evals/${id}` as const,
  settings: "/settings",
} as const;

export type Paths = typeof paths;
