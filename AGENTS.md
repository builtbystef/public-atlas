# Working in this repository

Public Atlas is a pnpm and uv monorepo: a Python server in `apps/server` (FastAPI, SQLAlchemy,
procrastinate, Playwright) and a Next.js console in `apps/web` with its generated client in
`packages/api-client`. The README explains what the product does and how the pieces fit;
`docs/glossary.md` names the things. This file holds the rules that are not obvious from the
code.

Run `vp run check` before handing work back, and `vp run test` when you have touched anything
the tests cover. `vp run test:py` runs the Python suite alone (`uv run pytest <path>` for one
file), `vp run test:ts` the Vitest suite. The Python suite needs the PostgreSQL and object store
from `vp run infra:up`. `vp run test:e2e` runs the console smoke (`apps/web/e2e`) in Playwright
against the API and the built console (`next build` in `apps/web` first); it needs a migrated
database seeded with `public-atlas seed canada`, and it creates a step run named "Console
smoke …" that it stops when done. CI runs it after the build.

A console test that renders (a hook, a component) starts with `// @vitest-environment jsdom`
and uses Testing Library; the rest run in Node. The API calls a hook makes are replaced with
`vi.mock` of the feature's `mutations.ts`, since the browser client's `/api` base URL has no
page to resolve against in a test; the body each call receives is what such a test asserts.

## Testing

The tests are the product's safety net: they keep the agent on approved sites, keep money
counted, and keep the trust chain honest. A test that cannot fail is worse than no test, because
it is counted as cover. These rules apply to every test in either language, and
`docs/testing-audit.md` shows what each of them looks like when broken.

### Expected values are written by hand

An expected value is a fact the test author knows independently of the code: a number worked
out on paper, a string copied from the fixture, a row read from the seed. It is never imported
or computed from the module under test.

- Do not `assert x == module.CONSTANT`, `text.startswith(prompts.COMMON)`, or
  `attempts == MAX_ATTEMPTS - 1`. Write the literal.
- Do not build the expectation with the same comprehension, loader or builder that produced
  the input. `len(build()) == len(build())` is a tautology.
- Do not snapshot a function's own diagnostics as a golden dictionary. Pin the totals that
  matter and let the rest change.
- Do not re-implement the rule under test inside the test (a hand copy of the loader's matching
  rules, a second `_find_place`). Call the real one, or assert the end state it should produce.
- Do not grep the source text. A test asserts behaviour, not spelling.
- In the console, read limits from the generated schema or the module's exported constant only
  when that constant is itself the contract; otherwise write the number down.

### Assert the value, not that there is one

Where the right answer is known, assert it. `is not None`, `> 0`, `len(...) > 0`,
`startswith(...)`, `in`, or `success === false` are allowed only when the behaviour really is
"some value exists", and that is rare.

- A budget comes from a descriptor: assert it equals the descriptor's number, not that it is
  positive.
- A finding links to a page: assert which page, by id.
- A spawn list has one entry: assert the exact entry, `== [Spawn(FIND_SOURCES, library.id)]`.
- A schema rejects: assert the path or message of the issue, so a rejection for the wrong
  reason fails.
- A quantifier over a collection (`all(...)`, `<=`, `for row in rows: assert ...`) must sit
  beside an assertion that the collection is not empty, or be replaced by the exact expected
  collection.
- A cost is asserted as a number of dollars, on a priced model, never only at zero.

### Every `pytest.raises` carries `match`

An exception without a message check passes on the wrong exception from the wrong place. Use
`pytest.raises(SomeError, match=r"...")` with the part of the message that names the cause, and
in Vitest `toThrow(/.../)` the same way. After the raise, assert the state the failure was meant
to leave behind (nothing committed, the row unchanged, the old summary kept).

### Every skip has a CI job that runs the test

A test that skips on the machine that counts is green by omission. The markers in the root
`pyproject.toml` are the only skip mechanism, and each has a job:

