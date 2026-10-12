# Public Atlas Testing Audit

2026-10-12

## Summary

The test suite is sound in its construction and thin where it matters most. Both suites pass
(659 pytest, 100 Vitest); tests run against a real database, a real browser and a scripted
model rather than mocks; and 14 of 19 non-equivalent injected faults were caught. Roughly three
quarters of the tests should stay as they are. About 25 should be deleted and about 60
tightened: they assert existence or positivity where a value is known, restate constants from
the module under test, snapshot the loader's own diagnostics, or carry a name that promises more
than the body checks.

Three problems outweigh the rest. First, the browser allowlist, the one piece of code that keeps
the agent on approved sites, let every injected fault through: a lookalike suffix, an unresolved
host and a `.localhost` subdomain all pass. Second, money and budgets are pinned by two non-zero
assertions in the whole suite, because the scripted model has no price. Third, a quarter of the
Python suite reads cached government files that CI never has, so those 125 tests skip on every
CI run and the green badge does not mean what it appears to mean.

Reading the code to judge the tests also surfaced four places where the documentation and the
implementation disagree (robots `Crawl-delay`, the redirect hop, the per-assignment search cap,
and the "one door" for status changes). None was executed here; each needs a confirming test
before it is called a bug. The additions in this report are ordered so that those, the boundary
and the money paths come first.

## Scope and method

Every test file in the repository was read against the source it covers, both suites were run,
and a sample of tests was checked with hand-made mutations. The repository is a pnpm and uv
monorepo: a Python server (`apps/server`) and a Next.js console (`apps/web`,
`packages/api-client`).

| Suite               | Source lines | Test lines | Test files | Tests                         | Fixtures                                                                                                                                               |
| ------------------- | ------------ | ---------- | ---------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Python (pytest)     | 35,983       | 20,569     | 110        | 659 collected (559 functions) | Real PostgreSQL in a rolled-back transaction, in-memory object store, parser and search, a scripted model in place of the LLM, a local fixture site for real Chromium |
| TypeScript (Vitest) | 24,410       | 1,560      | 22         | 100                           | None (pure functions and zod schemas only)                                                                                                             |

The review followed the framework in the report that prompted it. For each test the question
was what independently specified behaviour it pins down, which plausible fault it would catch,
and which would slip past. Six passes were made, one per area: the agent module; graph, review
and evidence; assignments and evals; the list loaders; infrastructure, integrations and
countries; and the web console. Static scans looked for assertion-free tests, `is not None`
assertions, skips, and mock use. Git history was searched for removed assertions and added
skips. A small set of mutation probes (one-line faults injected into the source, the relevant
tests re-run, the source restored) checked whether the suite notices the kinds of faults it
claims to guard against.

Two things are out of scope: the Docling parse tests, which need a dependency group not
installed here (CI runs them in a separate job), and a full mutation-testing run, which would
take hours against a database-backed suite.

## What is wrong today

The suite is in better shape than the failure modes in the prompting report would predict, and
its problems are concentrated rather than spread. All 659 Python tests and 100 Vitest tests
pass. Mocks are rare (23 lines in 6 files); tests run against a real PostgreSQL, a real Chromium
and a local fixture site, with in-memory ports only for storage, parsing, search and the model.
Of 21 hand-made faults, the suite caught 14, and 2 of the 7 survivors turned out to be
equivalent mutants (the mutated clause was redundant). The five real survivors all sit in two
places: the browser allowlist, which is the product's security boundary, and the eval scorer's
ratios.

### Mutation probes that survived

| Fault injected                                                                          | Where                                              | What it means                                                                               |
| --------------------------------------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Allowlist suffix match without the dot, so `evilontario.ca` passes for `ontario.ca`     | `integrations/browser/policy.py` `domain_matches`  | No test uses a confusable host. The classic allowlist bug is uncaught.                      |
| A host whose DNS lookup fails is allowed instead of refused                             | `policy.py` `resolve_host`                         | The fail-closed rule the docstring promises has no test.                                    |
| `foo.localhost` is no longer treated as loopback                                        | `policy.py` `is_blocked_address`                   | Only bare `localhost` is tested.                                                            |
| Recall with nothing labelled reads 0.0 instead of "no ratio"                            | `evals/scorer/tally.py`                            | A zero-denominator case nobody pinned; a gate would read a fail where there is no data.      |
| `same_site` returns true for two empty hosts                                            | `evals/scorer/rules.py`                            | A malformed URL in the dataset would match any other malformed URL.                         |
| IPv4-mapped IPv6 unwrapping removed; link-local clause removed                          | `policy.py`                                        | Equivalent mutants: Python already classifies these as non-global. Not a test weakness.     |

The 14 caught faults covered the quote check (short quotes, run-together text, `www.` handling,
empty names, page numbers), all three pricing formulas, all three lifecycle rules, and three of
five scorer rules. Those unit suites do their job.

### Weak or vacuous assertions

About 40 tests across the Python suite assert something that cannot fail or that fails to
distinguish the right answer from a wrong one. The recurring shapes:

- **Positive-number checks standing in for a value.** `budget_requests > 0`
  (`tests/integration/modules/assignments/test_runs.py:80`) is the only check that a per-type
  budget reaches the row; `len(goal) > 100`, `context_window >= 100_000`
  (`tests/unit/assignments/test_descriptors.py:30`); `tokens_used >= 1050`
  (`tests/integration/modules/agent/test_runner.py:155`).
- **Existence where identity is the point.** `found_on_webpage_id is not None` instead of the
  specific linking page (`test_findings_homepages.py:309`); `len(library_spawn) == 1` instead of
  the exact spawn (`graph/test_status_changes.py:102`); `source_id != uuid.UUID(int=0)`
  (`test_findings_sources.py:322`).
- **Quantifiers over empty sets.** `all(...)` over video rows when there may be none
  (`agent/test_purge.py:116`); `{e.kind for e in hits} <= {"hit"}` where hits is empty
  (`evals/test_harness.py:447`); a decoy row ("City of Pelee") whose match result is discarded
  before any assertion (`unit/evals/test_scorer.py:541`).
