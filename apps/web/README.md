# @public-atlas/web

The console: the Next.js front end for `apps/server`.

```sh
vp run dev:web      # from the repo root, http://localhost:3000
vp run dev:api      # the API it talks to, in another terminal
```

```text
apps/web/src/
├── app/              # routes only; each page composes feature components behind <Suspense>
├── features/         # product code by domain, mirroring the API's modules (added with the console)
│   └── <feature>/    # components/, hooks/, queries.ts, mutations.ts, schemas.ts, server.ts
├── components/       # ui/ (shadcn) and shared/ (layout, form, data-table, ...)
├── hooks/            # generic hooks
└── lib/              # api/, formatting/, time-zone/, lists.ts, validation.ts
```

## Calling the API

There is no authentication: the console is an operator's tool. The browser never sees
`API_URL`: Client Components use `browserApi` from `@/lib/api/client`, which calls `/api/*`,
and `next.config.ts` rewrites that to the API. Server Components use `api` from
`@/lib/api/server-client`. `unwrap()` turns a non-2xx result into an `ApiError`.

The rewrite is fixed when Next.js builds, so `API_URL` is a build argument of
`apps/web/Dockerfile`; the server-side client reads the same variable at run time.

## Data flow

Pages are Server Components. Read-only pages fetch and render. Pages that mutate or filter
prefetch into a per-request `QueryClient`, hand the cache over with `<HydrationBoundary>`, and
a Client Component continues with `useSuspenseQuery` on the same key. Query definitions in
each feature's `queries.ts` take the client as a parameter so both sides build identical keys.
Writes are plain functions in `mutations.ts`. List filters, page and sort live in the URL.

## Forms and tables

Forms: TanStack Form bound to shadcn `Field` via `useAppForm`, validated with the Zod schemas
in each feature's `schemas.ts`. Tables: TanStack Table v9 in manual mode, one page of 50 rows,
sorting and paging done by the API.

## Styling

Tailwind CSS v4 and shadcn/ui (`base-nova` style on Base UI, zinc, Geist). Everything lives in
`src/app/globals.css`; prefer semantic utilities (`bg-background`, `text-muted-foreground`).
Add components with:

```sh
cd apps/web && pnpm dlx shadcn@latest add card dialog
```

## Notes

- `reactCompiler` is on: write plain React, use `useMemo`/`useCallback` only where needed.
- `<TimeZoneSync>` writes the browser's zone to a `tz` cookie so server and client format dates the same way.
- `next-env.d.ts` and `.next/types/` are generated and gitignored.
