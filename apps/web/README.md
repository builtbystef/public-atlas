# @public-atlas/web

The console: the Next.js front end for `apps/server`. Spec section 11 lists its pages: runs,
assignments, institutions, the review queue, countries and evals.

```sh
vp run dev:web      # from the repo root, http://localhost:3000
vp run dev:api      # the API it talks to, in another terminal
```

```text
apps/web/src/
├── app/(console)/    # routes only; each page composes feature components behind <Suspense>
├── features/         # product code by domain, mirroring the API's modules
│   ├── runs/         # list, detail, the create form, pause/stop/release
│   ├── assignments/  # list with filters, detail with events, videos, findings and spend
│   ├── graph/        # institutions table and detail, places, the evidence list with the highlighted quote
│   ├── review/       # kinds decided together, items, approve/reject/merge
│   ├── countries/    # settings, levels, the country's types, the global type tables
│   └── evals/        # eval runs over time, scores per subject and type
│   each: components/, hooks/, queries.ts, mutations.ts, schemas.ts
├── components/       # ui/ (shadcn) and shared/ (layout, form, data-table, status badges, ...)
├── hooks/            # generic hooks
└── lib/              # api/, formatting/, time-zone/, labels.ts, lists.ts, routes.ts, validation.ts
```

## Calling the API

There is no authentication: the console is an operator's tool. The browser never sees
`API_URL`: Client Components use `browserApi` from `@/lib/api/client`, which calls `/api/*`,
and `next.config.ts` rewrites that to the API. Server Components call `getApi()` from
`@/lib/api/server`. `unwrap()` turns a non-2xx result into an `ApiError`; `unwrapOrNotFound()`
renders the not-found page on a 404.

The rewrite is fixed when Next.js builds, so `API_URL` is a build argument of
`apps/web/Dockerfile`; the server-side client reads the same variable at run time.

## The two databases

Every page reads either the live graph or the eval harness's database (spec section 10). The
switch on the settings page sets a `db` cookie; both API clients send it as the API's
`X-Database` header (`lib/api/database.ts`). Switching clears the browser's query cache and
re-renders every page from the server. The API answers 422 for `eval` when the server has no
eval database configured.

## Data flow

Pages are Server Components. Read-only pages fetch and render. Pages that mutate or filter
prefetch into a per-request `QueryClient`, hand the cache over with `<HydrationBoundary>`, and
a Client Component continues with `useSuspenseQuery` on the same key. Query definitions in
each feature's `queries.ts` take the client as a parameter so both sides build identical keys.
Writes are plain functions in `mutations.ts`. List filters, page and sort live in the URL.
Pages about work in progress (a run, a running assignment, the queue) poll on an interval.

## Forms and tables

Forms: TanStack Form bound to shadcn `Field` via `useAppForm`, validated with the Zod schemas
in each feature's `schemas.ts`. Tables: TanStack Table v9 in manual mode, one page of 50 rows,
sorting and paging done by the API. Every enum value's label is in `lib/labels.ts`; type
names the country tables define go through `humanize()`.

## Styling

Tailwind CSS v4 and shadcn/ui (`base-nova` style on Base UI, zinc, Geist). Everything lives in
`src/app/globals.css`; prefer semantic utilities (`bg-background`, `text-muted-foreground`).
Add components with:

```sh
cd apps/web && pnpm dlx shadcn@latest add card dialog
```

## Notes

- `reactCompiler` is on: write plain React, use `useMemo`/`useCallback` only where needed.
- `typedRoutes` is on: every link goes through `paths` in `lib/routes.ts`.
- `<TimeZoneSync>` writes the browser's zone to a `tz` cookie so server and client format dates the same way.
- `next-env.d.ts` and `.next/types/` are generated and gitignored; run `pnpm exec next typegen` before `vp check` on a fresh clone.