- **Tests whose name promises more than the body checks.** `test_stop_cancels_held_and_queued_work`
  never creates a queued row (`test_runs.py:238`); `test_a_stale_cache_is_fetched_again` only
  asserts the failure branch (`unit/imports/test_files.py:294`);
  `test_the_latest_snapshot_is_the_newest` has only one snapshot with text, so `.asc()` would
  pass (`evidence/test_service.py:203`); five `*_sits_at_a_place` tests check the level enum, not
  that the place exists (`unit/imports/lists/us/test_transit.py:104` and four siblings).
- **Tautologies.** Nineteen `test_the_counts` tests assert `len(module.entries(...)) == len(entries)`
  where both sides are the same `build()[0]` call (e.g.
  `unit/imports/lists/canada/alberta/test_places.py:61`). `malloc_trim(0) in (0, 1)` admits every
  return value (`unit/integrations/test_parse_docling.py:130`). `{KEY: r}[KEY] is r`
  (`integration/test_resources.py:78`).
- **Smoke tests with no assertion.** `test_ping_answers_when_the_store_is_reachable`
  (`integration/integrations/test_storage.py:152`); the in-memory `ping` is a bare `return`.

### Tests that mirror the implementation

- **Expected values read from the code under test.** `text.startswith(prompts.COMMON)`
  (`agent/test_briefing.py:52`); `confirm_attempts == MAX_CONFIRM_ATTEMPTS - 1` next to a
  hard-coded "attempt 1 of 3" (`test_findings_homepages.py:512`); `assert MIN_QUOTE_CHARS == 12`
  (`unit/evidence/test_quote_checks.py:20`); `RETRY_ON_ERROR.max_attempts == 5`
  (`integration/jobs/test_jobs.py:54`); `expected_source_types("hospital") == shared.CAMPUS_SOURCES`
  compares seed input to itself (`unit/countries/test_rules.py:33`); a descriptor test that
  restates the model and effort constants (`test_descriptors.py:66`).
- **Expectation built by the same comprehension as the input.** `types_not_found` in
  `agent/test_assignments.py:331`.
- **Three hand copies of the loader's own matching rules in test code**
  (`unit/imports/lists/canada/conftest.py:97`, `us/test_municipalities.py:210`,
  `quebec/test_places.py:313`) and two divergent copies of `_find_place`
  (`ontario/conftest.py:65`, `quebec/conftest.py:36`). When the loader's rule changes, the copies
  drift and the tests keep passing.
- **Golden snapshots of the loader's own diagnostics.** Dictionaries such as
  `("C1","A"): 14963` (`us/test_municipalities.py:87`) record what the parser emitted the day the
  test was written. They break on every legitimate fix and pass on every consistent bug.
- **A grep of the source text.** `test_the_one_door_does_write_statuses` asserts two substrings
  of `status_changes.py` (`unit/graph/test_status_writes.py:24`). Its sibling at line 13 is the
  real guard, but its regex misses `entity.status = other.status`, `.values(status=...)` and
  `setattr`.

### Redundant tests

- Twenty-four near-identical `every_entry_*` loops across the province and US list tests repeat
  the same six to eight assertions; five copies of the `open_sources` fixture and four of `rules`.
- Three end-to-end agent tests duplicate stronger findings tests:
  `agent/test_assignments.py:163` vs `test_findings_homepages.py:420`, `:199` vs `:485`, `:356`
  vs `test_findings_session.py:200`.
- Queue parsing is tested twice because it is implemented twice (`unit/test_worker.py:4`,
  `unit/test_cli.py:88`). `GET /health == 200` is asserted in three files.

### Fakes that stand in for the behaviour under test

- **One model for every choice.** `FixedModels` returns the same scripted model whatever is asked
  for, so no test can tell whether the handoff note was written by the cheap handoff model or
  the session's expensive one. The `choices` list built for exactly this purpose is asserted
  nowhere.
- **The scripted model has no price.** Every integration path that sums cost (run progress,
  assignment detail, eval run cost) is exercised only at zero. The whole suite has two non-zero
  money assertions (`unit/assignments/test_pricing.py:16`, `evals/test_harness.py:514`).
- **Inline jobs always succeed.** The inline connector asserts every job succeeded, so the retry
  path, the "last attempt" flag and the parse-wait deadline can never be observed.
- **Stalled-worker requeue is tested against procrastinate's in-memory connector**, never the
  SQL. The job that is "out of retries" gets there because its task is unregistered, not because
  attempts reached the limit.
- **The browser integration tests run with private-address blocking off**
  (`test_browser.py:27`), so the private-address and unresolved-host branches never run against
  a real browser.
- **Spawn dedup is proved through the pre-check, not the unique index** that guards two workers.
- The `finish_script` helper parses the refusal and supplies the missing types, so two runner
  tests would pass with the checklist check deleted.

### Tests that do not run

- **A quarter of the Python suite runs only on the owner's machine.** 125 list tests read cached
  copies of official files from `~/.cache/public-atlas/official-lists`. CI caches Playwright, uv
  and Docling models but never this directory, and there is no warm-up step. Every one of these
  tests calls `pytest.skip` when the cache is cold, and the only end-to-end Ontario load is
  `skipif` on the same condition (`test_load_list.py:1113`). Manual-export lists (territories,
  Saskatchewan, PEI, Alberta, Ontario health units, US transit) can never be fetched, and
  PDF-backed lists need Docling, which the main CI job lacks, while the parse job runs only tests
  marked `parse`, which these are not. The 659-pass count locally and a green CI are therefore
  not the same thing.

### Structural problems

- **Process-global state leaks between tests.** The "No price for model" warning is deduplicated
  by a module-level set, so `test_usage.py:66` passes or fails on test order. The pacing and DNS
  caches in the policy module are also module-level.
