# Public Atlas

Read `docs/product-and-tech-spec.md` before changing anything: it is the design, and
`docs/todo.md` is the build order. Phases are built in order; a phase is done when its
"Done when" holds.

## Words

Use the words in `docs/glossary.md` (the spec's section 13) and no synonyms. One word per
concept, even when the name gets longer: `assignment` not `item`, `homepage` not `website`,
`institution` not `organization`, `finish` not `complete`. `trusted` (a verified official
domain) is not `allowed` (on the browser allowlist). Check new names against the glossary's
"Not" column.

## Rules for the code

- Every function that needs the database, the store or the model receives it as an argument. Nothing reads settings at import time; `build_resources(settings)` in `resources.py` is the one door, called by `asgi.py`, the worker, the tests and the eval runner.
- A status changes only in `graph/status_changes.py`. An assignment changes status only in `assignments/lifecycle.py`.
- Tool results and refusals are typed values; prose is rendered at the tool edge.
- A module imports another only through its `service.py` and `models.py`. No imports after `TYPE_CHECKING` blocks to dodge cycles; a cycle means two things are one module.
- Product data (city names, prices, model names) lives in tables or data files, never in `Settings`.
- Enumerations are checked strings: a text column with a check constraint generated from the Python `StrEnum`, never a PostgreSQL enum type.
- API routes have no trailing slash.

## Working here

- `vp run check` and `vp run test` must pass before a phase is called done. Both need `vp run infra:up` (PostgreSQL and RustFS).
- Python: `uv run ...` from the repo root; Alembic from `apps/server`. TypeScript: `vp ...`.
- Tests run against real PostgreSQL in a rolled-back transaction, with an in-memory object store and an inline job queue (`apps/server/tests/integration/conftest.py`).
- After changing a route or a schema, run `vp run generate` and commit the regenerated client.
