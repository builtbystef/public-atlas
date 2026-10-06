# Public Atlas: build order

Everything from an empty folder to a recorded demo and a submitted
application, in order. Each phase ends with what says it is done. The design
is `product-and-tech-spec.md`. Code to port lives in
`../archived-public-atlas-v1` (v1 below); the base template is
`~/Code/personal/alloy`.

## Phase 0: scaffold

- [ ] Copy current alloy into this folder, rename to `public_atlas` and `@public-atlas/*`.
- [ ] In the first commit delete auth, workspaces, mail, rate limits and the CRM, on both server and web. Delete the web proxy route and replace it with a `rewrites` rule in `next.config.ts`.
- [ ] Add `resources.py` with `build_resources(settings)` and make `main.py`, the worker and the test fixtures call it. Remove every import-time `get_settings()` and the module-level job app.
- [ ] Set up compose with PostgreSQL and RustFS, the three server image targets (`server`, `agent`, `parse`) and CI, copied from v1 and trimmed.
- [ ] Write `README.md` from the spec's sections 1 and 12, and `apps/server/.env.example`.
- [ ] Add a `docs/glossary.md` link to the spec's section 13 and keep it in `CLAUDE.md` so coding agents follow the naming rules.

**Done when** `vp run check` and `vp run test` pass on an app with only a health route, and a test can build resources against the test database without touching environment variables.

## Phase 1: schema and seeds

- [ ] Write the models from spec section 4: the `entities` parent with joined-table inheritance for places, institutions, sources, domains and homepages; aliases, identifiers and metrics with the two-column link and check constraint; `institution_served_places`; webpages, snapshots, evidence, blocked attempts; the setup tables; runs, assignments, review items, usage, agent run events, eval runs and scores.
- [ ] Checked strings generated from each `StrEnum`, with a test that compares the constraints with the enums.
- [ ] One initial Alembic migration. Partial unique index on assignments per subject and type while open. Trigram index on aliases.
- [ ] The five setup tables from spec section 4.4: `country_settings`, `administrative_levels`, `institution_types`, `source_types`, `country_institution_types`, with type names as primary keys and the two checklists as text arrays validated by the API.
- [ ] Turn v1's `data/shared` and `data/canada` YAML into Python seed modules, `setup/seeds/shared.py` (global types, default expected sources) and `setup/seeds/canada.py` (settings and naming rules, levels with expected types, Canada's type rows, platforms, and the Ontario anchor as verified place, government and domains). Validated by the setup API's Pydantic models. No YAML.
- [ ] `public-atlas seed canada`: idempotent, adds what is missing, never deletes.
- [ ] The `CountryRules` object built from the setup tables at the start of each assignment, so an edit takes effect on the next one: levels and ranks, expected types per level, expected sources per type for this country, naming forms, platforms.
- [ ] The shared list loader in `imports/`: download and hash-check with a local cache, one text renderer per format (CSV and spreadsheet, JSON, HTML, PDF, ZIP member), store each source as a snapshot and an `official_lists` row, diff against the database, apply `PlaceEntry` and `InstitutionEntry` records with their citations as evidence. Idempotent by code then name under the same parent.
- [ ] The entry models: `PlaceEntry`, `InstitutionEntry`, `Citation`, in memory only.
- [ ] `imports/lists/ontario_places.py`: port v1's `generate.py` and `statcan.py` into `SOURCES` (census population table, census geography file, Ontario directory page), `OVERRIDES` and `entries()`. No generated files.
- [ ] `public-atlas load-list <name>`: prints the diff, applies with `--apply`.
- [ ] Port the rule test to call `entries()` on the cached files.
- [ ] Setup API: list and edit country settings, administrative levels and their expected types, institution types, source types, and a country's type rows with their expected sources, with validation of every array against the type tables.

**Done when** seeding and loading Ontario produces 40 regions, 414 municipalities and 444 governments with codes and populations, a rerun changes nothing, and the rule test passes.