- **Tests read the developer's `.env`.** `Settings()` in `test_storage.py:146` and the `open_s3`
  helper pick up local configuration, so `bucket == "public-atlas"` tests the machine, not the
  code.
- **No mutation or coverage tooling** is configured for either language, so the gap between line
  coverage and fault detection is invisible.
- **The console has pure-function tests only.** 1,560 test lines against 24,400 source lines, no
  component, hook, server-action or route tests, and no testing-library or request-mocking
  dependency installed. Details in the web section below.

### The web console

The 100 Vitest tests are mostly sound: formatting expectations are hand-written and
locale-pinned, timezones are always passed explicitly, and the error-mapping and graph-data
tests pin real contracts. The problems are the same shapes as on the server, at smaller scale:

- **Rejection without a reason.** Eight schema tests assert only `success === false`
  (`features/runs/schemas.test.ts:50`, `review/schemas.test.ts:61`,
  `countries/schemas.test.ts:69`, `lib/validation.test.ts:26`), so a schema that rejects for the
  wrong reason passes.
- **Pass-through restated.** Most of the URL-parser tests enumerate fields flowing through zod
  (`assignments/schemas.test.ts:5`, `graph/schemas.test.ts:5`), while the real logic next to them
  (`assignmentFilters` forcing `order: "desc"` and letting a fixed run id beat the URL;
  `graphViewFilters` turning the domains overlay into a whole-web query) has no test.
- **A constant compared with itself.** `lists.test.ts:64` hard-codes the API's page limit of 500
  instead of reading it from the generated schema.
- **The API-client test checks the library, not the client.**
  `packages/api-client/src/index.test.ts` exercises openapi-fetch's error placement; the one-line
  `createApiClient` and the typed paths are not verified at runtime. The committed OpenAPI schema
  is kept in sync by `check:generated` in CI, which does fail on drift.
- **The URL-to-API layer and the action hooks are untested.** The two hooks that build mutation
  bodies and choose which queries to invalidate (`use-run-actions.tsx`,
  `use-review-actions.tsx`) have zero coverage, and one of them can post an empty `into_id` on a
  merge. No coverage provider is installed, so `vp test --coverage` fails.

### Claims in the README or docstrings the tests do not back

Reading the code to judge the tests surfaced four places where the documented behaviour and the
implemented behaviour differ. None was executed as part of this audit; each needs a confirming
test before it is treated as a bug.

1. **"Honours robots.txt"**: `Crawl-delay` is never read; pacing uses the fixed interval only
   (`policy.py:260`).
2. **"Only reaches approved domains"**: `test_browser.py:158` documents, without asserting, that
   Chromium loads a redirect hop off the allowlist and is bounced afterwards. Nothing asserts the
   off-list host was never requested in that path.
3. **Five searches per assignment**: the counter lives on the session context and resets per
   session (`modules/agent/context.py:102`), while the tool text promises per assignment.
4. **"Every status change goes through one door"**: `send_to_review` sets status without
   `_set_status` (`graph/status_changes.py:345`), so it is neither logged nor seen by the review
   preview; `reject_domain` leaves an already-verified homepage verified on the rejected domain
   (`status_changes.py:124`); verification functions have no evidence precondition, so review
   approval and imports can verify an entity with zero evidence rows.

## Tests to remove or rewrite

About 25 tests should go and about 60 should be tightened; the rest of the suite (roughly 75
percent) stands as it is. Paths are relative to `apps/server/tests/` unless they start with
`apps/web` or `packages`.

### Remove

| Test                                                                                                                | Why                                                                                              |
| ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `unit/graph/test_status_writes.py:24` `test_the_one_door_does_write_statuses`                                       | Asserts two substrings of the source file.                                                       |
| `unit/agent/test_events.py:82` `test_a_video_event_carries_its_storage_key`                                         | Restates the constructor field by field; the purge test covers the event.                        |
| `integration/modules/agent/test_assignments.py:356`                                                                 | Duplicate of `test_findings_session.py:200`, which asserts the exact summary and review question. |
| `unit/assignments/test_pricing.py:9` `test_the_price_list_is_a_data_file`                                           | Reads `prices.toml` back; line 27 already prices a search.                                       |
| `unit/assignments/test_descriptors.py:66`                                                                           | Restates the model and effort constants; catches a typo, not a wrong decision.                   |
| `unit/assignments/test_lifecycle.py:48` and `:81`                                                                   | Subsumed by the full transition table proposed below.                                            |
| `unit/evals/test_dataset.py:47` `test_parent_labels_replace_relationships`                                          | Re-implements the validator; implied by `validate_files(...) == []` at line 22.                  |
| `unit/countries/test_seeds.py:123`                                                                                  | `name_pattern is not None`; `test_rules.py:49` covers the regex.                                 |
| `unit/integrations/test_parse_docling.py:130` `test_freed_memory_is_handed_back`                                    | `malloc_trim(0) in (0, 1)` admits every return value.                                            |
| `integration/test_resources.py:78` `test_a_worker_context_carries_the_resources`                                    | `{KEY: r}[KEY] is r`.                                                                            |
| `integration/integrations/test_storage.py:152`, memory parameter                                                    | No assertion and the fake's `ping` is a bare return. Keep the S3 case and add the negative.       |
| `unit/test_worker.py:4` or `unit/test_cli.py:88`                                                                    | Queue parsing is implemented twice; dedupe the source, keep one test.                            |
| The `len(module.entries(...)) == len(entries)` line in all 19 `test_the_counts`                                     | Both sides are the same `build()[0]` call; it also rebuilds a 38,000-entry list.                 |
| `unit/imports/lists/canada/ontario/test_places.py:23-36` fixtures; the five copies of `open_sources` and four of `rules` | Already defined in the conftests.                                                            |
| `unit/imports/test_lists.py:63-80`                                                                                  | Recomputes the manifest from the same list it checks; keep lines 82-100.                         |
| `integration/modules/graph/test_api.py:248`                                                                         | Re-tests `reject_institution`; fold the `status=rejected` line into line 69.                     |
| `integration/modules/health/test_health.py:11` `GET /health == 200`                                                 | Asserted in three files; keep the one that checks the body.                                      |
| `apps/web/src/features/runs/schemas.test.ts:53-55`                                                                  | Restates `listSearch`, pinned in `lib/lists.test.ts:26-36`.                                      |
| `apps/web/src/features/graph/schemas.test.ts` page, sort and order lines                                            | Duplicate `lib/lists.test.ts`.                                                                   |
| `apps/web/src/lib/page-titles.test.ts:5-19`                                                                         | Implied by the `titleFor` cases at lines 21-34.                                                  |
| `apps/web/src/lib/validation.test.ts:46-53`                                                                         | Same Belgrade input as `dates.test.ts:14`.                                                       |
| `apps/web/src/lib/api/errors.test.ts:82` dynamic import                                                             | The module is already imported at line 3.                                                        |

