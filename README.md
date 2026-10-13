# Public Atlas

Public Atlas maps the public sector for companies that sell to governments. It finds every
public body in a country (governments, school boards, transit agencies, police boards, health
units, libraries, crown corporations and so on), its official website, and the pages on that
site that carry buying signals: budgets, capital plans, council and board minutes, procurement
portals, tenders, contract awards and strategic plans.

The hard part is not finding pages. It is finding _all_ of them, knowing which body each one
belongs to, and being able to prove it. So the project is built around three ideas:

1. **Official lists first, agents second.** Where a government publishes a register (a census
   file, a municipal directory, a list of agencies), a scripted loader reads it, and the AI
   agent only fills the gaps. Twenty-eight lists cover Canada and the United States today.
2. **Nothing is true without evidence.** The agent browses official websites, but it cannot
   just assert a fact. Each finding comes with a quote, the system stores a copy of the page,
   and code checks that the quote is really on it. Only then is the fact _verified_. Anything
   the rules cannot settle goes to a person through a review queue.
3. **Measured, not felt.** A hand-labelled dataset scores every change: recall and precision per
   assignment type against fixed gates, and the dollar cost of getting there.

For the full design (data model, trust rules, agent, evals), read the
[technical specification](docs/product-and-tech-spec.md).

## Screenshots

|                                                                                                                                                                    |                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Run**: its filter and mode, progress and cost, its assignments, and release / pause / stop<br>![Run](docs/screenshots/runs.png)                                  | **Assignment detail**: every tool call and result, the finish, and the browser session's video<br>![Assignment](docs/screenshots/assignment.png) |
| **Session timeline**: the system prompt, the briefing, then each model turn, tool call and result<br>![Session timeline](docs/screenshots/assignment-events.png)   | **Institution**: type, parent, homepage, the bodies under it, and its sources by type<br>![Institution](docs/screenshots/institution.png)        |
| **Review item**: the question, why it was raised, the evidence, the entity, and approve / merge / reject<br>![Review](docs/screenshots/review.png)                 | **Eval run**: recall and precision per assignment type against the gates, then by subject<br>![Evals](docs/screenshots/evals.png)                |
| **Country config**: a country's levels, institution types and the sources expected of each<br>![Countries](docs/screenshots/countries.png)                         | **New run**: a country, a mode, and a filter by assignment type, level, institution type and subject<br>![New run](docs/screenshots/new-run.png) |
| **Institutions**: the whole graph as a table, filtered by place, country, level, type, status and population<br>![Institutions](docs/screenshots/institutions.png) | **Graph**: places and the institutions under them, centred on any place<br>![Graph](docs/screenshots/graph.png)                                  |

## How it works

**Data enters the graph three ways.** A _seed_ creates a country, its levels and types, and the
top-level governments and domains trusted by hand. _Official lists_ load places and institutions
from government registers, each file pinned by URL and hash so a fresh clone rebuilds the same
database. _Assignments_ send the agent after everything the lists do not cover.

**There are three kinds of assignment.** `find_homepage` finds and verifies the official site
of one institution. `find_institutions` finds the public bodies under one place.
`find_sources` finds the signal pages of one institution. A _run_ picks a filter (country,
level, type, subject) and a mode (step-by-step or automatic), then creates the work that is
due. Findings spawn the next assignments, so one run over a province fans out on its own and
never queues the same work twice.

**The agent is fenced.** It works in a real Chromium that only reaches approved domains,
honours `robots.txt`, paces its requests and refuses private addresses. Every page it lands on
is stored as a snapshot. A new domain becomes trusted only through a chain back to an official
source: a trusted page must link to it, or a reviewer approves it. PDFs and spreadsheets are
parsed on a separate worker, a few pages at a time and only as far as the agent reads.