## Phase 2: port the stable pieces

- [ ] Storage port (S3, memory) from v1; add an R2 configuration note.
- [ ] Search port (Brave, memory) from v1, one request per call.
- [ ] Parse port (Docling, memory) and the parse worker with its page ranges, memory trim, retire threshold and retry-with-one-page from v1.
- [ ] Browser: rewrite v1's `integrations/browser` as an owned layer. One policy object (allowlist with subdomains, private addresses, robots, shared pacing, resource filtering), the twelve tools used, a capture hook that receives plain values. Drop CDP, auto-install, storage state, event-log tools, protocols file and the durability guard. Port `test_browser.py`.
- [ ] Evidence: `quote_checks.py` (text normalization, mojibake repair, name-in-quote, link-in-HTML) and `capture.py` from v1, with the snapshot now holding bytes and text together and sharing text by hash.
- [ ] Jobs: the Procrastinate wrapper, worker, stalled sweep and purge from alloy, taking resources as an argument.
- [ ] Usage recording: one `usage` table and one `record_usage` function for model and search calls, priced from a prices data file.
- [ ] Unit tests ported for quote checks, name matching, media detection, browser policy.

**Done when** a test drives real Chromium against the fixture site and every navigating tool produces a snapshot, a refused domain produces a blocked attempt and nothing else, and a PDF goes through `read_file` to text.

## Phase 3: graph, status changes and review

- [ ] `graph/service.py`: create and find places and institutions, add aliases, duplicate search (trigram, designator rule, one row per entity, at most five), normalize URLs, candidate domain names.
- [ ] `graph/status_changes.py`: trust a domain, reject a domain, verify a homepage, verify an institution, reject an institution, merge two entities. Each records `entered_by`, sets status once and returns what to spawn.
- [ ] Review: raise (dedup per entity, fold into a kind when the rule has one), approve, reject, merge, decide a kind, settle open type items when the setup tables change. Review API.
- [ ] Merge fixed properly: check conflicts first, move aliases, evidence, sources, homepages and open assignments, set the government link and the homepage link.
- [ ] Integration tests for every status change and every review action.

**Done when** every path that changes a status goes through `status_changes.py` (a grep for direct status writes finds nothing else) and the review tests pass.

## Phase 4: runs, assignments and the agent

- [ ] Runs: create with filter and mode, pause, stop, release held. `assignments/lifecycle.py` with the status and result columns and the allowed moves.
- [ ] Spawning as a consequence of status changes, obeying the run's mode. No `ensure-items` command.
- [ ] One descriptor per assignment type: subject kind, tools, finishing tool, goal text, checklist, budget, model choice.
- [ ] The runner from v1: sessions, half-window handoff, budgets, twenty sessions per job, requeue, finish as `failed` on the last attempt. Three ended signals collapsed into one.
- [ ] `agent_run_events`: write the session's message list (prompt, text, tool calls, results) as rows when a session ends.
- [ ] Video: `record_video` on the run turns on Playwright video for the browser context; store each file through the storage port and note it as a `video` event.
- [ ] Purge jobs, scheduled daily: delete videos of assignments finished more than `video_keep_days` ago (default 7) from storage and mark their events as purged; delete the events of assignments finished more than `events_keep_days` ago (default 90). Both settings; findings, usage and the summary are never purged. Snapshots no evidence cites are pruned when the assignment finishes, as in spec section 8.2.
- [ ] Findings as typed functions registered as tools through one adapter: `save_institution` (with parent and `procurement_handled_by`), `save_homepage`, `save_source`, `confirm_domain`, `reject_domain`, `domain_moved`, `status`, `request_review`, `finish`, `read_file`, `search`.
- [ ] The merged `find_homepage` assignment: trusted-domain path, new-domain path, search path; `no_homepage` result with its review item.
- [ ] `find_institutions` and `find_sources` with the checklist, refused short close, `complete_with_gaps` and its review item.
- [ ] Briefing and prompts from v1, rewritten in the glossary's words and read from the setup tables.
- [ ] Integration tests with a scripted model for each type and each end state; port v1's findings tests.
- [ ] CLI: `seed`, `load-list`, `run create [--video]|pause|stop|release`, `worker`.