### Rewrite

| Test                                                                                                                                                     | Change                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `integration/modules/assignments/test_runs.py:80`                                                                                                        | Assert each row's `budget_requests` and `budget_tokens` equal its type's descriptor, not `> 0`.                                                                                             |
| `test_runs.py:238` stop test                                                                                                                             | Release one row and start one through `lifecycle.start`; assert held and queued are cancelled and running survives.                                                                         |
| `test_runs.py:327`, `:347`                                                                                                                               | Record a priced usage row on the released assignment; assert `progress.cost` and the detail's `cost` equal it.                                                                              |
| `test_runs.py:466`                                                                                                                                       | Three cases: raising run live; raising run stopped but a newer country run live; nothing live.                                                                                              |
| `test_usage.py:66`                                                                                                                                       | Drop the `caplog` line or reset the module-level `_unpriced` set first.                                                                                                                     |
| `unit/assignments/test_descriptors.py:30`                                                                                                                | Keep the tool-subset and finishing-tool invariants; delete the numeric floors.                                                                                                              |
| `unit/assignments/test_lifecycle.py`                                                                                                                     | One parametrized test over all 25 (from, to) pairs with the allowed set spelled out; add `finish(summary=None)` keeps the old summary.                                                      |
| `unit/evals/test_scorer.py:348`, `:541`                                                                                                                  | Add an `expected: review` case with a verified row; give "City of Pelee" a homepage or assert `match_municipality(...) is None` directly.                                                   |
| `integration/modules/evals/test_harness.py:447`, `:503`, `:541`                                                                                          | Assert on a measure with a hit; add a third run and assert `previous_id` skips the unfinished one; pass real assignment ids with a child to `cost_by_subject`.                                |
| `integration/modules/agent/test_findings_sources.py:322-329`                                                                                             | Drop the `UUID(int=0)` and `is_domain_name` lines; keep the owner check.                                                                                                                    |
| `agent/test_purge.py:116`                                                                                                                                | Assert the recent video row's content is `{"key": recent_key, "size": 4}`.                                                                                                                  |
| `agent/test_runner.py:155`, `:355`                                                                                                                       | Give every scripted response explicit `usage` and assert the exact sum; `pytest.raises(..., match=)` and exact `last_error`.                                                                |
| `agent/test_runner.py:53`, `:217`, `:388` handoff tests                                                                                                  | Add a case at exactly half the context window that must not hand off.                                                                                                                       |
| `agent/test_findings_homepages.py:309`, `:512`, `:777`                                                                                                   | Assert the `/milton` page's id; use the literal 2; assert per claim which was rejected (with reason) and which verified.                                                                     |
| `agent/test_assignments.py:184`, `:219`, `:331`, `:371`                                                                                                  | Replace `summary.startswith` with the state the summary describes; assert the literal six-type list.                                                                                        |
| `agent/test_findings_session.py:98`                                                                                                                      | Assert the "Pages opened" block; add a candidate and a handoff-note case.                                                                                                                    |
| `agent/test_briefing.py:45-62`                                                                                                                           | Keep one level line and one platform line; drop `startswith(prompts.COMMON)`.                                                                                                               |
| `unit/graph/test_status_writes.py:13`                                                                                                                    | Match `\.status\s*=` with any right-hand side and `values(... status=`; allowlist the door.                                                                                                 |
| `integration/modules/graph/test_status_changes.py:102`, `:106`, `:190`, `:450`                                                                           | `== [Spawn(FIND_SOURCES, library.id)]`; return all three statuses and `town.homepage_id`; keep `subject_id`; `match=` plus both entities' full attachment sets unchanged.                    |
| `integration/modules/evidence/test_service.py:203`                                                                                                       | Two READY snapshots so the ordering is exercised.                                                                                                                                           |
| `evidence/test_jobs.py:187`                                                                                                                              | Assert `(FAILED, startswith("scan.pdf:"))`, not the fake parser's wording.                                                                                                                  |
| `integration/modules/review/test_review.py:543`                                                                                                          | Exact rows instead of `len == 2`.                                                                                                                                                           |
| `unit/evidence/test_files.py:18`; `test_quote_checks.py:20`                                                                                              | Assert on `two.body`; drop the `MIN_QUOTE_CHARS == 12` line.                                                                                                                                |
| `unit/integrations/test_browser_fetch.py:34`, `:75`                                                                                                      | Make them `async` tests with the anyio plugin and inline the helpers.                                                                                                                       |
| `integration/integrations/test_storage.py:146`, `open_s3`                                                                                                | `Settings(_env_file=None)`; add `ping` on a missing bucket raising `ClientError`.                                                                                                            |
| `integration/jobs/test_jobs.py:54`, `:109`, `:148`                                                                                                       | Assert each task's queue; register a retrying test task and probe attempts 4 vs 5 and heartbeat 29 s vs 31 s; add a 6-day-old job that survives the 7-day purge.                             |
| `unit/test_openapi.py:6`; `integration/db/test_db.py:26`                                                                                                 | Compare schema paths with the app's routes; assert the body and the 422 for `X-Database: eval` without an eval database.                                                                    |
| `unit/countries/test_naming.py:33`; `test_rules.py:33`                                                                                                   | Assert the exact designator group; spell the hospital checklist out.                                                                                                                        |
| `unit/integrations/test_parse_docling.py:51`; `test_parse.py:54`                                                                                         | Fold into the OCR test; either assert `docling` is absent from `sys.modules` in a subprocess or rename.                                                                                     |
| `unit/imports/lists/us/test_transit.py:104` and the four other `*_sits_at_a_place`                                                                       | Resolve `(place, place_level, place_parent)` against the loaded places lists, as `test_government_units.py:79` does.                                                                        |
| `unit/imports/lists/us/test_special_districts.py:152`                                                                                                    | Exact under-state counts per state and one named Connecticut district's place.                                                                                                              |
| `british_columbia/test_places.py:138`, `ontario/test_conservation_authorities.py:100`, `ontario/test_fippa_bodies.py:134`                                | Assert the overridden field equals the override value, as `ontario/test_places.py:153` does.                                                                                                |
| `unit/imports/test_files.py:294`                                                                                                                         | Serve bytes from the fixture site; test the refetch-on-match and refuse-on-hash-mismatch branches.                                                                                          |
| `unit/imports/test_lists.py:39`                                                                                                                          | Pin `set(LISTS)` to the 28 names.                                                                                                                                                           |
| `integration/modules/imports/test_load_list.py:1113`                                                                                                     | Assert Kitchener's parent is the Waterloo region row and Kingston's is Ontario; make it run in CI (see next steps).                                                                          |
| The three copies of the loader's matching rules and two of `_find_place` in the list conftests                                                           | Call the loader's own methods, or replace with one integration load per list asserting `report.skipped == []`.                                                                              |
| The golden `notes` dictionaries (`us/test_municipalities.py:84`, `test_states_counties.py:61`, `test_government_units.py:24`)                             | Keep headline totals; mark the rest as snapshots or drop.                                                                                                                                   |
| The 24 `every_entry_*` loops                                                                                                                             | One parametrized contract test over `LISTS.values()`, with per-list exceptions as a small dict; each province keeps `test_the_counts` and `*_that_show_the_rules`.                           |
| `apps/web` schema tests asserting only `success === false` (`runs/schemas.test.ts:50`, `review/schemas.test.ts:61`, `countries/schemas.test.ts:69`, `lib/validation.test.ts:26`) | Assert `issues[0].path` or message; add the `limit: "501"` and non-uuid cases and the `note: "" -> null` happy path.                                                         |
| `apps/web/src/lib/lists.test.ts:64`                                                                                                                      | Read the page limit from the generated schema instead of hard-coding 500.                                                                                                                   |
| `packages/api-client/src/index.test.ts`                                                                                                                  | A type-level drift guard (`expectTypeOf`) that a required body field such as `into_id` is required.                                                                                         |
| `apps/web/src/lib/api/database.test.ts:18`; `errors.test.ts:66`                                                                                          | `toBe` the full cookie string; add the `statusText` fallback case.                                                                                                                          |
| `apps/web/src/features/graph/graph-data.test.ts:120`, `:141`                                                                                             | Pin the size constants; assert the exact truncated string with its ellipsis.                                                                                                                |
| `apps/web/src/features/assignments/schemas.test.ts`                                                                                                      | Replace the pass-through enumeration with tests of `assignmentFilters`.                                                                                                                     |