**Everything is bounded and observable.** Each assignment has a request and token budget, and a
model chosen per type. A session ends when the agent finishes, the budget runs out, the
assignment stops making progress, or the context passes half the model's window, in which case
the agent writes a handoff note and a fresh session picks up. Every model and search call is a
priced `usage` row, and every session's events, tool calls and video can be replayed in the
console.

**Work is queued in PostgreSQL.** There is no message broker, so a job commits or rolls back
with the rows it is about. A worker whose heartbeat stops has its jobs requeued, and pausing a
run puts picked-up jobs back with a delay. Every status change goes through one module, so there
is one place to look when something is wrong.

## Tech stack

| Layer   | Choice                                                                                                                                 |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| API     | Python 3.14, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL (`pg_trgm` for duplicates)                                               |
| Jobs    | Procrastinate on the same PostgreSQL. Queues: `assignment`, `parse`, `default`                                                         |
| Agent   | Pydantic AI; model and reasoning effort set per assignment type                                                                        |
| Browser | Playwright Chromium behind one policy object                                                                                           |
| Parsing | Docling, on the `parse` worker only                                                                                                    |
| Storage | S3-compatible: RustFS locally, Cloudflare R2 hosted                                                                                    |
| Search  | Brave Search, off unless configured                                                                                                    |
| Console | Next.js 16, shadcn/ui, TanStack Query, Form and Table, a generated API client                                                          |
| Tooling | pnpm via [Vite+](https://viteplus.dev), [uv](https://docs.astral.sh/uv), Ruff, [ty](https://docs.astral.sh/ty), oxlint, Vitest, pytest |

Settings come from `PUBLIC_ATLAS_*` environment variables, documented in
`apps/server/.env.example`. GitHub Actions builds four images (`server`, `server-agent`,
`server-parse`, `web`) after CI passes. Dependencies are held back four days before install,
and every action is pinned to a commit.

## Running it

Needs Node 24+, uv 0.12+ (it downloads Python 3.14) and Docker with Compose.

```sh
vp install && vp config          # dependencies and the pre-commit hook
(cd apps/server && uv sync --group parse-cpu)   # Docling for the parser; parse-cu130 for an NVIDIA GPU
vp run infra:up                  # PostgreSQL and RustFS in Docker
vp run db:migrate
vp run browser:install           # Playwright's Chromium, once per machine
cd apps/server
uv run public-atlas seed canada
uv run public-atlas load-list canada/ontario/places --apply
cd ../..
vp run dev                       # API on :8000, one worker on every queue, console on :3000
```

Then, with `PUBLIC_ATLAS_OPENAI_API_KEY` set in `apps/server/.env`:

```sh
cd apps/server
uv run public-atlas run create pilot --mode step --level municipality --video   # a run, holding its assignments
uv run public-atlas run release <run id> --limit 2                             # let two through
uv run public-atlas eval run                                                   # the quick eval: five subjects and the homepage file
uv run public-atlas --help                                                     # seed, load-list, lists, run, eval, worker
```

`vp run check` formats, lints and type-checks both languages; `vp run test` runs Vitest and
pytest; `vp run ci` is what CI runs.

## Layout

```
apps/server/src/public_atlas/     the FastAPI app, the CLI, the workers and the agent
  modules/countries/              country tables, seeds, naming rules
  modules/graph/                  places, institutions, sources, domains, homepages, status changes
  modules/evidence/               snapshots, quotes and the quote check, page capture, parse jobs
  modules/review/                 the review queue: approve, reject, merge
  modules/assignments/            runs, assignments, spawning, budgets, prices
  modules/agent/                  sessions, briefing, findings, tools, events, video
  modules/imports/lists/          one module per official list, by country and region
  modules/evals/                  dataset, harness, scorer
  integrations/                   storage, search, parse, browser, ai: one port each
  jobs/                           the worker, the stalled-job sweep, purges
apps/web/                         the console (Next.js)
packages/api-client/              typed client generated from the API's OpenAPI schema
docs/                             the specification, the glossary and the screenshots
```