**Done when** a step-mode run on one eval subject, released one assignment at a time, produces verified institutions, homepages and sources with checked quotes, and every end state in spec section 7.2 is reached by a test.

## Phase 5: evals

- [ ] Port the dataset, its schema, validator and README. Add `parent` labels in place of relationship labels.
- [ ] Port the scorer; score parent links from `parent_institution_id`.
- [ ] The harness: an eval run is a run with `is_eval`, a separate graph database from the same settings object, seeds through the real loader with hold as a parameter, serves the queues in process, starts a parse worker, scores, prices, writes `eval_runs` and `eval_scores`.
- [ ] `public-atlas eval run --subject ... --json` and `eval score`.
- [ ] Unit tests for the scorer from v1.

**Done when** one full eval run over the twelve subjects finishes, its scores and cost are rows in the main database, and a second run appears beside it.

## Phase 6: console

- [ ] Regenerate the API client from the new routes.
- [ ] Runs list and detail: create, pause, stop, release held, progress by status, cost.
- [ ] Assignments list and detail: filters, the event timeline, video playback, findings, spend, result.
- [ ] Institutions table with search and filters; institution detail with aliases, parent, homepage, sources by type, evidence quotes linked to presigned snapshot downloads.
- [ ] Review queue: items with snapshot and highlighted quote; approve, reject, merge; kinds decided together.
- [ ] Setup pages: country settings, administrative levels, institution types, source types, a country's expected sources per type.
- [ ] Evals page: runs over time, scores per type, cost.
- [ ] Web tests for the list state, formatting and error handling that the pages use.

**Done when** every page works against the live database and the eval database, and `vp run check` and `vp run test` pass.

## Phase 7: the Ontario pilot

- [ ] Load the live database: `seed canada`, then `load-list ontario_places --apply`.
- [ ] Run `find_homepage` for all 444 governments in auto mode. Read the review queue; fix rules where the queue shows a pattern.
- [ ] Run the eval twice. Fix by the largest miss bucket, re-run the touched subjects, repeat until the gates pass or every miss has a written reason.
- [ ] Release `find_institutions` and `find_sources` for the province in auto mode, sources first. Watch cost per assignment type.
- [ ] Write `docs/eval-results.md`: recall and precision per type, the gates, cost per subject, the explained misses.
- [ ] Update the spec's pilot table with the numbers.

**Done when** the gates pass or are explained, Ontario's graph is in the live database, and the numbers are written down.

## Phase 8: demo and application

- [ ] A top section in the README for a reader who does not know the project: what it does, the verification idea in two sentences, the eval numbers, how it would scale to the United States, the known gaps.
- [ ] Deploy with the pilot database loaded (R2 for storage), or a read-only local build the recording can use.
- [ ] Record a three-minute demo: start a step-mode run on one city with video on and release an assignment; watch the assignment detail fill with events and play the video; open the institution page and click a quote through to its snapshot; decide a review item; show the eval page with two runs.
- [ ] Make the repository public. Check nothing secret is in history.
- [ ] Write the application: a short cover note that links the repository, the README section and the recording, and maps the project to the Data Mining Software Engineer posting (crawling and extraction, entity resolution, a verified graph, evals, cost control).
- [ ] Submit at the posting and note the date here.

**Done when** the application is submitted.

## Open decisions

| Decision | Options | Decide when |
| --- | --- | --- |
| Pause semantics | Worker checks run status per assignment, or queued jobs are moved to held | Phase 4 |
| Sources of an institution whose homepage is on a platform | Each source to review, or trust a URL prefix under the verified homepage | Phase 7, after counting them |
| Model per assignment type | Keep one model, or a cheaper one for sources | Phase 7, from eval cost |