## Tests to add

The missing tests matter more than the weak ones. Each row names the behaviour as an independent
specification, not as a description of the code, so the test can be written from the row alone
and would fail if the implementation were wrong. Ranked by what a fault would cost: the agent
reaching a host it must not, money miscounted, the trust chain broken, data silently wrong in
the graph, work lost or duplicated, measurements wrong, console actions sending the wrong
request.

### 1. The browser boundary (`integrations/browser/`)

| Behaviour to assert                                                                                                                                                              | Proposed test                                            |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| A host that merely ends in an allowed domain's letters (`evilontario.ca`, `notontario.ca`) is refused; `www.ontario.ca` and `a.b.ontario.ca` pass.                               | `test_a_lookalike_suffix_is_not_a_subdomain`             |
| A host whose lookup times out or fails is refused with the unresolved reason, never allowed.                                                                                     | `test_a_name_that_does_not_resolve_is_refused`           |
| `::1`, `fe80::1`, `fc00::1`, `::ffff:127.0.0.1`, `http://[::1]:8000/` and `foo.localhost` are all refused, including when the allowlist names them.                              | `test_ipv6_and_dot_localhost_addresses_are_refused`      |
| A second decision within 30 seconds reuses the first lookup; after the TTL the name is resolved again.                                                                           | `test_resolution_is_cached_for_the_ttl_then_asked_again` |
| A Chromium redirect from an allowed page to an off-list host never issues a request to that host, and the object store holds nothing from it. Today's test documents the hop without asserting it. | `test_a_redirect_off_the_allowlist_is_never_requested` |
| An image, frame or fetch inside an allowed page cannot reach a private address.                                                                                                  | `test_page_assets_and_frames_cannot_reach_private_addresses` |
| A WebSocket to an off-list host is closed; one to an allowed host connects.                                                                                                      | `test_a_websocket_is_bounded_by_the_allowlist`           |
| Popups beyond the tab limit are closed; selecting a tab re-checks its URL and bounces one that drifted off-list.                                                                 | `test_a_popup_past_the_tab_limit_is_closed`              |
| Two policy instances on one host take consecutive pacing slots.                                                                                                                  | `test_two_sessions_on_one_host_take_consecutive_slots`   |
| `Crawl-delay` in robots.txt slows the host (after deciding whether to implement it); a robots 5xx is treated the chosen way.                                                     | `test_a_crawl_delay_slows_the_host`                      |
| A backslash URL and a userinfo URL (`https://ontario.ca@evil.example/`) are hostless or refused.                                                                                 | `test_hosts_are_read_as_chromium_reads_them`             |
| The production wiring sets private-address blocking on, in both places a policy is built (`runner.py`, `agent/context.py`).                                                     | `test_create_browser_blocks_private_addresses_by_default` |
| `read_file` refuses a body over the size cap by `Content-Length` and by streamed length, storing nothing.                                                                        | `test_a_file_over_the_cap_is_refused_and_not_stored`     |

