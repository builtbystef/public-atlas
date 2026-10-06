# Public Atlas

Public Atlas builds a map of the public sector for vendors who sell to governments. For each
public body it records what it is, where it is, which body buys on its behalf, its official web
page, and the web pages that carry procurement signals: budgets, capital plans, council and
board minutes, procurement portals, open tenders, contract awards and strategic plans.

Selling to government needs three things in order: a map of institutions and their signal
sources, continuous collection of what those sources publish, and analysis that turns the
collected text into buying signals. Public Atlas is the first of the three. It finds
institutions and sources. It does not read the sources' documents for their contents.

An AI agent does the finding by browsing official websites. The agent cannot simply assert a
fact. Every fact comes with a quote, the system keeps a stored copy of the page, and code checks
that the quote is really on it. Only then is the fact marked verified. What the rules cannot
decide goes to a human through a review queue.

The design is [docs/product-and-tech-spec.md](docs/product-and-tech-spec.md); the build order
is [docs/todo.md](docs/todo.md); the words the code uses are in
[docs/glossary.md](docs/glossary.md).

## Goals

- **Complete coverage.** Every place and public institution in a country, measured against a hand-labelled dataset, not the agent's own sense of done.
- **Auditable trust.** Every verified fact has a chain of evidence back to an official register or a domain a person verified by hand.
- **Sources mapped to institutions.** Each signal source is linked to the body it belongs to and typed.
- **Controlled runs.** Work can be started, paused, stopped and filtered by place, level and type, in a careful step-by-step mode for development and a hands-off mode for an entire country, or part of a country.
- **Bounded cost.** The agent reaches only approved domains, within a budget per assignment, and every model and search call is priced.

## Pilot

The pilot is Ontario: the province, its 444 municipal and regional governments, the public
bodies under them and their sources. Targets:

| Measure                                            | Target      | How it is measured                                            |
| -------------------------------------------------- | ----------- | ------------------------------------------------------------- |
| Places against the official register               | 100%        | A unit test on the Ontario places list module                 |
| Homepage of each government correct                | 99% or more | The homepage assignment scored on the 25-government eval file |
| Institution recall against the eval dataset        | 95% or more | The scorer (agent eval)                                       |
| Source recall for procurement, minutes and budgets | 90% or more | The scorer (agent eval)                                       |

## Tech stack