| Marker    | Skipped when                               | Where it runs                                                                              |
| --------- | ------------------------------------------ | ------------------------------------------------------------------------------------------ |
| `browser` | Chromium is not installed                  | the main CI job, after `playwright install chromium`                                       |
| `parse`   | Docling is not installed                   | the `parse` CI job, with the `parse-cpu` group                                             |
| `lists`   | an official list's files cannot be fetched | both jobs, after `lists fetch`, with `PUBLIC_ATLAS_REQUIRE_LISTS=1` so a skip is a failure |

Do not add a bare `pytest.skip` or `skipif`, a new marker, or an `if not available: return`.
If a test needs a tool CI lacks, add the tool to CI in the same change. A list test that reads
a PDF carries both `lists` and `parse`. Vitest has no skips.

### A test named for a behaviour asserts that behaviour

The name is the specification, written as a sentence: `test_a_lookalike_suffix_is_not_a_subdomain`,
`test("a filter change returns to page 1 but keeps the sort")`. Read the body against the name
before finishing:

- "cancels held and queued work" creates a queued row and asserts it was cancelled, not only
  the held one.
- "the latest snapshot is the newest" has at least two snapshots, so an `asc()` would fail.
- "a stale cache is fetched again" exercises the refetch, not only the failure branch.
- "sits at a place" resolves the place, not the level enum.

If the body cannot be made to match the name, change the name to what it does check, and add
the missing test as its own function.

### One scenario per test, with the full end state asserted

Each test sets up one situation and asserts everything that situation should have changed and
the one thing it should not. Rejecting a domain asserts the domain's status, the homepage that
sat on it, the institution's link, the review item and the spawn. Two scenarios that share a
setup are two tests or one parametrized test with a spelled-out table, not one test with two
halves. Three cases that must behave alike (held, queued, running) appear as three rows.

A boundary gets both sides: 29 s and 31 s, attempt 4 and attempt 5, exactly half the window
and one token over. A refusal gets its reason. A fail-closed rule gets a test where the lookup
fails.

### What the fixtures are, and what they stand in for

- **The database is real.** Every integration test runs in a transaction on
  `public_atlas_test` that is rolled back after it (`db` in `tests/integration/conftest.py`).
  Assert through the ORM or the API, not by inspecting the fake.
- **The model is scripted, and priced.** `scripted(script)` plays a list of tool calls and a
  finish as the model, and charges them from `prices.toml` under the name of the model it
  stands in for. Give each response explicit `usage` and assert the exact dollar sum.
- **Storage, parsing and search are in memory.** `MemoryObjectStore` and the in-memory parser
  and search are ports with the same contract as the real ones; a test that needs the S3
  contract (a missing bucket, a `ClientError`) runs against the bucket `infra:up` and CI both
  provide, as `tests/integration/integrations/test_storage.py` does.
- **The browser is real.** Tests marked `browser` drive Chromium against the local fixture
  `site`. Private-address blocking must be on in any test that claims to test the boundary.
- **Jobs run inline.** `InlineConnector` runs each queued job at once and asserts it succeeded.
  A retry, a last-attempt flag or a stalled worker is tested against the real queue schema, not
  the in-memory connector.
- **Mocks are a last resort.** Twenty-odd lines in the whole suite. Prefer a fake that honours
  the port's contract, injected through the existing fixture, to `monkeypatch` on a module.
- **No test reads the developer's environment.** Build `Settings(_env_file=None)` or use the
  test settings fixture; never let a `.env` decide what a test asserts.
- **No module-level state.** If the code under test caches in a module global (pacing, DNS,
  the unpriced-model warning set), the test resets it first, so order cannot change the result.

### Before a test is done

1. Break the code on purpose, in the one line the test is for, and watch the test fail. If it
   stays green, the test is not finished. Restore the line.
2. Read each `assert` and ask what wrong implementation would still pass it. Tighten until the
   answer is "none that matters".
3. Check the name against the body.
4. Run the whole file, not only the new test: shared fixtures and module state make neighbours
   fail.

Delete a test rather than keep one that fails these checks. The audit's remove list in
`docs/testing-audit.md` is the model for what goes.