### 2. Money and budgets (`modules/assignments/`)

| Behaviour to assert                                                                                                                                                              | Proposed test                                                                          |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| All-cached input is charged at the cached price only; cached plus output exceeding the total clamps uncached to zero; zero units cost zero. Build `Prices` by hand so the test is independent of `prices.toml`. | `test_cached_tokens_are_never_charged_twice`                             |
| A seven-token call is stored at the column precision the owner chooses, and 1,000 such rows sum to the expected total.                                                           | `test_small_calls_round_to_the_column_precision`                                       |
| Two runs with usage keep separate costs; `by_result` omits nulls; an empty run reads zero.                                                                                       | `test_progress_sums_each_runs_cost_alone`                                              |
| An assignment's detail `cost` equals the sum of its usage rows; an eval run's `cost` equals the sum of its cost lines.                                                            | `test_an_assignments_detail_carries_its_cost`, `test_an_eval_run_records_its_dollar_cost` |
| With requests left but tokens spent, the session ends out of budget before any request; crossing the token limit mid-session ends the same way.                                  | `test_a_spent_token_budget_ends_the_assignment_out_of_budget`                          |
| The session asks for the type's model and the handoff asks for the handoff model (assert on `FixedModels.choices`).                                                              | `test_handoff_notes_are_written_by_the_cheap_model`                                    |
| A `find_homepage` assignment gets five searches across all its sessions, not five per session. Likely fails today.                                                               | `test_searches_are_capped_across_sessions_of_an_assignment`                            |
| A fourth search domain is dropped and a single domain renders as `query site:x`.                                                                                                 | `test_search_takes_at_most_three_domains`                                              |

### 3. The trust chain and the evidence invariant (`modules/graph/`, `modules/review/`, `modules/evidence/`)

| Behaviour to assert                                                                                                                                                                                      | Proposed test                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Rejecting a domain that carries a verified homepage either rejects that homepage and clears the institution's link, or the owner pins the opposite.                                                      | `test_rejecting_a_domain_with_a_verified_homepage_on_it`                                                                                                           |
| Rejecting the institution's verified homepage clears `homepage_id`, records the reason and spawns a new search.                                                                                          | `test_rejecting_the_verified_homepage_clears_the_link_and_looks_again`                                                                                             |
| Sending an entity to review is recorded like every other status change (logged, visible to the preview).                                                                                                | `test_sending_to_review_is_recorded_like_any_change`                                                                                                               |
| An entity cannot be verified with zero evidence rows, or the owner pins that review approval and imports may.                                                                                            | `test_verification_requires_evidence_or_a_reviewer`                                                                                                                |
| A quote matches words, not letters run together across boundaries: "publicity of a jaxon" does not contain "City of Ajax".                                                                               | `test_a_run_together_match_still_respects_words`                                                                                                                   |
| An `href` inside a script, a comment or visible text is not a link; a frame's link text is linkable but not quotable as page text.                                                                       | `test_a_link_in_a_script_or_comment_is_not_a_link`, `test_frame_links_are_linkable_but_not_quotable`                                                               |
| Merging closes every open review item on the duplicate with `merged_into_id`; merging a parent into its own child reparents rather than cycling; a duplicate's code in a scheme the survivor already has stays put. | `test_merging_closes_every_open_item_on_the_duplicate`, `test_merging_a_parent_into_its_child_reparents_the_child`, `test_merge_keeps_the_survivors_code_in_a_scheme` |
| Rejecting a place is refused while anything sits under it; `verify_source` and `reject_source` record who did it.                                                                                        | `test_rejecting_a_place_is_refused_while_anything_sits_under_it`                                                                                                   |
| Deciding a subset of a kind's items leaves the rest open; a second kind on an existing item does not overwrite the first.                                                                                | `test_a_kind_is_decided_for_the_items_the_reviewer_saw`, `test_a_second_kind_does_not_overwrite_the_first`                                                         |
| A blocked browser redirect records `redirects_to_url` on the requested page; a failed or HTML snapshot is never reused by `read_file`; a pruned quote has no link and a hidden quote gets its context from stored HTML. | `test_a_blocked_redirect_is_on_record`, `test_a_failed_or_html_snapshot_is_never_reused`, `test_a_pruned_quote_has_no_link`                                 |
| `_ancestors` stops at a parent cycle; redirect chains stop at five hops; a name just under the similarity floor is not offered; an alias the owner has is not added twice.                                | `test_ancestors_stop_at_a_cycle`, `test_redirect_chains_stop_at_five_hops`, `test_similar_places_respects_the_floor`                                               |

### 4. The agent's findings and runner (`modules/agent/`)

| Behaviour to assert                                                                                                                                                                                                                                      | Proposed test                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `confirm_domain` on another institution's verified homepage goes to review at once; LINKS_TO evidence whose cited copy lacks the link sends the domain to review; a claim found on an untrusted page fails with that reason.                             | `test_confirm_domain_refuses_a_page_that_is_anothers_verified_homepage` and two siblings |
| `domain_moved` to a platform, a rejected domain, a domain in review, and another's verified homepage each end as specified.                                                                                                                              | `test_domain_moved_to_a_platform_or_a_decided_domain`                                   |
| `save_homepage` refuses a rejected domain, waits on one in review, refuses another's verified page.                                                                                                                                                      | `test_save_homepage_refuses_a_rejected_domain_and_waits_on_a_reviewed_one`              |
| A reviewed source is verified when the trusted link arrives; re-saving without it opens no second review item; a platform page linked only from a platform goes to review.                                                                               | `test_a_reviewed_source_is_verified_when_the_trusted_link_arrives`                      |
| A model that answers in text ends the session and the next session starts with the old handoff note; a missing or wrong-kind subject ends failed without raising; a re-delivered job for a finished assignment runs no session; a crash before the claim on the last attempt ends failed and prunes uncited pages. | `test_a_text_answer_starts_another_session_with_the_old_note` and three siblings |
| A failed handoff model falls back; thinking parts are stripped from the history sent to it.                                                                                                                                                              | `test_a_failed_handoff_falls_back_and_reasoning_is_stripped`                            |
| A run paused between sessions re-queues a running assignment.                                                                                                                                                                                            | `test_a_run_paused_between_sessions_requeues_the_running_assignment`                    |
| A store failure during purge leaves the row rewritten and the other keys deleted.                                                                                                                                                                        | `test_a_purge_survives_a_store_failure`                                                 |