| Layer    | Choice                                                                                                                   |
| -------- | ------------------------------------------------------------------------------------------------------------------------ |
| Base     | The [alloy](https://github.com/builtbystef/alloy) template, with auth, workspaces, mail, rate limits and the CRM removed |
| API      | Python 3.14, FastAPI                                                                                                     |
| Database | PostgreSQL, SQLAlchemy 2 async, Alembic, `pg_trgm` for duplicate matching                                                |
| Jobs     | Procrastinate on the same database. Queues: `assignment`, `parse`, `default`                                             |
| Agent    | Pydantic AI; model and reasoning effort set per assignment type                                                          |
| Browser  | Playwright Chromium, an owned layer: one policy object, one session, the tools                                           |
| Parsing  | Docling on the `parse` worker image only                                                                                 |
| Storage  | S3-compatible port: RustFS locally, Cloudflare R2 hosted                                                                 |
| Search   | Brave Search behind a port, off unless configured                                                                        |
| Console  | Next.js 16, shadcn/ui, TanStack Query, Form and Table, a generated API client                                            |
| Tracing  | Logfire when configured; cost always from the `usage` table                                                              |

| Concern    | TypeScript                                    | Python                          |
| ---------- | --------------------------------------------- | ------------------------------- |
| Packages   | pnpm via [Vite+](https://viteplus.dev) (`vp`) | [uv](https://docs.astral.sh/uv) |
| Format     | oxfmt (`vp check`)                            | Ruff                            |
| Lint       | oxlint (`vp check`)                           | Ruff                            |
| Type check | tsc (`vp check`)                              | [ty](https://docs.astral.sh/ty) |
| Tests      | Vitest (`vp test`)                            | pytest                          |

## Requirements

- Node ≥ 24, Python ≥ 3.14 (uv downloads it), uv ≥ 0.12
- Docker with Compose, for the local PostgreSQL and RustFS

## Commands

```sh
vp run check         # format + lint + typecheck, both languages (check:fix to apply fixes)
vp run test          # Vitest + pytest
vp run ci            # everything CI runs
vp run infra:up      # PostgreSQL and RustFS in Docker (infra:down stops them)
vp run db:migrate    # alembic upgrade head
cd apps/server && uv run public-atlas seed canada   # the country tables and the Ontario anchor; safe to rerun
cd apps/server && uv run public-atlas load-list ontario_places           # what loading Ontario's places would change
cd apps/server && uv run public-atlas load-list ontario_places --apply   # load them; a rerun changes nothing
vp run dev           # API, worker and web together, on the host
vp run dev:api       # http://127.0.0.1:8000/docs
vp run dev:web       # http://localhost:3000
vp run app:build     # the server, agent, parse and web images
vp run app:up        # the whole stack in Docker (app:down stops it, infra stays)
vp run browser:install  # Playwright's Chromium, once per machine, for the agent worker and its tests
```

Run `vp config` once after cloning to activate the pre-commit hook.

## Layout

- `apps/server`: the FastAPI app, the workers and the agent (package `public_atlas`).
- `apps/web`: the console, a Next.js 16 front end (`@public-atlas/web`).
- `packages/api-client`: typed fetch client generated from the API's OpenAPI schema (`@public-atlas/api-client`).

New projects go in `apps/*`, `packages/*` or `tools/*`. TypeScript projects extend a preset
from `tsconfig/` and take versions from the catalog in `pnpm-workspace.yaml`. Python projects
are listed under `[tool.uv.workspace] members` in the root `pyproject.toml`.

### apps/server

```
apps/server/src/public_atlas/
  asgi.py                 the ASGI app for `fastapi run`; the one place the API reads the environment
  cli.py                  `public-atlas`: the operator's commands (seed), reading the environment like asgi.py
  main.py                 create_app(settings): the FastAPI app; its lifespan calls build_resources once
  resources.py            build_resources(settings): database, store, jobs, searcher, models, parser
  dependencies.py         FastAPI dependencies that read the resources from request.state
  config.py               Settings: deployment values only, no product data
  db/                     base, session, checked strings (an enum as text with a check constraint)
  integrations/           storage, search, parse, browser, ai: one port each
  jobs/                   Procrastinate registry, task decorator, worker, stalled sweep, purge
  modules/
    countries/            the five country tables, seeds, naming rules, the CountryRules object
    graph/                places, institutions, sources, domains, homepages, webpages,
                          aliases, identifiers, metrics, duplicate search, status_changes.py
    evidence/             snapshots, evidence, quote_checks.py, capture.py, parse jobs
    review/               review items, kinds, approve, reject, merge
    assignments/          runs, assignments, spawning, the descriptor per type (budget, model), the run_assignment job
    agent/                the session context, briefing, the findings and their adapter, runner, events, video, purges
    imports/              the shared list loader, and lists/<name>.py per official list
    evals/                dataset, harness, scorer, eval runs
  shared/                 errors, logs, pagination, text helpers
```

Every function that needs the database, the store or the model receives it as an argument.
Nothing reads settings at import time: `asgi.py` and the worker's `main` build one `Settings`
from `PUBLIC_ATLAS_*` environment variables (every one is documented in
`apps/server/.env.example`) and hand it to `build_resources`. Tests and the eval runner call
`build_resources` with their own settings.

- **Errors and logs**: every response and log line carries `X-Request-ID`. Unhandled exceptions become a plain 500.
- **Database**: SQLAlchemy 2 async over psycopg 3, Alembic migrations (`cd apps/server && uv run alembic revision --autogenerate -m "..."`). Integration tests run against real PostgreSQL in a rolled-back transaction; a model change without a migration fails CI.
- **Routes** have no trailing slash. The console reaches the API through a same-origin `/api` rewrite, which drops one, and the API does not redirect, so a redirect could never leak its internal address.
- **Storage**: a port in `integrations/storage`, S3-compatible. The app writes snapshots and videos; the browser reads through presigned download URLs.
- **Jobs**: [Procrastinate](https://procrastinate.readthedocs.io) on the app's PostgreSQL, no broker. Jobs are written on the handler's session, so they commit or roll back with the rows they are about. Tasks live in a `jobs.py` next to what they work on, are listed in `jobs/__init__.py` and name their queue: `default` for the platform's own tasks, `assignment` for the agent, `parse` for document parsing. `public-atlas-worker` serves every queue unless started with `--queues`. A cron task requeues the jobs of a worker whose heartbeat stopped, and fails one that is out of retries through its task's `abandoned` hook.
- **Browser** (`integrations/browser`): one `BrowserPolicy` decides every request (the allowlist with subdomains, private addresses, `robots.txt`, pacing shared across sessions, the resource types never fetched); the session is one Chromium with a route guard; the tools return typed results. Every page the agent lands on reaches `modules/evidence/capture.py` as plain values and is stored as a snapshot. Tests marked `browser` drive a real Chromium against a local fixture site and are skipped until `vp run browser:install` has run.
- **Parsing** (`integrations/parse`): documents fetched with `read_file` are parsed on the `parse` queue in ranges of pages, one page per range on a retry; a worker that has grown past `parse_retire_rss_mb` stops after its job. Tests marked `parse` need the `parse-cpu` group and run in a CI job of their own.
- **Runs and assignments** (`modules/assignments`): a run is created with a filter and a mode and seeds itself with the work due for the subjects in scope; every status change that asks for work (`Spawn`) becomes an assignment of the run it belongs to, held in step mode and queued with a job in auto mode, never doubled while open. Pause puts a picked-up job back with a delay and leaves the assignment queued; stop cancels what is held or queued. An assignment changes status only through `lifecycle.py`.
- **The agent** (`modules/agent`): one job runs an assignment as fresh sessions from the database and the last handoff note, each on the model its descriptor names (`descriptors.py`, product data) with the browser's tools and the findings registered through one adapter. A session ends with a finishing tool, when the budget runs out (`out_of_budget`) or when a request passes half the context window (a handoff); a job runs at most twenty sessions, then requeues; a job that fails on its last attempt finishes the assignment `failed`. Everything a session saw, said and did is written to `agent_run_events` when it ends, with the videos of a run that records them; daily purges drop the videos after `video_keep_days` and the events after `events_keep_days`.
- **Cost**: every model and search call is one `usage` row, priced from `modules/assignments/prices.toml`.

### Rules for the code

- One word per concept, from the [glossary](docs/glossary.md). No synonyms (`assignment`, not `item` or `work`; `homepage`, not `official webpage`; `finish`, not `complete` or `close`).
- A status changes only in `status_changes.py`. An assignment changes status only in `assignments/lifecycle.py`.
- Tool results and refusals are typed values; prose is rendered at the tool edge.
- A module imports another only through its `service.py` and `models.py`. No imports after `TYPE_CHECKING` blocks to dodge cycles; a cycle means two things are one module.
- Product data (city names, prices, model names) lives in tables or data files, never in `Settings`.

## Deploying

One image per process, one command per process, settings from environment variables:

| Process  | Image                    | Command                                   | Port |
| -------- | ------------------------ | ----------------------------------------- | ---- |
| `api`    | `apps/server` (`server`) | `fastapi run --port 8000 --proxy-headers` | 8000 |
| `worker` | `apps/server` (`server`) | `public-atlas-worker --queues default`    | none |
| `agent`  | `apps/server` (`agent`)  | `public-atlas-worker --queues assignment` | none |
| `parse`  | `apps/server` (`parse`)  | `public-atlas-worker --queues parse`      | none |
| `web`    | `apps/web`               | `node apps/web/server.js`                 | 3000 |

Plus managed PostgreSQL and an S3-compatible bucket (Cloudflare R2: endpoint
`https://<account id>.r2.cloudflarestorage.com`, region `auto`, path style off). Only `web`
needs a public address; it forwards `/api/*` to the API. Run `alembic upgrade head` from
`/app/apps/server` before new code starts. Health checks: `/health` (liveness),
`/health/{db,storage}` (readiness).

```sh
PUBLIC_ATLAS_DATABASE_URL=postgresql+psycopg://...
PUBLIC_ATLAS_STORAGE_ENDPOINT_URL=... PUBLIC_ATLAS_STORAGE_BUCKET=... PUBLIC_ATLAS_STORAGE_ACCESS_KEY=... PUBLIC_ATLAS_STORAGE_SECRET_KEY=...
PUBLIC_ATLAS_STORAGE_PATH_STYLE=false            # true for MinIO and RustFS
API_URL=http://api.internal:8000                 # web only; also a build argument of apps/web/Dockerfile
```

`.github/workflows/images.yml` builds `ghcr.io/<owner>/<repo>/{server,server-agent,server-parse,web}`
after CI passes on `main`.

## Supply-chain policy

New package versions are held back for 4 days before install (pnpm `minimumReleaseAge`, uv
`exclude-newer`), and Dependabot runs weekly with the same cooldown. pnpm runs no dependency
build scripts (`strictDepBuilds` with an empty `allowBuilds`), refuses exotic subdependency
sources, and keeps provenance from being downgraded. Every GitHub Action is pinned to a commit.