### 5. The list loader (`modules/imports/`)

| Behaviour to assert                                                                                                                                                                                     | Proposed test                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| A list place matching an agent-entered candidate is adopted with verified identifiers and either verified or reported, never left silent.                                                               | `test_a_list_place_matching_an_agents_candidate_is_verified_or_reported`     |
| A place matched by code whose parent changed is moved and reported; a re-coded place has its identifier changed and reported.                                                                           | `test_a_place_whose_parent_changes_is_moved_and_reported`                    |
| An exception on entry three of four under `--apply` commits nothing and writes no half report.                                                                                                          | `test_an_error_midway_writes_nothing`                                        |
| A download whose hash differs from the pin is refused and the cache untouched.                                                                                                                          | `test_a_download_whose_hash_differs_is_refused_and_not_cached`               |
| A list homepage does not displace an agent-verified one; a dissolved override on a loaded place reports it as no longer listed; a renamed place keeps its code and gains the new name as an alias.      | three tests                                                                  |
| A citation to an unlisted source or a line past the file's end is skipped with a reason; a place without a parent below the top level is skipped.                                                       | `test_an_entry_citing_a_line_the_file_lacks_is_skipped`                      |
| A ragged CSV row is padded or refused, never silently truncated; undecodable bytes raise the list-file error; float, date and bool cells render predictably; trailing empty spreadsheet rows are handled one chosen way. | four small `test_files.py` tests                                   |
| Two workers spawning the same assignment at once create one row (the unique index path, with `_open` disabled).                                                                                         | `test_two_workers_asking_at_once_create_one_assignment`                      |

### 6. Jobs, config and schema

| Behaviour to assert                                                                                                                                                                                                                      | Proposed test                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Stalled-worker requeue against the real queue schema: a worker row with a heartbeat 31 s old has its job retried, 29 s old is left alone; attempts 4 of 5 retried, 5 of 5 failed and the abandoned hook settles the assignment as failed. | `test_retry_stalled_against_the_real_queue_schema`, `test_a_dead_workers_assignment_ends_failed` |
| The last attempt knows it is last; `max_attempts=None` always retries.                                                                                                                                                                   | `test_retries_left_boundaries`                                                                   |
| Mixed queues give parse concurrency 1.                                                                                                                                                                                                   | extend `test_worker.py:9`                                                                        |
| The initial migration lists every procrastinate object the installed version creates.                                                                                                                                                    | `test_the_initial_migration_lists_every_procrastinate_object`                                    |
| Settings read the `PUBLIC_ATLAS_` prefix; an empty variable reads as the default; out-of-range and unknown-provider values are rejected.                                                                                                 | `test_settings_read_the_prefixed_environment`                                                    |
| `/health/db` is 503 when the session raises; `X-Database: eval` is 422 without an eval database.                                                                                                                                         | `test_a_dead_database_is_a_503`                                                                  |
| The six assignment results split into settling and non-settling; `queue_spawns` never makes a second job; `release` by id and oldest-first; run pause, resume and stop as a transition table; `would_spawn` names every skip reason; a failed finish spawns nothing. | six small `test_runs.py` tests                                                |

### 7. The scorer and the dataset (`modules/evals/`)

| Behaviour to assert                                                                                                                                                                                                                  | Proposed test                                                                                       |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| Recall and precision are "no ratio" at a zero denominator; `judged` excludes unlabelled and off-list rows; a gate passes at exactly its floor and reads "-" with nothing judged. No gate passes in any test today.                   | `test_a_tally_with_nothing_judged_has_no_ratio`, `test_a_gate_passes_at_its_floor`                 |
| `same_site` is false for empty hosts; `find_domain` prefers the longest related row and casefolds.                                                                                                                                   | `test_same_site_needs_two_hosts`, `test_find_domain_prefers_the_longest_related_row`                |
| Several name matches prefer type, then place; a trap is caught by its URL; an unsurfaced "confirm" domain is a miss; the parent-not-found, wrong-parent, homepage-for-none, saved-instead and rejected-source branches each produce their line. | `test_several_name_matches_prefer_type_then_place` and a parametrized `test_subject_branches` |
| A municipality is matched under its parent when two share a name; differing designators do not match.                                                                                                                                | `test_a_municipality_is_matched_under_its_parent`                                                   |
| Each dataset validator rule fires on one bad file (about 20 rules; two have a failing case today), and the places validator's tier, count and homepage rules fire.                                                                   | `test_each_validator_rule_fires`                                                                    |
| Evidence text normalization handles quotes, dashes, non-breaking spaces and punctuation spacing.                                                                                                                                     | `test_evidence_text_normalizes_quotes_and_spacing`                                                  |
| A mixed-country dataset is refused; scoring the eval database completes an unfinished run.                                                                                                                                           | `test_a_run_works_one_country`                                                                      |

### 8. The console (`apps/web/`)

Most of these are pure or extractable and need only Vitest. Only the two hooks need
`@testing-library/react` with `msw` or a mocked mutations module.

| Behaviour to assert                                                                                                                                                         | Proposed test                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| A release sends `assignment_type: null` for "any", singular and plural toasts, and invalidates both run and assignment queries.                                             | `use-run-actions` hook test                            |
| A merge never posts an empty `into_id`; approve sends `institution_type: null` when blank; the spawn summary counts by type; the four key families are invalidated.         | `use-review-actions` hook test, `spawnSummary` unit test |
| The domains overlay asks for the whole web with platforms; hierarchy asks for governments and both kinds.                                                                   | `graphViewFilters` test                                |
| A run page's fixed run id beats the URL; `sort` is stripped and `order` forced to descending; fixed table filters win and page 2 is offset 50.                               | `assignmentFilters`, `institutionTableFilters` tests   |
| A filter change returns to page 1 but keeps the sort; the default sort is stored as absent.                                                                                 | `use-list-state` test                                  |
| Saved lists are kept per database, keep array identity while unchanged, and read as empty when storage is blocked.                                                          | `saved-lists/store` test under jsdom                   |
| A 404 renders not-found and other errors rethrow; the browser client sends the cookie's database header.                                                                    | `unwrapOrNotFound`, `client.ts` tests                  |
| A stopped run offers no actions; Release is disabled at zero held; an emptied last page keeps a way back; a zero budget reads 0 percent.                                    | small component or extracted-helper tests              |
| The untested branches of `review/question.ts`, `review/effects.ts` and `evals/scores.ts` (new type, domain moved, platform homepage, out of scope, run stopped, first gate wins, lowest recall null). | plain Vitest                                 |
| One Playwright smoke that loads `/runs`, `/review` and `/institutions?page=2` against the server and opens a release dialog. CI already has Chromium and PostgreSQL.         | `smoke.spec.ts`                                        |

## Recommended next steps

Do the work in this order; the first three items buy the most safety per hour.

1. **Make the suite run in CI, not only on one machine.** Add an `actions/cache` step for
   `~/.cache/public-atlas/official-lists` keyed on a hash of the `sha256` pins under `lists/`,
   with a `lists fetch` warm-up command; store the manual exports where CI can read them; add a
   `lists` marker and a `PUBLIC_ATLAS_REQUIRE_LISTS=1` switch that turns the conftest skips into
   failures in CI; mark the PDF-backed list tests `parse` so the parse job runs them. Until this
   is done, 125 tests and the only end-to-end Ontario load are green by omission.
2. **Close the browser-boundary gaps** (section 1 of the additions): the lookalike suffix, the
   unresolved host, IPv6 and `.localhost`, the redirect hop, and the production wiring. Decide
   whether `Crawl-delay` is implemented or the README is amended. These are the five-minute
   tests with the largest consequence.
3. **Give the scripted model a price in the fixtures** and add the money and budget tests
   (section 2). Add the per-assignment search cap test and fix whichever side is wrong.
4. **Pin the trust chain** (section 3): the four README-versus-code discrepancies each need one
   test that states the intended rule, then a fix where the code disagrees.
5. **Clean up**: apply the remove list, then the rewrite list, starting with the lifecycle
   transition table, the stop test, and the list-loader contract test that replaces the 24
   loops.
6. **Write the rules down for the agents that write the tests.** A short testing section in
   `AGENTS.md`: expected values are written by hand, never imported from the module under test;
   no `is not None`, `> 0` or `len > 0` where a value is known; every `pytest.raises` carries
   `match`; every skip has a CI job that runs the test; a test named for a behaviour asserts
   that behaviour; one scenario per test with the full end state asserted.
7. **Console**: the pure-helper tests in section 8 first (no new dependencies), then
   `@testing-library/react` and `msw` for the two action hooks, then one Playwright smoke in the
   existing CI job.

## Appendix: the mutation probe script

The probes were run with a throwaway script that, for each entry, replaces one exact string in a
source file, runs the named test paths with `uv run pytest -q -x`, and restores the file with
`git checkout`. The 21 probes and their outcomes:

| Probe                                                                 | Tests run                        | Outcome              |
| --------------------------------------------------------------------- | -------------------------------- | -------------------- |
| Q1 `MIN_QUOTE_CHARS` 12 to 1                                          | `unit/evidence`                  | killed               |
| Q2 whitespace-squash fallback removed from `_contains`                | `unit/evidence`                  | killed               |
| Q3 `same_address` no longer strips `www.`                             | `unit/evidence`                  | killed               |
| Q4 `mentions_any` accepts an empty name                               | `unit/evidence`                  | killed               |
| Q5 `find_quote` reports page 1 for every multi-page hit               | `unit/evidence`                  | killed               |
| P1 output tokens also charged as input                                | `unit/assignments/test_pricing`  | killed               |
| P2 cached input charged at the full price                             | `unit/assignments/test_pricing`  | killed               |
| P3 search priced per call, not per unit                               | `unit/assignments/test_pricing`  | killed               |
| L1 a result may accompany any status                                  | `unit/assignments/test_lifecycle`| killed               |
| L2 finished may go back to queued                                     | `unit/assignments/test_lifecycle`| killed               |
| L3 `started_at` overwritten on every start                            | `unit/assignments/test_lifecycle`| killed               |
| B1 allowlist suffix match without the dot                             | `unit/integrations` browser tests| **survived**         |
| B2 IPv4-mapped IPv6 not unwrapped                                     | `unit/integrations/test_browser_policy` | survived (equivalent) |
| B3 link-local clause removed                                          | `unit/integrations/test_browser_policy` | survived (equivalent) |
| B4 `.localhost` subdomains allowed                                    | `unit/integrations/test_browser_policy` | **survived**  |
| B5 unresolved host passes instead of refusing                         | `unit/integrations/test_browser_policy` | **survived**  |
| S1 recall at zero denominator reads 0.0                               | `unit/evals`                     | **survived**         |
| S2 precision divides by hits plus misses                              | `unit/evals`                     | killed               |
| S3 "wrong" no longer counts as a false positive                       | `unit/evals`                     | killed               |
| S4 homepage path prefix without the slash                             | `unit/evals`                     | killed               |
| S5 `same_site` true for empty hosts                                   | `unit/evals`                     | **survived**         |
